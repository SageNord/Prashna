"""Add the extensible UPSC learning catalog and user topic progress."""
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "0004_learning_catalog"
down_revision = "0003_current_affairs"
branch_labels = None
depends_on = None


SUBJECTS = [
    ("Current Affairs", "current-affairs", "Understand the context and syllabus links behind important developments.", "newspaper", "#416c52"),
    ("Indian Polity", "indian-polity", "Study the Constitution, institutions, rights, and governance of India.", "landmark", "#55745e"),
    ("History", "history", "Explore the people, movements, and processes that shaped the subcontinent.", "landmark", "#a46b43"),
    ("Geography", "geography", "Connect physical systems, places, resources, and human activity.", "globe-2", "#478b87"),
    ("Economy", "economy", "Build a clear foundation in the ideas and institutions of the Indian economy.", "chart-no-axes-combined", "#93703d"),
    ("Environment & Ecology", "environment-ecology", "Understand ecosystems, biodiversity, and environmental change.", "leaf", "#568359"),
    ("Science & Technology", "science-technology", "Study applications of science and technology in public life.", "atom", "#6877a2"),
    ("Art & Culture", "art-culture", "Explore India's artistic, architectural, and cultural traditions.", "palette", "#a05e72"),
    ("International Relations", "international-relations", "Understand India's external relations and global institutions.", "globe", "#5a789a"),
    ("Society", "society", "Examine social structure, inclusion, and change in India.", "users", "#98784b"),
    ("Governance", "governance", "Study public institutions, service delivery, and accountability.", "building-2", "#5a7c70"),
    ("Internal Security", "internal-security", "Explore security challenges, institutions, and resilience.", "shield", "#7c687e"),
    ("Ethics", "ethics", "Develop concepts and frameworks for ethical public service.", "scale", "#9a8050"),
    ("CSAT", "csat", "Practice the comprehension, reasoning, and numeracy skills used in CSAT.", "brain", "#667b9b"),
]

TOPICS = [
    ("indian-polity", "Constitution Basics", "constitution-basics", "The Constitution's structure, values, and framing.", 1),
    ("indian-polity", "Fundamental Rights", "fundamental-rights", "Rights guaranteed in Part III and their constitutional limits.", 2),
    ("indian-polity", "Directive Principles", "directive-principles", "Directive Principles in Part IV and their role in governance.", 3),
    ("indian-polity", "Parliament", "parliament", "The Union legislature, its houses, and core functions.", 4),
    ("history", "Revolt of 1857", "revolt-of-1857", "Causes, course, and consequences of the uprising of 1857.", 1),
    ("history", "Indian National Congress", "indian-national-congress", "The formation and early development of the national movement.", 2),
    ("history", "Gandhian Era", "gandhian-era", "Mass movements and political change in the Gandhian period.", 3),
    ("geography", "Indian Monsoon", "indian-monsoon", "Seasonal winds, rainfall patterns, and monsoon variability.", 1),
    ("geography", "Rivers of India", "rivers-of-india", "Major river systems and their geographic significance.", 2),
    ("geography", "Indian Physiography", "indian-physiography", "The major physical divisions of the Indian subcontinent.", 3),
    ("economy", "GDP", "gdp", "Output, value added, and the measurement of national income.", 1),
    ("economy", "Inflation", "inflation", "Price changes, measurement, causes, and distributional effects.", 2),
    ("economy", "Monetary Policy", "monetary-policy", "How monetary policy influences liquidity, prices, and activity.", 3),
    ("environment-ecology", "Ecosystems", "ecosystems", "Interactions between organisms and their physical environment.", 1),
    ("environment-ecology", "Biodiversity", "biodiversity", "The variety of life and approaches to its conservation.", 2),
    ("environment-ecology", "Climate Change", "climate-change", "Climate drivers, observed impacts, and response frameworks.", 3),
    ("science-technology", "Science in Everyday Life", "science-everyday-life", "A starting point for understanding applied science topics.", 1),
    ("art-culture", "Indian Architecture", "indian-architecture", "A starting point for India's architectural traditions.", 1),
    ("international-relations", "India and Global Institutions", "india-global-institutions", "A starting point for India's engagement with global institutions.", 1),
    ("society", "Social Diversity", "social-diversity", "A starting point for understanding India's social diversity.", 1),
    ("governance", "Accountability", "governance-accountability", "A starting point for accountability in public institutions.", 1),
    ("internal-security", "Security Foundations", "security-foundations", "A starting point for India's internal security landscape.", 1),
    ("ethics", "Ethics in Public Service", "ethics-public-service", "A starting point for ethical reasoning in public service.", 1),
    ("csat", "Reading Comprehension", "reading-comprehension", "A starting point for structured comprehension practice.", 1),
]

