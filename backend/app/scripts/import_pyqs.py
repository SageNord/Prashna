"""Import manually transcribed PYQs from JSON into the existing review workflow."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

from ..database import SessionLocal
from ..models import Question, QuestionOption, QuestionTopicClassification, SourceDocument, SourceDocumentTopic, Subject, Topic


def validate_pyq_payload(payload: object) -> list[dict]:
    if not isinstance(payload, list) or not payload:
        raise ValueError("PYQ JSON root must be a non-empty array")
    required = ("year", "exam", "stage", "paper", "question_number", "question_text", "options", "subject", "topic", "official_source_url")
    for index, row in enumerate(payload, 1):
        if not isinstance(row, dict):
            raise ValueError(f"Question {index} must be a JSON object")
        missing = [field for field in required if field not in row or row[field] is None or row[field] == ""]
        if missing:
            raise ValueError(f"Question {index} is missing: {', '.join(missing)}")
        if type(row["year"]) is not int or not 1900 <= row["year"] <= 2100:
            raise ValueError(f"Question {index}: year must be a valid integer")
        for field in ("exam", "stage", "paper", "question_text", "subject", "topic"):
            if not isinstance(row[field], str) or not row[field].strip():
                raise ValueError(f"Question {index}: {field} must be non-empty text")
        if type(row["question_number"]) not in (int, str) or not str(row["question_number"]).strip():
            raise ValueError(f"Question {index}: question_number must be text or an integer")
        options = row["options"]
        if not isinstance(options, list) or not 2 <= len(options) <= 6 or any(not isinstance(x, str) or not x.strip() for x in options):
            raise ValueError(f"Question {index}: options must contain 2–6 non-empty strings")
        parsed = urlparse(row["official_source_url"] if isinstance(row["official_source_url"], str) else "")
        if parsed.scheme != "https" or parsed.hostname not in {"upsc.gov.in", "www.upsc.gov.in"}:
            raise ValueError(f"Question {index}: official_source_url must be an HTTPS UPSC URL")
        answer = row.get("correct_option")
        if answer is not None and (type(answer) is not int or not 1 <= answer <= len(options)):
            raise ValueError(f"Question {index}: correct_option must be a 1-based option number")
        if row.get("answer_verified") is True and answer is None:
            raise ValueError(f"Question {index}: answer_verified requires correct_option")
        if type(row.get("answer_verified", False)) is not bool:
            raise ValueError(f"Question {index}: answer_verified must be boolean")
        if "explanation" in row and not isinstance(row["explanation"], str):
            raise ValueError(f"Question {index}: explanation must be text")
    return payload


def import_pyqs(db, payload: object) -> dict:
    rows = validate_pyq_payload(payload)
    added = duplicates = pending_answers = 0
    question_ids, duplicate_ids = [], []
    for row in rows:
        subject = db.query(Subject).filter((Subject.slug == row["subject"]) | (Subject.name.ilike(row["subject"]))).first()
        if not subject:
            raise ValueError(f"Unknown subject: {row['subject']}")
        topic = db.query(Topic).filter(Topic.subject_id == subject.id,
            (Topic.slug == row["topic"]) | (Topic.name.ilike(row["topic"]))).first()
        if not topic:
            raise ValueError(f"Unknown topic for {subject.name}: {row['topic']}")
        number = str(row["question_number"])
        exists = db.query(Question).filter(Question.source_type == "UPSC_PYQ", Question.year == row["year"],
            Question.exam == row["exam"], Question.stage == row["stage"], Question.paper == row["paper"],
            Question.question_number == number).first()
        duplicate = exists or db.query(Question).filter(Question.source_type == "UPSC_PYQ", Question.year == row["year"],
            Question.exam == row["exam"], Question.paper == row["paper"], Question.question_text == row["question_text"]).first()
        if duplicate:
            duplicates += 1
            duplicate_ids.append(duplicate.id)
            continue
        url = row["official_source_url"]
        source = db.query(SourceDocument).filter_by(source_url=url).first()
        if source and source.source_type != "UPSC":
            raise ValueError(f"Source URL is already registered as non-UPSC: {url}")
        if not source:
            source = SourceDocument(title=f"UPSC {row['exam']} {row['year']} — {row['paper']}",
                publisher="Union Public Service Commission", source_type="UPSC", subject_id=subject.id,
                source_url=url, publication_year=row["year"], version="Official paper link",
                license_notes="Official question paper link; this importer stores question text, not the source PDF.",
                ingestion_status="REVIEW")
            db.add(source); db.flush()
        if not db.query(SourceDocumentTopic).filter_by(document_id=source.id, topic_id=topic.id).first():
            db.add(SourceDocumentTopic(document_id=source.id, topic_id=topic.id,
                classification_method="MANUAL", confidence=1.0, review_status="REVIEW"))
            db.flush()
        answer = row.get("correct_option") if row.get("answer_verified") is True else None
        question = Question(topic_id=topic.id, question_text=row["question_text"],
            explanation=row.get("explanation", ""), difficulty="MEDIUM", question_type="MCQ",
            source=f"UPSC CSE {row['stage']} — {row['year']}", is_published=False, source_type="UPSC_PYQ",
            year=row["year"], exam=row["exam"], stage=row["stage"], paper=row["paper"],
            question_number=number, source_document_id=source.id, status="REVIEW",
            classification_method="MANUAL", classification_confidence=1.0)
        question.options = [QuestionOption(option_text=text, is_correct=(answer == option_number), display_order=option_number - 1)
                            for option_number, text in enumerate(row["options"], 1)]
        db.add(question); db.flush()
        question_ids.append(question.id)
        db.add(QuestionTopicClassification(question_id=question.id, topic_id=topic.id,
            classification_method="MANUAL", confidence=1.0, review_status="REVIEW"))
        added += 1
        if answer is None:
            pending_answers += 1
    db.commit()
    return {"added": added, "duplicates": duplicates, "pending_answer_verification": pending_answers,
            "question_ids": question_ids, "duplicate_question_ids": duplicate_ids}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_file", type=Path)
    args = parser.parse_args(argv)
    payload = json.loads(args.json_file.read_text(encoding="utf-8"))
    with SessionLocal() as db:
        print(json.dumps(import_pyqs(db, payload), ensure_ascii=False))


if __name__ == "__main__":
    main()
