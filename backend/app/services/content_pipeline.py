"""Local/admin content ingestion. All extracted material remains in REVIEW."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import re
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from ..models import (ContentIngestionJob, LearningCard, LearningCardSourceRef, Question,
                      QuestionOption, QuestionTopicClassification, SourceChunk, SourceDocument, SourceDocumentTopic)


def extract_pages(path: str | Path) -> list[tuple[int, str]]:
    """Return (1-based physical page, cleaned text) without flattening provenance."""
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader
        return [(number, clean_text(page.extract_text() or ""))
                for number, page in enumerate(PdfReader(str(file_path)).pages, start=1)]
    if suffix in {".txt", ".md"}:
        text = file_path.read_text(encoding="utf-8-sig")
        return [(number, clean_text(page)) for number, page in enumerate(text.split("\f"), start=1)]
    raise ValueError("Only PDF, TXT and Markdown documents are supported")


def clean_text(value: str) -> str:
    value = value.replace("\x00", " ").replace("\u00ad", "")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r" *\n *", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def chunk_pages(pages: list[tuple[int, str]], *, max_chars: int = 1800) -> list[dict]:
    """Split per page and retain page and best-effort heading metadata."""
    chunks: list[dict] = []
    for page_number, text in pages:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        current: list[str] = []
        length = 0
        section = None
        for paragraph in paragraphs:
            if len(paragraph) <= 140 and not paragraph.endswith((".", ";", ",")):
                section = paragraph.lstrip("# ").strip()[:300]
            pieces = [paragraph[i:i + max_chars] for i in range(0, len(paragraph), max_chars)]
            for piece in pieces:
                if current and length + len(piece) + 2 > max_chars:
                    chunks.append({"page_number": page_number, "section": section,
                                   "text": "\n\n".join(current)})
                    current, length = [], 0
                current.append(piece)
                length += len(piece) + 2
        if current:
            chunks.append({"page_number": page_number, "section": section,
                           "text": "\n\n".join(current)})
    return chunks


def register_document(db: Session, *, title: str, publisher: str, source_type: str,
                      file_path: str, source_url: str | None = None, subject_id: int | None = None,
                      topic_id: int | None = None, publication_year: int | None = None,
                      version: str | None = None, license_notes: str | None = None) -> tuple[SourceDocument, bool]:
    path = Path(file_path).expanduser().resolve(strict=True)
    if path.suffix.lower() not in {".pdf", ".txt", ".md"} or not path.is_file():
        raise ValueError("File must be a local PDF, TXT or Markdown file")
    if source_type not in {"NCERT", "UPSC", "GOVERNMENT", "PARLIAMENTARY", "IGNOU", "NIOS", "COACHING", "NEWS_CURRENT_AFFAIRS", "OTHER"}:
        raise ValueError("Unsupported source type")
    checksum = sha256()
    with path.open("rb") as source_file:
        for block in iter(lambda: source_file.read(1024 * 1024), b""):
            checksum.update(block)
    digest = checksum.hexdigest()
    existing = db.query(SourceDocument).filter(SourceDocument.checksum == digest).first()
    if existing:
        return existing, True
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    document = SourceDocument(title=title.strip(), publisher=publisher.strip(), source_type=source_type,
        subject_id=subject_id, source_url=source_url, file_identifier=str(path), publication_year=publication_year,
        version=version, license_notes=license_notes, checksum=digest, ingestion_status="DRAFT",
        created_at=now, updated_at=now)
    db.add(document)
    db.flush()
    db.add(ContentIngestionJob(document_id=document.id, status="QUEUED", phase="QUEUED", queued_at=now))
    if topic_id is not None:
        db.add(SourceDocumentTopic(document_id=document.id, topic_id=topic_id,
            classification_method="MANUAL", confidence=1.0, review_status="APPROVED"))
    db.commit()
    db.refresh(document)
    return document, False


def process_next_job(db: Session) -> ContentIngestionJob | None:
    job = db.query(ContentIngestionJob).filter(ContentIngestionJob.status == "QUEUED").order_by(ContentIngestionJob.id).first()
    if job is None:
        return None
    document = db.get(SourceDocument, job.document_id)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    job.status = "PROCESSING"; job.phase = "EXTRACTING"; job.started_at = now
    document.ingestion_status = "PROCESSING"
    db.commit()
    try:
        pages = extract_pages(document.file_identifier or "")
        if not any(text for _, text in pages):
            raise ValueError("No extractable text found; OCR is not enabled")
        chunks = chunk_pages(pages)
        topic_mappings = db.query(SourceDocumentTopic).filter_by(document_id=document.id).all()
        mapped_topic_id = topic_mappings[0].topic_id if len(topic_mappings) == 1 else None
        for index, chunk in enumerate(chunks):
            db.add(SourceChunk(document_id=document.id, topic_id=mapped_topic_id, chunk_index=index, page_number=chunk["page_number"],
                section=chunk["section"], text=chunk["text"], metadata_json={"extractor": "pypdf-or-text", "index": index}))
        job.phase = "REVIEW_REQUIRED"; job.status = "REVIEW"; job.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
        document.ingestion_status = "REVIEW"; document.updated_at = job.finished_at
        db.commit()
    except Exception as exc:
        db.rollback()
        job = db.get(ContentIngestionJob, job.id); document = db.get(SourceDocument, job.document_id)
        job.status = "FAILED"; job.phase = "FAILED"; job.error_summary = f"{type(exc).__name__}: {str(exc)[:300]}"
        job.finished_at = datetime.now(timezone.utc).replace(tzinfo=None); document.ingestion_status = "FAILED"
        db.commit()
    return job


def validation_report(db: Session) -> dict:
    """Small deterministic report; unsupported semantic claims remain human review."""
    from ..models import LearningCard, LearningCardSourceRef, Question, QuestionOption
    documents = db.query(SourceDocument).all()
    cards = db.query(LearningCard).all()
    questions = db.query(Question).filter(Question.source_type == "UPSC_PYQ").all()
    missing_refs = [card.id for card in cards if not db.query(LearningCardSourceRef.id).filter_by(card_id=card.id).first()]
    malformed = []
    for question in questions:
        opts = db.query(QuestionOption).filter_by(question_id=question.id).all()
        if len(opts) < 2 or sum(bool(option.is_correct) for option in opts) != 1:
            malformed.append(question.id)
    return {"documents": len(documents), "duplicate_checksums": len(documents) - len({d.checksum for d in documents if d.checksum}),
        "documents_missing_source_locator": [d.id for d in documents if not (d.source_url or d.file_identifier)],
        "documents_missing_attribution": [d.id for d in documents if not d.publisher.strip() or d.publisher.startswith("Unspecified")],
        "documents_missing_subject": [d.id for d in documents if not d.subject_id],
        "documents_missing_topic_mapping": [d.id for d in documents if not db.query(SourceDocumentTopic.id).filter_by(document_id=d.id).first()],
        "cards": len(cards), "cards_missing_source_refs": missing_refs,
        "cards_missing_topic": [card.id for card in cards if not card.topic_id],
        "cards_empty": [card.id for card in cards if not card.title.strip() or not card.content.strip()],
        "pyqs": len(questions), "pyqs_missing_metadata": [q.id for q in questions if not (q.year and q.question_number and q.exam and q.stage and q.paper and q.source_document_id)],
        "pyqs_missing_year": [q.id for q in questions if not q.year],
        "pyqs_missing_question_number": [q.id for q in questions if not q.question_number],
        "pyqs_malformed_options": malformed,
        "pyqs_invalid_option_count": [q.id for q in questions if not 2 <= db.query(QuestionOption).filter_by(question_id=q.id).count() <= 6],
        "pyqs_missing_official_source": [q.id for q in questions if not q.source_document or not q.source_document.source_url or
            urlparse(q.source_document.source_url).hostname not in {"upsc.gov.in", "www.upsc.gov.in"}],
        "pyqs_empty_text": [q.id for q in questions if not q.question_text.strip()],
        "duplicate_pyq_metadata": [q.id for q in questions if db.query(Question.id).filter(
            Question.id != q.id, Question.source_type == "UPSC_PYQ", Question.year == q.year,
            Question.exam == q.exam, Question.stage == q.stage, Question.paper == q.paper,
            Question.question_number == q.question_number).first()],
        "duplicate_pyq_text": [q.id for q in questions if db.query(Question.id).filter(
            Question.id != q.id, Question.source_type == "UPSC_PYQ", Question.year == q.year,
            Question.exam == q.exam, Question.paper == q.paper, Question.question_text == q.question_text).first()],
        "low_confidence_classifications": [d.id for d in documents if d.ingestion_status == "PUBLISHED" and
            db.query(SourceDocumentTopic).filter(SourceDocumentTopic.document_id == d.id,
                (SourceDocumentTopic.confidence.is_(None)) | (SourceDocumentTopic.confidence < 0.7)).first()],
        "semantic_claim_review": "Human review required; automated validation cannot establish factual support."}


def publish_card(db: Session, card_id: int) -> LearningCard:
    card = db.get(LearningCard, card_id)
    if not card or not card.title.strip() or not card.content.strip():
        raise ValueError("Card must exist and have a title and content")
    if card.classification_confidence is None or card.classification_confidence < 0.7:
        raise ValueError("Topic classification confidence is too low; manual review is required")
    refs = db.query(LearningCardSourceRef, SourceChunk, SourceDocument).join(
        SourceChunk, LearningCardSourceRef.source_chunk_id == SourceChunk.id).join(
        SourceDocument, SourceChunk.document_id == SourceDocument.id).filter(LearningCardSourceRef.card_id == card.id).all()
    if not refs:
        raise ValueError("A source-backed learning card must cite at least one source chunk")
    if any(not doc.title.strip() or not doc.publisher.strip() or doc.publisher.startswith("Unspecified") or
           not (doc.source_url or doc.file_identifier) for _, _, doc in refs):
        raise ValueError("Every cited source needs identified title, publisher, and source URL or local file")
    if any(not chunk.page_number or doc.ingestion_status not in {"REVIEW", "PUBLISHED"}
           for _, chunk, doc in refs):
        raise ValueError("Every cited source needs a valid page and reviewed document")
    card.status = "PUBLISHED"
    db.commit()
    return card


def publish_pyq(db: Session, question_id: int) -> Question:
    question = db.get(Question, question_id)
    if not question or question.source_type != "UPSC_PYQ":
        raise ValueError("Question is not a registered UPSC PYQ")
    if not all((question.year, question.exam, question.stage, question.paper, question.question_number, question.source_document_id)):
        raise ValueError("PYQ publication requires year, exam, stage, paper, number, and source document")
    source = db.get(SourceDocument, question.source_document_id)
    official_host = urlparse(source.source_url).hostname if source and source.source_url else None
    if not source or source.source_type != "UPSC" or official_host not in {"upsc.gov.in", "www.upsc.gov.in"} or source.ingestion_status not in {"REVIEW", "PUBLISHED"}:
        raise ValueError("PYQ must cite a reviewed UPSC source document with an official URL")
    if question.classification_confidence is None or question.classification_confidence < 0.7:
        raise ValueError("Topic classification confidence is too low; manual review is required")
    mappings = db.query(QuestionTopicClassification).filter_by(question_id=question.id).all()
    if not mappings:
        mappings = [QuestionTopicClassification(question_id=question.id, topic_id=question.topic_id,
            classification_method=question.classification_method or "MANUAL",
            confidence=question.classification_confidence, review_status="REVIEW")]
        db.add(mappings[0])
    if any(mapping.confidence is None or mapping.confidence < 0.7 for mapping in mappings):
        raise ValueError("Every topic mapping needs reviewed confidence of at least 0.7")
    options = db.query(QuestionOption).filter_by(question_id=question.id).all()
    if len(options) < 2 or sum(bool(option.is_correct) for option in options) != 1:
        raise ValueError("PYQ needs at least two options and exactly one verified answer")
    question.status = "PUBLISHED"; question.is_published = True
    for mapping in mappings:
        mapping.review_status = "APPROVED"
    db.commit()
    return question