# These short samples demonstrate the content shape; they are not official UPSC material.
CONTENT = [
    ("indian-polity", "constitution-basics", "A first look at the Constitution", "A demo lesson on constitutional structure and values.", "## Core idea\nThe Constitution establishes institutions, distributes public power, and sets limits on its exercise.\n\n## Key connections\nThe Preamble states the Constitution's guiding commitments. The Union, states, legislature, executive, and judiciary operate within this constitutional framework.\n\n## Why it matters\nConstitutional principles help explain how institutions interact and how public authority is reviewed.\n\n## Demo material\nThis short sample is for product demonstration and is not official UPSC material.", 8),
    ("indian-polity", "fundamental-rights", "Fundamental Rights: the basic framework", "A demo lesson introducing Part III and rights-based constitutional review.", "## Core idea\nPart III of the Constitution contains Fundamental Rights. These rights protect important freedoms and equality interests.\n\n## Key connection\nArticles 12–35 cover the rights framework. Article 32 provides a constitutional remedy for enforcement of Fundamental Rights.\n\n## Common confusion\nRights are constitutionally protected, while their scope and permissible restrictions depend on the text and judicial interpretation.\n\n## Demo material\nThis short sample is for product demonstration and is not official UPSC material.", 10),
    ("history", "revolt-of-1857", "The Revolt of 1857: a starting framework", "A demo lesson for organizing causes, course, and consequences.", "## Core idea\nThe uprising of 1857 involved multiple regions and groups, with varied causes and outcomes.\n\n## Study lens\nOrganize revision around political, military, economic, and social factors; regional leadership; the course of events; and the changes that followed. Avoid reducing a complex event to a single cause.\n\n## Demo material\nThis short sample is for product demonstration and is not official UPSC material.", 9),
    ("geography", "indian-monsoon", "Understanding the Indian monsoon", "A demo lesson connecting seasonal circulation and rainfall distribution.", "## Core idea\nThe Indian monsoon is a seasonal reversal of winds associated with land–sea heating contrasts and broader atmospheric circulation.\n\n## Study lens\nConnect onset and withdrawal, regional rainfall differences, relief, ocean conditions, and variability. Monsoon rainfall is not uniform across India.\n\n## Demo material\nThis short sample is for product demonstration and is not official UPSC material.", 9),
    ("economy", "inflation", "Inflation: what to measure and why", "A demo lesson on sustained price increases and their effects.", "## Core idea\nInflation is a sustained rise in the general price level, reducing the purchasing power of money.\n\n## Study lens\nDistinguish a change in one price from a broad price-level change. Consider measurement, possible demand- and supply-side pressures, and effects on households, savers, and borrowers.\n\n## Demo material\nThis short sample is for product demonstration and is not official UPSC material.", 8),
    ("environment-ecology", "ecosystems", "Ecosystems: components and relationships", "A demo lesson on interactions between organisms and their environment.", "## Core idea\nAn ecosystem includes living communities and the non-living environment interacting as a system.\n\n## Study lens\nTrack energy flow, nutrient cycling, food relationships, and how disturbances can affect ecosystem structure and function.\n\n## Demo material\nThis short sample is for product demonstration and is not official UPSC material.", 8),
]


def _insert_if_missing(table, values, key="slug"):
    bind = op.get_bind()
    if bind.execute(sa.select(table.c.id).where(table.c[key] == values[key])).first() is None:
        bind.execute(table.insert().values(**values))


