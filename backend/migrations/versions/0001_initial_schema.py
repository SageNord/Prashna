"""Initial Prashna schema.

Revision ID: 0001_initial
"""
from alembic import op
from app.database import Base
from app import models  # noqa: F401

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Keep this historical revision frozen as the original schema. Models may
    # grow in later revisions; those tables must be created by their own
    # migration rather than appearing before Alembic reaches that revision.
    later_tables = {"subjects", "topics", "learning_content", "user_topic_progress"}
    Base.metadata.create_all(bind=op.get_bind(), tables=[
        table for table in Base.metadata.sorted_tables if table.name not in later_tables
    ])

def downgrade():
    Base.metadata.drop_all(bind=op.get_bind())
