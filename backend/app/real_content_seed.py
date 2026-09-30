"""Idempotent, human-reviewed first Polity/Fundamental Rights content slice."""
from datetime import datetime, timezone

from .database import SessionLocal
from .models import (LearningCard, LearningCardSourceRef, Question, QuestionOption, QuestionTopicClassification,
                     SourceChunk, SourceDocument, SourceDocumentTopic, Subject, Topic)

NCERT_URL = "https://www.ncert.nic.in/textbook/pdf/keps202.pdf"
UPSC_PAPER_URL = "https://www.upsc.gov.in/sites/default/files/QP-CSP-24-GENERAL-STUDIES-PAPER-I-180624.pdf"


def seed():
    with SessionLocal() as db:
        subject = db.query(Subject).filter_by(slug="indian-polity").one()
        topic = db.query(Topic).filter_by(slug="fundamental-rights").one()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        ncert = db.query(SourceDocument).filter_by(source_url=NCERT_URL).first()
        if not ncert:
            ncert = SourceDocument(title="Indian Constitution at Work — Chapter 2: Rights in the Indian Constitution",
                publisher="National Council of Educational Research and Training", source_type="NCERT", subject_id=subject.id,
                source_url=NCERT_URL, publication_year=None, version="Official textbook PDF", 
                license_notes="Copyright remains with NCERT. Link to the official source; do not redistribute the PDF.",
                ingestion_status="PUBLISHED", created_at=now, updated_at=now)
            db.add(ncert); db.flush()
            db.add(SourceDocumentTopic(document_id=ncert.id, topic_id=topic.id, classification_method="MANUAL", confidence=1.0, review_status="APPROVED"))
        if not db.query(LearningCard).filter_by(slug="fundamental-rights-why-rights-are-constitutional").first():
            # This locator is intentionally not represented as extracted source text.
            locator = SourceChunk(document_id=ncert.id, topic_id=topic.id, page_number=1,
                section="Chapter 2 — Rights in the Indian Constitution", chunk_index=900001,
                text="Source locator only; the page text is available in the linked NCERT publication and is not cached here.",
                metadata_json={"locator_only": True, "printed_page": 26})
            db.add(locator); db.flush()
            card = LearningCard(topic_id=topic.id, title="Why constitutional rights matter",
                slug="fundamental-rights-why-rights-are-constitutional",
                content="Part III of the Constitution sets out Fundamental Rights and places limits on public power. These guarantees give people standards they can invoke and courts a basis for reviewing state action. Read the chapter's discussion of rights alongside its treatment of reasonable restrictions: a right's scope and its limits belong together.",
                display_order=1, status="PUBLISHED", content_origin="PRASHNA_SUMMARY", classification_method="MANUAL",
                classification_confidence=1.0, created_at=now)
            db.add(card); db.flush()
            db.add(LearningCardSourceRef(card_id=card.id, source_chunk_id=locator.id, reference_order=1,
                attribution_note="NCERT, Indian Constitution at Work, Chapter 2; PDF page 1 (printed page 26). Summary in Prashna's own words."))

        upsc = db.query(SourceDocument).filter_by(source_url=UPSC_PAPER_URL).first()
        if not upsc:
            upsc = SourceDocument(title="Civil Services (Preliminary) Examination, 2024 — General Studies Paper I",
                publisher="Union Public Service Commission", source_type="UPSC", subject_id=subject.id,
                source_url=UPSC_PAPER_URL, publication_year=2024, version="Official paper", 
                license_notes="Official UPSC question paper; link to source, no paper file redistributed.",
                ingestion_status="PUBLISHED", created_at=now, updated_at=now)
            db.add(upsc); db.flush()
            db.add(SourceDocumentTopic(document_id=upsc.id, topic_id=topic.id, classification_method="MANUAL", confidence=1.0, review_status="APPROVED"))
        if not db.query(Question).filter_by(source_type="UPSC_PYQ", year=2024, exam="Civil Services Examination",
                                            stage="Prelims", paper="General Studies Paper I", question_number="76").first():
            question = Question(topic_id=topic.id, question_text="Under which of the following Articles of the Constitution of India, has the Supreme Court of India placed the Right to Privacy?",
                explanation="The Supreme Court has recognised privacy as a fundamental right protected under Article 21.",
                difficulty="MEDIUM", question_type="MCQ", source="UPSC CSE Prelims 2024, GS Paper I",
                is_published=True, source_type="UPSC_PYQ", year=2024, exam="Civil Services Examination",
                stage="Prelims", paper="General Studies Paper I", question_number="76", source_document_id=upsc.id,
                status="PUBLISHED", classification_method="MANUAL", classification_confidence=1.0)
            question.options = [QuestionOption(option_text="Article 15", is_correct=False, display_order=0),
                QuestionOption(option_text="Article 16", is_correct=False, display_order=1),
                QuestionOption(option_text="Article 19", is_correct=False, display_order=2),
                QuestionOption(option_text="Article 21", is_correct=True, display_order=3)]
            db.add(question); db.flush()
            db.add(QuestionTopicClassification(question_id=question.id, topic_id=topic.id,
                classification_method="MANUAL", confidence=1.0, review_status="APPROVED"))
        db.commit()
        print("Seeded source-linked Fundamental Rights reading card and UPSC CSE Prelims 2024 GS-I Q76.")


if __name__ == "__main__":
    seed()