def upgrade():
    op.create_table(
        "subjects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("slug", sa.String(140), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("icon", sa.String(40), nullable=False),
        sa.Column("color", sa.String(24), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("slug", name="uq_subjects_slug"),
    )
    op.create_index("ix_subjects_active_order", "subjects", ["is_active", "display_order"])
    op.create_table(
        "topics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subject_id", sa.Integer(), sa.ForeignKey("subjects.id", name="fk_topics_subject_id_subjects", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_topic_id", sa.Integer(), sa.ForeignKey("topics.id", name="fk_topics_parent_topic_id_topics", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("slug", sa.String(180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("slug", name="uq_topics_slug"),
    )
    op.create_index("ix_topics_subject_order", "topics", ["subject_id", "display_order"])
    op.create_index("ix_topics_parent", "topics", ["parent_topic_id"])
    op.create_table(
        "learning_content",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subject_id", sa.Integer(), sa.ForeignKey("subjects.id", name="fk_learning_content_subject_id_subjects", ondelete="CASCADE"), nullable=False),
        sa.Column("topic_id", sa.Integer(), sa.ForeignKey("topics.id", name="fk_learning_content_topic_id_topics", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("slug", sa.String(260), nullable=False),
        sa.Column("content_type", sa.String(32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("difficulty", sa.String(24), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(200), nullable=False),
        sa.Column("source_url", sa.String(1000), nullable=True),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("slug", name="uq_learning_content_slug"),
    )
    op.create_index("ix_learning_content_topic_published", "learning_content", ["topic_id", "is_published"])
    op.create_index("ix_learning_content_subject_published", "learning_content", ["subject_id", "is_published"])
    op.create_table(
        "user_topic_progress",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=False), sa.ForeignKey("profiles.id", name="fk_user_topic_progress_user_id_profiles", ondelete="CASCADE"), nullable=False),
        sa.Column("topic_id", sa.Integer(), sa.ForeignKey("topics.id", name="fk_user_topic_progress_topic_id_topics", ondelete="CASCADE"), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "topic_id", name="uq_user_topic_progress_user_topic"),
    )
    op.create_index("ix_user_topic_progress_topic", "user_topic_progress", ["topic_id"])

    subjects = sa.table("subjects", sa.column("id", sa.Integer()), sa.column("name", sa.String()),
        sa.column("slug", sa.String()), sa.column("description", sa.Text()), sa.column("icon", sa.String()),
        sa.column("color", sa.String()), sa.column("display_order", sa.Integer()), sa.column("is_active", sa.Boolean()))
    topics = sa.table("topics", sa.column("id", sa.Integer()), sa.column("subject_id", sa.Integer()),
        sa.column("parent_topic_id", sa.Integer()), sa.column("name", sa.String()), sa.column("slug", sa.String()),
        sa.column("description", sa.Text()), sa.column("display_order", sa.Integer()), sa.column("is_active", sa.Boolean()))
    content = sa.table("learning_content", sa.column("id", sa.Integer()), sa.column("subject_id", sa.Integer()),
        sa.column("topic_id", sa.Integer()), sa.column("title", sa.String()), sa.column("slug", sa.String()),
        sa.column("content_type", sa.String()), sa.column("summary", sa.Text()), sa.column("body", sa.Text()),
        sa.column("difficulty", sa.String()), sa.column("estimated_minutes", sa.Integer()), sa.column("source", sa.String()),
        sa.column("source_url", sa.String()), sa.column("is_published", sa.Boolean()),
        sa.column("created_at", sa.DateTime()), sa.column("updated_at", sa.DateTime()))

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    subject_ids = {}
    for order, (name, slug, description, icon, color) in enumerate(SUBJECTS):
        _insert_if_missing(subjects, {"name": name, "slug": slug, "description": description, "icon": icon,
            "color": color, "display_order": order, "is_active": True})
        subject_ids[slug] = op.get_bind().execute(sa.select(subjects.c.id).where(subjects.c.slug == slug)).scalar_one()
    topic_ids = {}
    for subject_slug, name, slug, description, order in TOPICS:
        _insert_if_missing(topics, {"subject_id": subject_ids[subject_slug], "parent_topic_id": None,
            "name": name, "slug": slug, "description": description, "display_order": order, "is_active": True})
        topic_ids[slug] = op.get_bind().execute(sa.select(topics.c.id).where(topics.c.slug == slug)).scalar_one()
    for subject_slug, topic_slug, title, summary, body, minutes in CONTENT:
        _insert_if_missing(content, {"subject_id": subject_ids[subject_slug], "topic_id": topic_ids[topic_slug],
            "title": title, "slug": f"demo-{topic_slug}", "content_type": "LESSON", "summary": summary,
            "body": body, "difficulty": "FOUNDATION", "estimated_minutes": minutes,
            "source": "Prashna demo material", "source_url": None, "is_published": True,
            "created_at": now, "updated_at": now})


def downgrade():
    op.drop_index("ix_user_topic_progress_topic", table_name="user_topic_progress")
    op.drop_table("user_topic_progress")
    op.drop_index("ix_learning_content_subject_published", table_name="learning_content")
    op.drop_index("ix_learning_content_topic_published", table_name="learning_content")
    op.drop_table("learning_content")
    op.drop_index("ix_topics_parent", table_name="topics")
    op.drop_index("ix_topics_subject_order", table_name="topics")
    op.drop_table("topics")
    op.drop_index("ix_subjects_active_order", table_name="subjects")
    op.drop_table("subjects")
