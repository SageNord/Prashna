import sys
import types

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (ContentIngestionJob, LearningCard, LearningCardSourceRef, Question,
                        QuestionOption, SourceChunk, SourceDocument, Topic)
from app.services.content_pipeline import chunk_pages, process_next_job, register_document, validation_report
from app.services.content_pipeline import publish_card, publish_pyq
from app.scripts.import_pyqs import import_pyqs, validate_pyq_payload
from app.scripts.process_content_jobs import register_local_documents
import pytest


def make_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'content-test.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_page_aware_chunks_keep_page_and_heading():
    chunks = chunk_pages([(2, "## Equality\n\nArticle 14 applies equality before law to every person.")], max_chars=30)
    assert chunks
    assert all(chunk["page_number"] == 2 for chunk in chunks)
    assert chunks[0]["section"] == "Equality"


def test_registration_deduplicates_and_worker_keeps_content_in_review(tmp_path):
    db = make_db(tmp_path)
    source = tmp_path / "fixture.txt"
    source.write_text("Chapter 2\n\nRights create enforceable limits.\fEquality is guaranteed.", encoding="utf-8")
    first, duplicate = register_document(db, title="Fixture", publisher="Fixture Publisher", source_type="OTHER", file_path=str(source))
    again, was_duplicate = register_document(db, title="Fixture duplicate", publisher="Fixture Publisher", source_type="OTHER", file_path=str(source))
    assert not duplicate and was_duplicate and first.id == again.id
    job = process_next_job(db)
    assert job.status == "REVIEW"
    chunks = db.query(SourceChunk).filter_by(document_id=first.id).order_by(SourceChunk.chunk_index).all()
    assert [chunk.page_number for chunk in chunks] == [1, 2]
    assert db.get(SourceDocument, first.id).ingestion_status == "REVIEW"
    assert db.query(ContentIngestionJob).count() == 1


def test_local_folder_scanner_uses_sidecar_taxonomy_and_processes_text(tmp_path):
    db = make_db(tmp_path)
    subject = __import__("app.models", fromlist=["Subject"]).Subject(name="Indian Polity", slug="indian-polity")
    db.add(subject); db.flush()
    topic = Topic(subject_id=subject.id, name="Fundamental Rights", slug="fundamental-rights")
    db.add(topic); db.commit()
    content = tmp_path / "content"
    folder = content / "polity" / "fundamental-rights"
    folder.mkdir(parents=True)
    source = folder / "chapter.txt"
    source.write_text("Chapter 2\n\nRights are protected.\fArticle 14 supports equality.", encoding="utf-8")
    source.with_suffix(".txt.meta.json").write_text(
        '{"title":"Rights chapter","publisher":"NCERT","source_type":"NCERT",'
        '"source_url":"https://ncert.nic.in/example.pdf","subject_slug":"indian-polity",'
        '"topic_slug":"fundamental-rights"}', encoding="utf-8")
    assert register_local_documents(db, content) == (1, 0, 0)
    job = process_next_job(db)
    assert job.status == "REVIEW"
    document = db.query(SourceDocument).one()
    assert document.subject_id == subject.id and document.title == "Rights chapter"
    chunks = db.query(SourceChunk).filter_by(document_id=document.id).order_by(SourceChunk.chunk_index).all()
    assert [chunk.page_number for chunk in chunks] == [1, 2]
    assert all(chunk.topic_id == topic.id for chunk in chunks)
    assert register_local_documents(db, content) == (0, 1, 0)


def test_pdf_extraction_preserves_physical_page_numbers(tmp_path, monkeypatch):
    from app.services import content_pipeline

    class Page:
        def __init__(self, value): self.value = value
        def extract_text(self): return self.value
    class Reader:
        def __init__(self, _path): self.pages = [Page("First page."), Page("Second page.")]
    monkeypatch.setitem(sys.modules, "pypdf", types.SimpleNamespace(PdfReader=Reader))
    pdf = tmp_path / "fixture.pdf"
    pdf.write_bytes(b"synthetic fixture")
    assert content_pipeline.extract_pages(pdf) == [(1, "First page."), (2, "Second page.")]


