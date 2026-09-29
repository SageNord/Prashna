from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, ForeignKey, Boolean, Integer, Date, JSON, UniqueConstraint, Index, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), default="Demo Aspirant")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (
        UniqueConstraint("content_hash", name="uq_articles_content_hash"),
        UniqueConstraint("canonical_url", name="uq_articles_canonical_url"),
        UniqueConstraint("event_fingerprint", name="uq_articles_event_fingerprint"),
        Index("ix_articles_published_at", "published_at"),
        Index("ix_articles_relevance_category", "relevance_category"),
        Index("ix_articles_ingestion_run_id", "ingestion_run_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(200), default="Prashna Editorial Learning Sample")
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    original_title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    source_identifier: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_priority: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    category: Mapped[str] = mapped_column(String(80))
    summary: Mapped[str] = mapped_column(Text)
    why_it_matters: Mapped[str] = mapped_column(Text)
    what_happened: Mapped[str] = mapped_column(Text, default="")
    background: Mapped[str] = mapped_column(Text, default="")
    upsc_relevance: Mapped[str] = mapped_column(Text, default="")
    prelims_points: Mapped[list] = mapped_column(JSON, default=list)
    mains_angles: Mapped[list] = mapped_column(JSON, default=list)
    important_terms: Mapped[list] = mapped_column(JSON, default=list)
    relevance_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    relevance_category: Mapped[str] = mapped_column(String(12), default="LOW", nullable=False)
    event_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ingestion_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("ingestion_runs.id", name="fk_articles_ingestion_run_id_ingestion_runs"),
        nullable=True,
    )
    processing_status: Mapped[str] = mapped_column(String(20), default="COMPLETED", index=True)
    processing_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    topics: Mapped[list["ArticleTopic"]] = relationship(cascade="all, delete-orphan")
    gs_tags: Mapped[list["ArticleGSTag"]] = relationship(cascade="all, delete-orphan")
    facts: Mapped[list["KeyFact"]] = relationship(cascade="all, delete-orphan")
    quiz_questions: Mapped[list["QuizQuestion"]] = relationship(cascade="all, delete-orphan")
    alternative_sources: Mapped[list["ArticleSource"]] = relationship(cascade="all, delete-orphan")

class ArticleSource(Base):
    """Additional primary/authoritative sources consolidated under one event."""
    __tablename__ = "article_sources"
    __table_args__ = (
        UniqueConstraint("article_id", "canonical_url", name="uq_article_source_url"),
        UniqueConstraint("source_url", name="uq_article_sources_source_url"),
        UniqueConstraint("canonical_url", name="uq_article_sources_canonical_url"),
        Index("ix_article_sources_article", "article_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), nullable=False)
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    source_identifier: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_priority: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    __table_args__ = (Index("ix_ingestion_runs_status", "status"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(40), default="scheduled", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sources_configured: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sources_succeeded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    candidates: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ignored: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deduplicated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    queued: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
class ArticleTopic(Base):
    __tablename__ = "article_topics"
    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), index=True)
    topic: Mapped[str] = mapped_column(String(150))
class ArticleGSTag(Base):
    __tablename__ = "article_gs_tags"
    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), index=True)
    gs_paper: Mapped[str] = mapped_column(String(30))
class KeyFact(Base):
    __tablename__ = "key_facts"
    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), index=True)
    fact: Mapped[str] = mapped_column(Text)
class QuizQuestion(Base):
    __tablename__ = "quiz_questions"
    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), index=True)
    question: Mapped[str] = mapped_column(Text)
    question_type: Mapped[str] = mapped_column(String(50), default="mcq")
    explanation: Mapped[str] = mapped_column(Text)
    options: Mapped[list["QuizOption"]] = relationship(cascade="all, delete-orphan")
class QuizOption(Base):
    __tablename__ = "quiz_options"
    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("quiz_questions.id", ondelete="CASCADE"), index=True)
    option_text: Mapped[str] = mapped_column(Text)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
class Bookmark(Base):
    __tablename__ = "bookmarks"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), default=1)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), default=1)
    question_id: Mapped[int] = mapped_column(ForeignKey("quiz_questions.id"))
    selected_option: Mapped[int] = mapped_column(ForeignKey("quiz_options.id"))
    is_correct: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
class Revision(Base):
    __tablename__ = "revisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), default=1)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"))
    difficulty: Mapped[str] = mapped_column(String(30), default="good")
    next_review_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    review_count: Mapped[int] = mapped_column(Integer, default=0)

