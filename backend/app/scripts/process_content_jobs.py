"""Discover local documents, register them through the existing pipeline, then process queued jobs."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from ..database import SessionLocal
from ..models import ContentIngestionJob, SourceDocument, SourceDocumentTopic, Subject, Topic
from ..services.content_pipeline import process_next_job, register_document

EXTENSIONS = {".pdf", ".txt", ".md"}
SUBJECT_FOLDERS = {
    "polity": "indian-polity", "science-tech": "science-technology",
    "environment": "environment-ecology", "art-culture": "art-culture",
}


def load_metadata(path: Path) -> dict:
    sidecar = path.with_suffix(path.suffix + ".meta.json")
    if not sidecar.exists():
        return {}
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Metadata must be a JSON object: {sidecar.name}")
    return data


def register_local_documents(db, content_root: Path) -> tuple[int, int, int]:
    registered = duplicates = skipped = 0
    if not content_root.exists():
        content_root.mkdir(parents=True, exist_ok=True)
        return registered, duplicates, skipped
    for path in sorted(p for p in content_root.rglob("*") if p.is_file() and p.suffix.lower() in EXTENSIONS):
        try:
            metadata = load_metadata(path)
            explicit_fields = set(metadata)
            relative = path.relative_to(content_root)
            folder = relative.parts[0] if len(relative.parts) > 1 else ""
            subject_slug = metadata.pop("subject_slug", SUBJECT_FOLDERS.get(folder, folder or None))
            topic_slug = metadata.pop("topic_slug", None)
            if topic_slug is None and len(relative.parts) > 2:
                topic_slug = re.sub(r"[^a-z0-9]+", "-", relative.parts[1].lower()).strip("-")
            subject = db.query(Subject).filter_by(slug=subject_slug).first() if subject_slug else None
            topic = db.query(Topic).filter_by(slug=topic_slug).first() if topic_slug else None
            if topic and subject and topic.subject_id != subject.id:
                raise ValueError("Topic does not belong to the selected subject")
            if topic and not subject:
                subject = topic.subject
            allowed = {"title", "publisher", "source_type", "source_url", "publication_year", "version", "license_notes"}
            unknown = set(metadata) - allowed
            if unknown:
                raise ValueError(f"Unsupported metadata fields: {', '.join(sorted(unknown))}")
            document, duplicate = register_document(db, title=metadata.get("title", path.stem.replace("_", " ").replace("-", " ").title()),
                publisher=metadata.get("publisher", "Unspecified — verify publisher"),
                source_type=metadata.get("source_type", "OTHER"), file_path=str(path),
                source_url=metadata.get("source_url"), subject_id=subject.id if subject else None,
                topic_id=topic.id if topic else None, publication_year=metadata.get("publication_year"),
                version=metadata.get("version"), license_notes=metadata.get("license_notes"))
            if duplicate:
                duplicates += 1
                if "title" in explicit_fields: document.title = metadata.get("title") or document.title
                if "publisher" in explicit_fields: document.publisher = metadata.get("publisher") or document.publisher
                if "source_type" in explicit_fields: document.source_type = metadata.get("source_type") or document.source_type
                if "source_url" in explicit_fields: document.source_url = metadata.get("source_url")
                if "publication_year" in explicit_fields: document.publication_year = metadata.get("publication_year")
                if "version" in explicit_fields: document.version = metadata.get("version")
                if "license_notes" in explicit_fields: document.license_notes = metadata.get("license_notes")
                if subject: document.subject_id = subject.id
                document.file_identifier = str(path)
                if topic and not db.query(SourceDocumentTopic).filter_by(document_id=document.id, topic_id=topic.id).first():
                    db.add(SourceDocumentTopic(document_id=document.id, topic_id=topic.id,
                        classification_method="MANUAL", confidence=1.0, review_status="APPROVED"))
                document.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                db.commit()
                print(f"DUPLICATE document_id={document.id} file={relative}")
            else:
                registered += 1
                print(f"QUEUED document_id={document.id} file={relative} subject={subject.slug if subject else 'unassigned'} topic={topic.slug if topic else 'unassigned'}")
        except Exception as exc:
            skipped += 1
            print(f"SKIPPED file={path.relative_to(content_root)} reason={type(exc).__name__}: {exc}")
    return registered, duplicates, skipped


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--content-dir", type=Path, default=Path(__file__).resolve().parents[2] / "content")
    parser.add_argument("--retry-failed", action="store_true", help="Requeue failed jobs after fixing the cause")
    args = parser.parse_args(argv)
    with SessionLocal() as db:
        registered, duplicates, skipped = register_local_documents(db, args.content_dir)
        if args.retry_failed:
            jobs = db.query(ContentIngestionJob).filter_by(status="FAILED").all()
            for job in jobs:
                job.status = "QUEUED"; job.phase = "QUEUED"; job.error_summary = None
                job.started_at = None; job.finished_at = None
                document = db.get(SourceDocument, job.document_id)
                if document: document.ingestion_status = "DRAFT"
            db.commit()
            print(f"REQUEUED failed_jobs={len(jobs)}")
        processed = 0
        while True:
            job = process_next_job(db)
            if job is None:
                break
            processed += 1
            suffix = f" error={job.error_summary}" if job.error_summary else ""
            print(f"JOB id={job.id} document_id={job.document_id} status={job.status} phase={job.phase}{suffix}")
        print(f"Finished registered={registered} duplicate_files={duplicates} skipped={skipped} jobs_processed={processed}")


if __name__ == "__main__":
    main()
