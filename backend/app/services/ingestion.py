"""Idempotent source collection, deduplication, screening, and preprocessing."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import re
from threading import Lock
import time

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import (Article, ArticleGSTag, ArticleSource, ArticleTopic, IngestionRun,
                      KeyFact, QuizOption, QuizQuestion)
from .llm import MockProvider, get_provider, process_with_retry
from .relevance import classify_relevance, event_fingerprint, title_similarity, utc_naive
from .sources import FeedSource, RawArticle, canonicalize_url, configured_sources, fetch_feed

log = logging.getLogger("prashna.ingestion")
_run_lock = Lock()
MAX_CANDIDATES_PER_SOURCE = 40
MAX_PROCESSED_PER_RUN = 30


def _safe_source_error(error: Exception) -> str:
    """Keep actionable source errors while stripping URLs and credential-like values."""
    message = str(error) or type(error).__name__
    message = re.sub(r"https?://[^\s\]\[()]+", "[url]", message, flags=re.IGNORECASE)
    message = re.sub(
        r"(?i)\b(authorization|token|secret|password|api[_-]?key)\b\s*([=:])\s*[^\s&,;]+",
        r"\1\2[redacted]",
        message,
    )
    return message[:240]


def _add_alternative_source(db: Session, article: Article, raw: RawArticle, priority: int) -> bool:
    if raw.url == (article.canonical_url or article.source_url):
        return False
    exists = db.query(ArticleSource).filter(ArticleSource.canonical_url == raw.url).first()
    if exists:
        return False
    # Some pre-pipeline rows do not have canonical_url populated.
    if db.query(Article).filter(Article.source_url == raw.url).first():
        return False
    db.add(ArticleSource(article_id=article.id, source_name=raw.source, source_url=raw.url,
                         canonical_url=raw.url, source_identifier=raw.source_identifier,
                         published_at=utc_naive(raw.published_at), source_priority=priority))
    return True


def _find_duplicate(db: Session, raw: RawArticle) -> Article | None:
    article = db.query(Article).filter(or_(Article.canonical_url == raw.url, Article.source_url == raw.url)).first()
    if article:
        return article
    fingerprint = event_fingerprint(raw.title, raw.published_at)
    article = db.query(Article).filter(Article.event_fingerprint == fingerprint).first()
    if article:
        return article
    if raw.published_at:
        published = utc_naive(raw.published_at)
        lower, upper = published - timedelta(days=2), published + timedelta(days=2)
        nearby = db.query(Article).filter(Article.published_at.between(lower, upper),
                                          Article.processing_status != "SAMPLE",
                                          Article.source_url.is_not(None)).order_by(Article.relevance_score.desc()).limit(100).all()
        for candidate in nearby:
            if title_similarity(raw.title, candidate.original_title or candidate.title) >= 0.86:
                return candidate
    return None


def store_candidate(db: Session, raw: RawArticle, priority: int, run_id: int) -> str:
    """Return inserted, ignored, duplicate, requeued, or failed_duplicate."""
    canonical = canonicalize_url(raw.url)
    raw = RawArticle(raw.title.strip()[:300], canonical, raw.source[:200], raw.source_identifier,
                     raw.published_at, raw.summary[:12000])
    score, relevance, category = classify_relevance(raw.title, raw.summary)
    duplicate = _find_duplicate(db, raw)
    fingerprint = event_fingerprint(raw.title, raw.published_at)
    if duplicate:
        if duplicate.relevance_category == "LOW" and relevance != "LOW":
            duplicate.relevance_score, duplicate.relevance_category = score, relevance
            duplicate.category = category or duplicate.category
            duplicate.what_happened = raw.summary or duplicate.what_happened
            duplicate.raw_content = raw.summary or duplicate.raw_content
            duplicate.processing_status = "PENDING"
            duplicate.ingestion_run_id = run_id
        added_source = _add_alternative_source(db, duplicate, raw, priority)
        if priority > duplicate.source_priority:
            # Keep the previous attribution before promoting the authoritative source.
            old = RawArticle(duplicate.original_title or duplicate.title, duplicate.canonical_url or duplicate.source_url,
                             duplicate.source, duplicate.source_identifier, duplicate.published_at,
                             duplicate.raw_content or duplicate.summary)
            _add_alternative_source(db, duplicate, old, duplicate.source_priority)
            duplicate.title = raw.title
            duplicate.original_title = raw.title
            duplicate.source = raw.source
            duplicate.source_url = raw.url
            duplicate.canonical_url = raw.url
            duplicate.source_identifier = raw.source_identifier
            duplicate.source_priority = priority
            duplicate.published_at = utc_naive(raw.published_at)
            duplicate.raw_content = raw.summary
            duplicate.what_happened = raw.summary
            duplicate.processing_status = "PENDING" if relevance != "LOW" else "IGNORED"
            duplicate.relevance_score, duplicate.relevance_category = score, relevance
            duplicate.category = category or duplicate.category
            duplicate.ingestion_run_id = run_id
        if duplicate.processing_status == "FAILED" and relevance != "LOW":
            duplicate.processing_status = "PENDING"
            duplicate.processing_error = None
            duplicate.ingestion_run_id = run_id
            return "requeued"
        return "duplicate" if added_source or duplicate else "duplicate"

    status = "IGNORED" if relevance == "LOW" else "PENDING"
    article = Article(title=raw.title, original_title=raw.title, source=raw.source,
                      source_url=raw.url, canonical_url=raw.url,
                      source_identifier=raw.source_identifier, source_priority=priority,
                      published_at=utc_naive(raw.published_at),
                      ingested_at=datetime.now(timezone.utc).replace(tzinfo=None),
                      category=category or "Unclassified", summary=raw.summary or raw.title,
                      what_happened=raw.summary or raw.title,
                      why_it_matters="", background="", upsc_relevance="",
                      raw_content=raw.summary or raw.title, event_fingerprint=fingerprint,
                      relevance_score=score, relevance_category=relevance,
                      processing_status=status, ingestion_run_id=run_id)
    db.add(article)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return "duplicate"
    return "ignored" if status == "IGNORED" else "inserted"


def process_stored_article(db: Session, article: Article) -> bool:
    if article.processing_status == "COMPLETED":
        return True
    if article.relevance_category == "LOW" or not article.source_url:
        article.processing_status = "IGNORED"
        db.commit()
        return False
    article.processing_status = "PROCESSING"
    article.processing_error = None
    db.commit()
    provider = get_provider()
    content = "\n".join(part for part in (article.original_title or article.title, article.raw_content or article.summary) if part)
    try:
        try:
            result = process_with_retry(provider, article.original_title or article.title, article.source, content)
        except Exception as exc:
            log.warning("AI processing failed for article_id=%s error_type=%s; using source-only fallback", article.id, type(exc).__name__)
            provider = MockProvider()
            result = provider.process(article.original_title or article.title, article.source, content)
        article.title = str(result.get("title") or article.original_title or article.title)[:300]
        article.summary = str(result.get("summary") or article.raw_content or article.original_title or article.title)[:6000]
        article.what_happened = str(result.get("what_happened") or article.raw_content or article.original_title or article.title)[:6000]
        article.why_it_matters = str(result.get("why_it_matters") or "")[:6000]
        article.background = str(result.get("background") or "")[:6000]
        article.upsc_relevance = str(result.get("upsc_relevance") or "")[:2000]
        article.prelims_points = _string_items(result.get("prelims_points"), 12, 1000)
        article.mains_angles = _string_items(result.get("mains_angles"), 8, 1500)
        article.important_terms = _string_items(result.get("important_terms"), 16, 120)
        article.topics = [ArticleTopic(topic=x) for x in _string_items(result.get("topics"), 20, 150)]
        article.gs_tags = [ArticleGSTag(gs_paper=x) for x in _string_items(result.get("gs_papers"), 8, 30)]
        article.facts = [KeyFact(fact=x) for x in _string_items(result.get("key_facts"), 12, 2000)]
        article.quiz_questions = _quiz_questions(article.id, result.get("quiz_questions"))
        article.processing_model = provider.name
        article.processed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        article.processing_status = "COMPLETED"
        # Preserve raw publisher material for audit and retry; user feed uses the processed fields.
        db.commit()
        return True
    except Exception as exc:
        db.rollback()
        article = db.get(Article, article.id)
        if article:
            article.processing_status = "FAILED"
            article.processing_error = type(exc).__name__
            db.commit()
        log.exception("Article processing failed article_id=%s error_type=%s", article.id, type(exc).__name__)
        return False


def _string_items(value: object, maximum: int, length: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip()[:length] for item in value[:maximum] if str(item).strip()]


def _quiz_questions(article_id: int, value: object) -> list[QuizQuestion]:
    if not isinstance(value, list):
        return []
    questions: list[QuizQuestion] = []
    for item in value[:4]:
        if not isinstance(item, dict):
            continue
        options = item.get("options")
        answer = item.get("answer_index")
        question_text = str(item.get("question") or "").strip()
        if not question_text or not isinstance(options, list) or len(options) < 2 or not isinstance(answer, int) or answer < 0 or answer >= len(options):
            continue
        row = QuizQuestion(article_id=article_id, question=question_text[:2000],
                           question_type="mcq", explanation=str(item.get("explanation") or "")[:2000])
        row.options = [QuizOption(option_text=str(option).strip()[:1000], is_correct=(index == answer))
                       for index, option in enumerate(options[:4]) if str(option).strip()]
        if len(row.options) >= 2 and row.options[answer].is_correct:
            questions.append(row)
    return questions


def run_ingestion(run_id: int, session_factory=None) -> None:
    """Background-safe scheduled ingestion; separate from user page requests."""
    session_factory = session_factory or SessionLocal
    if not _run_lock.acquire(blocking=False):
        log.warning("Ingestion run %s skipped because another run is active", run_id)
        with session_factory() as db:
            run = db.get(IngestionRun, run_id)
            if run:
                run.status = "FAILED"
                run.errors = ["Another ingestion run is already active."]
                run.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
                db.commit()
        return
    started = time.monotonic()
    db = session_factory()
    try:
        run = db.get(IngestionRun, run_id)
        if not run:
            return
        run.status = "PROCESSING"
        run.started_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
        log.info("Ingestion run started run_id=%s", run_id)
        sources = configured_sources()
        run.sources_configured = len(sources)
        candidates: list[tuple[RawArticle, FeedSource]] = []
        errors: list[str] = []
        for source in sources:
            try:
                rows = fetch_feed(source, limit=MAX_CANDIDATES_PER_SOURCE)
                run.sources_succeeded += 1
                candidates.extend((item, source) for item in rows)
                log.info("Ingestion source fetched run_id=%s source=%s candidates=%s", run_id, source.name, len(rows))
            except Exception as exc:
                detail = _safe_source_error(exc)
                errors.append(f"{source.name}: {detail}")
                log.warning("Ingestion source failed run_id=%s source=%s reason=%s", run_id, source.name, detail)
        run.candidates = len(candidates)
        db.commit()
        for raw, source in candidates:
            try:
                result = store_candidate(db, raw, source.priority, run_id)
                if result == "ignored":
                    run.ignored += 1
                elif result in {"duplicate", "requeued"}:
                    run.deduplicated += int(result == "duplicate")
                db.commit()
            except Exception as exc:
                db.rollback()
                errors.append(f"Candidate rejected: {type(exc).__name__}")
                run = db.get(IngestionRun, run_id)
                run.failed += 1
                db.commit()
        pending = db.query(Article).filter(Article.processing_status.in_(["PENDING", "FAILED"]),
                                            Article.relevance_category.in_(["HIGH", "MEDIUM"]),
                                            Article.source_url.is_not(None)).order_by(Article.relevance_score.desc(), Article.published_at.desc().nullslast()).limit(MAX_PROCESSED_PER_RUN).all()
        run.queued = max(0, db.query(Article).filter(Article.processing_status == "PENDING", Article.relevance_category.in_(["HIGH", "MEDIUM"])).count() - len(pending))
        db.commit()
        for article in pending:
            if process_stored_article(db, article):
                run.processed += 1
            else:
                run.failed += 1
            db.commit()
        run = db.get(IngestionRun, run_id)
        run.errors = (run.errors or []) + errors[:40]
        run.status = "PARTIAL" if errors or run.failed else "COMPLETED"
        run.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
        run.duration_ms = int((time.monotonic() - started) * 1000)
        db.commit()
        log.info("Ingestion run finished run_id=%s sources=%s candidates=%s ignored=%s deduplicated=%s processed=%s failed=%s queued=%s duration_ms=%s",
                 run_id, run.sources_succeeded, run.candidates, run.ignored, run.deduplicated, run.processed, run.failed, run.queued, run.duration_ms)
    except Exception as exc:
        db.rollback()
        run = db.get(IngestionRun, run_id)
        if run:
            run.status = "FAILED"
            run.errors = (run.errors or []) + [f"Run failed: {type(exc).__name__}"]
            run.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
            run.duration_ms = int((time.monotonic() - started) * 1000)
            db.commit()
        log.exception("Ingestion run failed run_id=%s error_type=%s", run_id, type(exc).__name__)
    finally:
        db.close()
        _run_lock.release()