# Supabase Auth owns identity. These rows only contain Prashna application data.
class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)  # Supabase Auth UUID
    display_name: Mapped[str] = mapped_column(String(120), default="")
    email: Mapped[str] = mapped_column(String(320), default="")
    avatar_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    target_exam: Mapped[str | None] = mapped_column(String(80), nullable=True)
    target_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preferred_subjects: Mapped[list] = mapped_column(JSON, default=list)
    onboarding_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    current_streak: Mapped[int] = mapped_column(Integer, default=0)
    longest_streak: Mapped[int] = mapped_column(Integer, default=0)
    last_activity_date: Mapped[object | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class UserBookmark(Base):
    __tablename__ = "user_bookmarks"
    __table_args__ = (UniqueConstraint("user_id", "article_id", name="uq_user_bookmark"), Index("ix_user_bookmarks_user", "user_id"))
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class UserQuizAttempt(Base):
    __tablename__ = "user_quiz_attempts"
    __table_args__ = (Index("ix_user_quiz_attempts_user_time", "user_id", "attempted_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    question_id: Mapped[int] = mapped_column(ForeignKey("quiz_questions.id", ondelete="CASCADE"), nullable=False)
    selected_option: Mapped[int] = mapped_column(ForeignKey("quiz_options.id"), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    activity_date: Mapped[object] = mapped_column(Date, nullable=False)
    attempted_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class DailyQuizAttempt(Base):
    __tablename__ = "daily_quiz_attempts"
    __table_args__ = (UniqueConstraint("user_id", "quiz_date", name="uq_daily_quiz_user_date"), Index("ix_daily_quiz_user_date", "user_id", "quiz_date"))
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    quiz_date: Mapped[object] = mapped_column(Date, nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    score: Mapped[int] = mapped_column(Integer, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class UserRevision(Base):
    __tablename__ = "user_revisions"
    __table_args__ = (UniqueConstraint("user_id", "article_id", name="uq_user_revision"), Index("ix_user_revisions_due", "user_id", "next_review_at"))
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(30), default="good")
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_review_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

class UserActivity(Base):
    __tablename__ = "user_activity"
    __table_args__ = (UniqueConstraint("user_id", "activity_type", "activity_date", name="uq_user_activity_type_date"), Index("ix_user_activity_user_date", "user_id", "activity_date"))
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    activity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    activity_date: Mapped[object] = mapped_column(Date, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class Subject(Base):
    __tablename__ = "subjects"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_subjects_slug"),
        Index("ix_subjects_active_order", "is_active", "display_order"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(140), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    icon: Mapped[str] = mapped_column(String(40), default="book-open", nullable=False)
    color: Mapped[str] = mapped_column(String(24), default="#416c52", nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    topics: Mapped[list["Topic"]] = relationship(back_populates="subject", cascade="all, delete-orphan")


class Topic(Base):
    __tablename__ = "topics"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_topics_slug"),
        Index("ix_topics_subject_order", "subject_id", "display_order"),
        Index("ix_topics_parent", "parent_topic_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    parent_topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), nullable=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    subject: Mapped[Subject] = relationship(back_populates="topics")
    parent: Mapped["Topic | None"] = relationship(remote_side="Topic.id", back_populates="children")
    children: Mapped[list["Topic"]] = relationship(back_populates="parent", cascade="all, delete-orphan")
    content: Mapped[list["LearningContent"]] = relationship(back_populates="topic", cascade="all, delete-orphan")


class LearningContent(Base):
    __tablename__ = "learning_content"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_learning_content_slug"),
        Index("ix_learning_content_topic_published", "topic_id", "is_published"),
        Index("ix_learning_content_subject_published", "subject_id", "is_published"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    slug: Mapped[str] = mapped_column(String(260), nullable=False)
    content_type: Mapped[str] = mapped_column(String(32), default="LESSON", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    difficulty: Mapped[str] = mapped_column(String(24), default="FOUNDATION", nullable=False)
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    source: Mapped[str] = mapped_column(String(200), default="Prashna demo material", nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    subject: Mapped[Subject] = relationship()
    topic: Mapped[Topic] = relationship(back_populates="content")


class UserTopicProgress(Base):
    __tablename__ = "user_topic_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "topic_id", name="uq_user_topic_progress_user_topic"),
        Index("ix_user_topic_progress_topic", "topic_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
