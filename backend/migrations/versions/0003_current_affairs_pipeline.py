"""Current-affairs provenance, event sources, and ingestion run tracking."""
from alembic import op
import sqlalchemy as sa
from app.database import Base
from app import models  # noqa: F401

revision = "0003_current_affairs"
down_revision = "0002_user_activity"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # On a fresh install the previous create_all-based first revision already
    # creates current metadata. On an existing installation, create only the
    # newly introduced tables before adding the Article reference column.
    Base.metadata.create_all(bind=bind)
    inspector = sa.inspect(bind)
    article_columns = {column["name"]: column for column in inspector.get_columns("articles")}
    additions = [
        sa.Column("original_title", sa.String(300), nullable=True),
        sa.Column("source_identifier", sa.String(1000), nullable=True),
        sa.Column("source_priority", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("canonical_url", sa.String(2048), nullable=True),
        sa.Column("ingested_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("what_happened", sa.Text(), nullable=True),
        sa.Column("background", sa.Text(), nullable=True),
        sa.Column("important_terms", sa.JSON(), nullable=True),
        sa.Column("relevance_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("relevance_category", sa.String(12), nullable=False, server_default="LOW"),
        sa.Column("event_fingerprint", sa.String(64), nullable=True),
        sa.Column("ingestion_run_id", sa.Integer(), sa.ForeignKey("ingestion_runs.id"), nullable=True),
    ]
    missing = [column for column in additions if column.name not in article_columns]
    if missing:
        with op.batch_alter_table("articles") as batch:
            for column in missing:
                batch.add_column(column)

    # RSS sources may legitimately omit their publication date. Preserve that
    # uncertainty instead of stamping an invented current timestamp.
    if article_columns.get("published_at", {}).get("nullable") is False:
        with op.batch_alter_table("articles") as batch:
            batch.alter_column("published_at", existing_type=sa.DateTime(), nullable=True)

    columns = {column["name"] for column in sa.inspect(bind).get_columns("articles")}
    if "original_title" in columns:
        op.execute("UPDATE articles SET original_title = title WHERE original_title IS NULL")
    if "what_happened" in columns:
        op.execute("UPDATE articles SET what_happened = summary WHERE what_happened IS NULL")
    op.execute("UPDATE articles SET relevance_score = 0, relevance_category = 'LOW', processing_status = 'SAMPLE' WHERE source = 'Prashna Editorial Learning Sample'")
    op.execute("UPDATE articles SET relevance_score = 50, relevance_category = 'MEDIUM' WHERE source_url IS NOT NULL AND source <> 'Prashna Editorial Learning Sample' AND relevance_score = 0")

    existing_indexes = {item["name"] for item in sa.inspect(bind).get_indexes("articles")}
    unique_columns = {tuple(item["column_names"]) for item in sa.inspect(bind).get_unique_constraints("articles")}
    if ("canonical_url",) not in unique_columns and "uq_articles_canonical_url" not in existing_indexes:
        op.create_index("uq_articles_canonical_url", "articles", ["canonical_url"], unique=True)
    if ("event_fingerprint",) not in unique_columns and "uq_articles_event_fingerprint" not in existing_indexes:
        op.create_index("uq_articles_event_fingerprint", "articles", ["event_fingerprint"], unique=True)
    if "ix_articles_relevance_category" not in existing_indexes:
        op.create_index("ix_articles_relevance_category", "articles", ["relevance_category"])
    if "ix_articles_published_at" not in existing_indexes:
        op.create_index("ix_articles_published_at", "articles", ["published_at"])
    if "ix_articles_ingestion_run_id" not in existing_indexes:
        op.create_index("ix_articles_ingestion_run_id", "articles", ["ingestion_run_id"])


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "articles" not in inspector.get_table_names():
        return
    indexes = {item["name"] for item in inspector.get_indexes("articles")}
    for name in ("ix_articles_ingestion_run_id", "ix_articles_published_at", "ix_articles_relevance_category"):
        if name in indexes:
            op.drop_index(name, table_name="articles")
    columns = {column["name"] for column in sa.inspect(bind).get_columns("articles")}
    remove = ("ingestion_run_id", "event_fingerprint", "relevance_category", "relevance_score", "important_terms", "background", "what_happened", "ingested_at", "source_priority", "canonical_url", "source_identifier", "original_title")
    present = [name for name in remove if name in columns]
    if present:
        with op.batch_alter_table("articles") as batch:
            for name in present:
                batch.drop_column(name)
    for table in ("article_sources", "ingestion_runs"):
        if table in sa.inspect(bind).get_table_names():
            op.drop_table(table)
