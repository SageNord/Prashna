"""Profile ownership, learning activity, and Supabase row security."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_user_activity"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

def upgrade():
    bind=op.get_bind()
    article_columns={column["name"] for column in sa.inspect(bind).get_columns("articles")}
    # Existing demo databases predate content-processing metadata.
    additions=[
        sa.Column("prelims_points",sa.JSON(),nullable=True),sa.Column("mains_angles",sa.JSON(),nullable=True),
        sa.Column("processing_status",sa.String(20),nullable=False,server_default="COMPLETED"),
        sa.Column("processing_model",sa.String(100),nullable=True),sa.Column("processed_at",sa.DateTime(),nullable=True),
        sa.Column("processing_error",sa.Text(),nullable=True),sa.Column("raw_content",sa.Text(),nullable=True),
        sa.Column("content_hash",sa.String(64),nullable=True)]
    with op.batch_alter_table("articles") as batch:
        for column in additions:
            if column.name not in article_columns:batch.add_column(column)
    if "content_hash" not in article_columns:op.create_index("uq_articles_content_hash","articles",["content_hash"],unique=True)

    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE profiles ADD CONSTRAINT fk_profiles_auth_user FOREIGN KEY (id) REFERENCES auth.users(id) ON DELETE CASCADE")
        for table in ("profiles","user_bookmarks","user_quiz_attempts","daily_quiz_attempts","user_revisions","user_activity"):
            op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        policies={
            "profiles":"id",
            "user_bookmarks":"user_id",
            "user_quiz_attempts":"user_id",
            "daily_quiz_attempts":"user_id",
            "user_revisions":"user_id",
            "user_activity":"user_id",
        }
        for table,column in policies.items():
            op.execute(f'CREATE POLICY "{table}_self_access" ON "{table}" USING ({column}::uuid = auth.uid()) WITH CHECK ({column}::uuid = auth.uid())')

def downgrade():
    bind=op.get_bind()
    if bind.dialect.name=="postgresql":
        for table in ("profiles","user_bookmarks","user_quiz_attempts","daily_quiz_attempts","user_revisions","user_activity"):
            op.execute(f'DROP POLICY IF EXISTS "{table}_self_access" ON "{table}"')
            op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
        op.execute("ALTER TABLE profiles DROP CONSTRAINT IF EXISTS fk_profiles_auth_user")
