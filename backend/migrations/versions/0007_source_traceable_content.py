"""Source provenance, reviewable ingestion jobs, learning cards and PYQ metadata."""
from alembic import op
import sqlalchemy as sa

revision = "0007_source_traceable_content"
down_revision = "0006_learning_progress"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "source_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("publisher", sa.String(200), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=True),
        sa.Column("source_url", sa.String(2048), nullable=True),
        sa.Column("file_identifier", sa.String(500), nullable=True),
        sa.Column("publication_year", sa.Integer(), nullable=True),
        sa.Column("version", sa.String(120), nullable=True),
        sa.Column("license_notes", sa.Text(), nullable=True),
        sa.Column("checksum", sa.String(64), nullable=True),
        sa.Column("ingestion_status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], name="fk_source_documents_subject_id_subjects"),
        sa.UniqueConstraint("checksum", name="uq_source_documents_checksum"),
    )
    op.create_index("ix_source_documents_status", "source_documents", ["ingestion_status"])
    op.create_table(
        "source_document_topics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), nullable=False), sa.Column("topic_id", sa.Integer(), nullable=False),
        sa.Column("classification_method", sa.String(20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True), sa.Column("review_status", sa.String(20), nullable=False, server_default="REVIEW"),
        sa.ForeignKeyConstraint(["document_id"], ["source_documents.id"], name="fk_source_document_topics_document_id_source_documents", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], name="fk_source_document_topics_topic_id_topics", ondelete="CASCADE"),
        sa.UniqueConstraint("document_id", "topic_id", name="uq_source_document_topics_pair"),
    )
    op.create_index("ix_source_document_topics_topic", "source_document_topics", ["topic_id"])
    op.create_table(
        "source_chunks",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("topic_id", sa.Integer(), nullable=True), sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("section", sa.String(300), nullable=True), sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False), sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["source_documents.id"], name="fk_source_chunks_document_id_source_documents", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], name="fk_source_chunks_topic_id_topics"),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_source_chunks_document_index"),
    )
    op.create_index("ix_source_chunks_topic", "source_chunks", ["topic_id"])
    op.create_table(
        "content_ingestion_jobs",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="QUEUED"),
        sa.Column("phase", sa.String(40), nullable=False, server_default="QUEUED"), sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("queued_at", sa.DateTime(), nullable=False), sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["source_documents.id"], name="fk_content_ingestion_jobs_document_id_source_documents", ondelete="CASCADE"),
    )
    op.create_index("ix_content_ingestion_jobs_status", "content_ingestion_jobs", ["status"])
    op.create_table(
        "learning_cards", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("topic_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(240), nullable=False), sa.Column("slug", sa.String(260), nullable=False),
        sa.Column("content", sa.Text(), nullable=False), sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="REVIEW"),
        sa.Column("content_origin", sa.String(24), nullable=False, server_default="PRASHNA_SUMMARY"),
        sa.Column("classification_method", sa.String(20), nullable=False, server_default="MANUAL"),
        sa.Column("classification_confidence", sa.Float(), nullable=True), sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], name="fk_learning_cards_topic_id_topics", ondelete="CASCADE"),
        sa.UniqueConstraint("slug", name="uq_learning_cards_slug"),
    )
    op.create_index("ix_learning_cards_topic_status_order", "learning_cards", ["topic_id", "status", "display_order"])
    op.create_table(
        "learning_card_source_refs", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("card_id", sa.Integer(), nullable=False), sa.Column("source_chunk_id", sa.Integer(), nullable=False),
        sa.Column("reference_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attribution_note", sa.String(500), nullable=True),
        sa.ForeignKeyConstraint(["card_id"], ["learning_cards.id"], name="fk_learning_card_source_refs_card_id_learning_cards", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_chunk_id"], ["source_chunks.id"], name="fk_learning_card_source_refs_source_chunk_id_source_chunks", ondelete="RESTRICT"),
        sa.UniqueConstraint("card_id", "source_chunk_id", name="uq_learning_card_source_refs_pair"),
    )
    op.create_index("ix_learning_card_source_refs_card_order", "learning_card_source_refs", ["card_id", "reference_order"])
    with op.batch_alter_table("questions") as batch:
        batch.add_column(sa.Column("source_type", sa.String(24), nullable=False, server_default="SAMPLE"))
        batch.add_column(sa.Column("year", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("exam", sa.String(120), nullable=True))
        batch.add_column(sa.Column("stage", sa.String(80), nullable=True))
        batch.add_column(sa.Column("paper", sa.String(120), nullable=True))
        batch.add_column(sa.Column("question_number", sa.String(40), nullable=True))
        batch.add_column(sa.Column("source_document_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("status", sa.String(20), nullable=False, server_default="PUBLISHED"))
        batch.add_column(sa.Column("classification_method", sa.String(20), nullable=False, server_default="MANUAL"))
        batch.add_column(sa.Column("classification_confidence", sa.Float(), nullable=True))
        batch.create_foreign_key("fk_questions_source_document_id_source_documents", "source_documents", ["source_document_id"], ["id"])
    op.create_index("ix_questions_pyq_metadata", "questions", ["source_type", "year", "exam", "stage", "paper", "question_number"], unique=True)
    op.create_table(
        "question_topic_classifications",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("topic_id", sa.Integer(), nullable=False), sa.Column("classification_method", sa.String(20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True), sa.Column("review_status", sa.String(20), nullable=False, server_default="REVIEW"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], name="fk_question_topic_classifications_question_id_questions", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], name="fk_question_topic_classifications_topic_id_topics", ondelete="CASCADE"),
        sa.UniqueConstraint("question_id", "topic_id", name="uq_question_topic_classifications_pair"),
    )
    op.create_index("ix_question_topic_classifications_topic", "question_topic_classifications", ["topic_id"])


def downgrade():
    op.drop_index("ix_question_topic_classifications_topic", table_name="question_topic_classifications")
    op.drop_table("question_topic_classifications")
    op.drop_index("ix_questions_pyq_metadata", table_name="questions")
    with op.batch_alter_table("questions") as batch:
        batch.drop_constraint("fk_questions_source_document_id_source_documents", type_="foreignkey")
        for col in ("classification_confidence", "classification_method", "status", "source_document_id", "question_number", "paper", "stage", "exam", "year", "source_type"):
            batch.drop_column(col)
    for table, indexes in (("learning_card_source_refs", ["ix_learning_card_source_refs_card_order"]),
                           ("learning_cards", ["ix_learning_cards_topic_status_order"]),
                           ("content_ingestion_jobs", ["ix_content_ingestion_jobs_status"]),
                           ("source_chunks", ["ix_source_chunks_topic"]),
                           ("source_document_topics", ["ix_source_document_topics_topic"]),
                           ("source_documents", ["ix_source_documents_status"])):
        for index in indexes: op.drop_index(index, table_name=table)
    for table in ("learning_card_source_refs", "learning_cards", "content_ingestion_jobs", "source_chunks", "source_document_topics", "source_documents"):
        op.drop_table(table)