def test_validation_report_checks_card_provenance_and_pyq_fields(tmp_path):
    db = make_db(tmp_path)
    subject = __import__("app.models", fromlist=["Subject"]).Subject(name="Polity", slug="polity")
    db.add(subject); db.flush()
    topic = Topic(subject_id=subject.id, name="Fundamental Rights", slug="fundamental-rights")
    db.add(topic); db.flush()
    document = SourceDocument(title="Paper", publisher="UPSC", source_type="UPSC", source_url="https://example.test/paper",
        ingestion_status="PUBLISHED")
    db.add(document); db.flush()
    chunk = SourceChunk(document_id=document.id, topic_id=topic.id, chunk_index=0, page_number=1,
        text="Locator", metadata_json={})
    db.add(chunk); db.flush()
    card = LearningCard(topic_id=topic.id, title="Card", slug="card", content="Paraphrased note", status="PUBLISHED")
    db.add(card); db.flush()
    db.add(LearningCardSourceRef(card_id=card.id, source_chunk_id=chunk.id, reference_order=1))
    q = Question(topic_id=topic.id, question_text="Actual question", explanation="Reason", source_type="UPSC_PYQ",
        year=2024, exam="CSE", stage="Prelims", paper="GS I", question_number="76", source_document_id=document.id)
    q.options = [QuestionOption(option_text="A", is_correct=True, display_order=0),
                 QuestionOption(option_text="B", is_correct=False, display_order=1)]
    db.add(q); db.commit()
    report = validation_report(db)
    assert report["cards_missing_source_refs"] == []
    assert report["pyqs_missing_metadata"] == []
    assert report["pyqs_malformed_options"] == []
    assert "Human review required" in report["semantic_claim_review"]


def test_publication_requires_provenance_and_verified_pyq_metadata(tmp_path):
    db = make_db(tmp_path)
    subject = __import__("app.models", fromlist=["Subject"]).Subject(name="Polity", slug="polity")
    db.add(subject); db.flush()
    topic = Topic(subject_id=subject.id, name="Fundamental Rights", slug="fundamental-rights")
    db.add(topic); db.flush()
    card = LearningCard(topic_id=topic.id, title="Note", slug="note", content="A short note.", status="REVIEW",
                        classification_confidence=1.0)
    db.add(card); db.commit()
    with pytest.raises(ValueError, match="cite at least one"):
        publish_card(db, card.id)
    assert db.get(LearningCard, card.id).status == "REVIEW"

    upsc = SourceDocument(title="Official paper", publisher="UPSC", source_type="UPSC", source_url="https://upsc.gov.in/paper",
                          ingestion_status="PUBLISHED")
    db.add(upsc); db.flush()
    pyq = Question(topic_id=topic.id, question_text="Exact source question", explanation="Verified explanation",
                   source_type="UPSC_PYQ", year=2024, exam="CSE", stage="Prelims", paper="GS I",
                   question_number="1", source_document_id=upsc.id, is_published=False,
                   classification_confidence=1.0)
    db.add(pyq); db.flush()
    pyq.options = [QuestionOption(option_text="A", is_correct=False, display_order=0),
                   QuestionOption(option_text="B", is_correct=False, display_order=1)]
    db.commit()
    with pytest.raises(ValueError, match="verified answer"):
        publish_pyq(db, pyq.id)
    assert not db.get(Question, pyq.id).is_published
    db.query(QuestionOption).filter_by(question_id=pyq.id, display_order=0).one().is_correct = True
    db.commit()
    assert publish_pyq(db, pyq.id).is_published


def test_pyq_json_import_preserves_wording_and_waits_for_answer_review(tmp_path):
    db = make_db(tmp_path)
    subject = __import__("app.models", fromlist=["Subject"]).Subject(name="Indian Polity", slug="indian-polity")
    db.add(subject); db.flush()
    topic = Topic(subject_id=subject.id, name="Fundamental Rights", slug="fundamental-rights")
    db.add(topic); db.commit()
    exact_text = "  Which Article protects the Right to Privacy?  "
    payload = [{"year": 2024, "exam": "Civil Services Examination", "stage": "Prelims",
        "paper": "General Studies Paper I", "question_number": 76, "question_text": exact_text,
        "options": ["Article 15", "Article 16", "Article 19", "Article 21"],
        "correct_option": 4, "subject": "Indian Polity", "topic": "Fundamental Rights",
        "official_source_url": "https://www.upsc.gov.in/papers/cse-2024.pdf"}]
    imported = import_pyqs(db, payload)
    assert imported["added"] == 1 and imported["duplicates"] == 0
    assert imported["pending_answer_verification"] == 1 and len(imported["question_ids"]) == 1
    question = db.query(Question).filter_by(source_type="UPSC_PYQ").one()
    assert question.question_text == exact_text
    assert question.status == "REVIEW" and not question.is_published
    assert not any(option.is_correct for option in question.options)
    assert [option.option_text for option in question.options] == payload[0]["options"]
    duplicate_result = import_pyqs(db, payload)
    assert duplicate_result["duplicates"] == 1 and duplicate_result["duplicate_question_ids"] == [question.id]


def test_pyq_json_rejects_missing_official_source_and_malformed_options():
    payload = [{"year": 2024, "exam": "CSE", "stage": "Prelims", "paper": "GS I",
        "question_number": 1, "question_text": "A question", "options": ["Only one"],
        "subject": "Indian Polity", "topic": "Fundamental Rights", "official_source_url": "https://example.com/paper.pdf"}]
    with pytest.raises(ValueError, match="2–6"):
        validate_pyq_payload(payload)
    payload[0]["options"] = ["A", "B"]
    with pytest.raises(ValueError, match="UPSC URL"):
        validate_pyq_payload(payload)
