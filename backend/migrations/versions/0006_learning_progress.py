"""Track completion of topic reading material."""
from alembic import op
import sqlalchemy as sa

revision = "0006_learning_progress"
down_revision = "0005_mcq_practice"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user_topic_progress", sa.Column("reading_completed_at", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("user_topic_progress", "reading_completed_at")
