"""Add topic MCQs and user-owned question attempts."""
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "0005_mcq_practice"
down_revision = "0004_learning_catalog"
branch_labels = None
depends_on = None


# Demonstration questions written for Prashna's sample catalog. They are not
# official UPSC questions and are not presented as previous-year questions.
DEMO_QUESTIONS = [
    ("constitution-basics", "On which date did the Constituent Assembly adopt the Constitution of India?", "EASY", "The Constituent Assembly adopted the Constitution on 26 November 1949. It came into force on 26 January 1950.", [
        ("26 November 1949", True), ("15 August 1947", False), ("26 January 1950", False), ("9 December 1946", False)]),
    ("constitution-basics", "When did the Constitution of India come into force?", "EASY", "The Constitution came into force on 26 January 1950. The date was chosen to honour the 1930 declaration of Purna Swaraj.", [
        ("26 January 1950", True), ("26 November 1949", False), ("15 August 1947", False), ("2 October 1950", False)]),
    ("constitution-basics", "Which body adopted the Constitution of India?", "EASY", "The Constituent Assembly adopted the Constitution after deliberation and debate.", [
        ("The Constituent Assembly", True), ("The first Lok Sabha", False), ("The Federal Court", False), ("The Council of States", False)]),
    ("constitution-basics", "Who chaired the Drafting Committee of the Constituent Assembly?", "MEDIUM", "Dr B. R. Ambedkar chaired the Drafting Committee, which was established in August 1947.", [
        ("Dr B. R. Ambedkar", True), ("Dr Rajendra Prasad", False), ("Jawaharlal Nehru", False), ("Sardar Vallabhbhai Patel", False)]),
    ("constitution-basics", "Which phrase begins the Preamble to the Constitution of India?", "EASY", "The Preamble begins with “We, the People of India”, expressing popular sovereignty.", [
        ("We, the People of India", True), ("The Parliament of India", False), ("The Union of States", False), ("The citizens and the states", False)]),

    ("fundamental-rights", "Which Part of the Constitution contains the Fundamental Rights?", "EASY", "Fundamental Rights are contained in Part III of the Constitution, broadly covering Articles 12 to 35.", [
        ("Part III", True), ("Part II", False), ("Part IV", False), ("Part IVA", False)]),
    ("fundamental-rights", "Article 14 guarantees which principle?", "EASY", "Article 14 guarantees equality before the law and equal protection of the laws.", [
        ("Equality before law and equal protection of laws", True), ("Freedom of religion only", False), ("Protection against double jeopardy only", False), ("A right to property as a Fundamental Right", False)]),
    ("fundamental-rights", "Which Article is associated with the right to constitutional remedies?", "MEDIUM", "Article 32 allows people to move the Supreme Court for enforcement of Fundamental Rights.", [
        ("Article 32", True), ("Article 19", False), ("Article 21A", False), ("Article 40", False)]),
    ("fundamental-rights", "The abolition of untouchability is provided under which Article?", "EASY", "Article 17 abolishes untouchability and forbids its practice in any form.", [
        ("Article 17", True), ("Article 14", False), ("Article 23", False), ("Article 29", False)]),
    ("fundamental-rights", "The Directive Principles of State Policy are primarily contained in which Part?", "MEDIUM", "The Directive Principles of State Policy are contained in Part IV; they are distinct from the Fundamental Rights in Part III.", [
        ("Part IV", True), ("Part III", False), ("Part V", False), ("Part IVA", False)]),

    ("revolt-of-1857", "At which place did the major uprising of 1857 begin on 10 May?", "EASY", "The uprising began at Meerut on 10 May 1857 before spreading to Delhi and other centres.", [
        ("Meerut", True), ("Kanpur", False), ("Jhansi", False), ("Lucknow", False)]),
    ("revolt-of-1857", "Which issue is commonly identified as the immediate trigger for the 1857 uprising?", "EASY", "The introduction of rifle cartridges believed to be greased with cow and pig fat became the immediate trigger among sepoys.", [
        ("The cartridge controversy", True), ("The Ilbert Bill", False), ("The partition of Bengal", False), ("The Vernacular Press Act", False)]),
    ("revolt-of-1857", "Who was proclaimed the symbolic emperor by the rebels at Delhi in 1857?", "MEDIUM", "The rebels proclaimed the Mughal emperor Bahadur Shah Zafar as their symbolic sovereign.", [
        ("Bahadur Shah Zafar", True), ("Akbar II", False), ("Nana Saheb", False), ("Wajid Ali Shah", False)]),
    ("revolt-of-1857", "Which leader was associated with the uprising at Kanpur?", "MEDIUM", "Nana Saheb emerged as a prominent leader of the uprising at Kanpur.", [
        ("Nana Saheb", True), ("Kunwar Singh", False), ("Khan Bahadur Khan", False), ("Bakht Khan", False)]),
    ("revolt-of-1857", "Which leader became a prominent symbol of resistance at Jhansi?", "EASY", "Rani Lakshmibai led resistance at Jhansi and became one of the best-known figures of the uprising.", [
        ("Rani Lakshmibai", True), ("Begum Hazrat Mahal", False), ("Rani Durgavati", False), ("Annie Besant", False)]),

    ("indian-monsoon", "The southwest monsoon reaches India through which two principal branches?", "EASY", "The Arabian Sea branch and the Bay of Bengal branch are the two principal branches of the southwest monsoon.", [
        ("Arabian Sea and Bay of Bengal branches", True), ("Red Sea and Persian Gulf branches", False), ("Western and eastern jet branches", False), ("Himalayan and Deccan branches", False)]),
    ("indian-monsoon", "Which period broadly corresponds to the southwest monsoon season over most of India?", "EASY", "The southwest monsoon broadly occurs from June to September, though onset and withdrawal vary by region and year.", [
        ("June to September", True), ("January to March", False), ("October to December only", False), ("February to May", False)]),
    ("indian-monsoon", "Why does the windward side of the Western Ghats receive heavy orographic rainfall?", "MEDIUM", "Moist monsoon air is forced to rise along the Western Ghats, cools, and condenses, producing orographic rainfall on windward slopes.", [
        ("Moist air is forced to rise over the mountains", True), ("The region lies beyond the rain shadow", False), ("Cold ocean currents remove all moisture", False), ("The Himalayas divert every rain-bearing wind westward", False)]),
    ("indian-monsoon", "Tamil Nadu receives a substantial share of its rainfall during which season?", "MEDIUM", "The northeast or retreating monsoon, especially during October to December, is important for rainfall in Tamil Nadu.", [
        ("Northeast monsoon season", True), ("Winter western disturbances only", False), ("Southwest monsoon exclusively in June", False), ("Pre-monsoon season only", False)]),
    ("indian-monsoon", "Which statement best describes monsoon rainfall across India?", "MEDIUM", "Monsoon rainfall varies across regions and years due to circulation, relief, ocean-atmosphere conditions, and other factors.", [
        ("It varies across regions and from year to year", True), ("It is uniform in every state", False), ("It occurs only along the coast", False), ("It is unaffected by topography", False)]),

    ("inflation", "In economics, inflation generally refers to which change?", "EASY", "Inflation is a sustained increase in the general price level, rather than a one-time change in one item’s price.", [
        ("A sustained increase in the general price level", True), ("A fall in the price of one product", False), ("An increase in real output alone", False), ("A rise in the exchange rate alone", False)]),
    ("inflation", "India's Consumer Price Index is compiled by which institution?", "MEDIUM", "The National Statistical Office compiles the Consumer Price Index. The CPI is widely used to measure retail inflation.", [
        ("National Statistical Office", True), ("Reserve Bank of India", False), ("Finance Commission", False), ("NITI Aayog", False)]),
    ("inflation", "A rise in the price of one commodity, by itself, necessarily proves that economy-wide inflation has risen.", "MEDIUM", "A single price can change without a broad increase in the general price level. Inflation measures broader price movements.", [
        ("No; inflation concerns a broad, sustained price-level change", True), ("Yes; any price change is inflation", False), ("Yes, but only for imported goods", False), ("No; inflation means only falling prices", False)]),
    ("inflation", "A poor harvest that reduces food supply is an example of what kind of inflationary pressure?", "MEDIUM", "A supply shortfall can raise food prices and contribute to supply-side inflationary pressure.", [
        ("Supply-side pressure", True), ("A fall in aggregate demand", False), ("A productivity increase", False), ("A reduction in indirect taxes", False)]),
    ("inflation", "Which index is designed to track changes in prices faced by households for a basket of goods and services?", "EASY", "The Consumer Price Index tracks changes in prices of a representative basket consumed by households.", [
        ("Consumer Price Index", True), ("Index of Industrial Production", False), ("Wholesale trade balance", False), ("Fiscal deficit ratio", False)]),

    ("ecosystems", "An ecosystem consists of which elements interacting with one another?", "EASY", "An ecosystem includes a community of organisms and the physical environment with which they interact.", [
        ("Organisms and their physical environment", True), ("Only plants in a region", False), ("Only climate and soil", False), ("Only top-level consumers", False)]),
    ("ecosystems", "Which organisms are generally described as primary producers in an ecosystem?", "EASY", "Primary producers, such as green plants, use photosynthesis to convert light energy into chemical energy.", [
        ("Organisms that make organic matter from inorganic sources", True), ("Organisms that feed only on carnivores", False), ("Organisms that consume dead matter only", False), ("Organisms that do not need energy", False)]),
    ("ecosystems", "How does energy generally move through trophic levels in an ecosystem?", "MEDIUM", "Energy flows through trophic levels and much of it is dissipated as heat at each transfer; it is not recycled like nutrients.", [
        ("It flows in one direction, with losses at transfers", True), ("It cycles completely like mineral nutrients", False), ("It increases at every trophic level", False), ("It moves only from consumers to the Sun", False)]),
    ("ecosystems", "What is an important ecological role of decomposers?", "EASY", "Decomposers break down dead organic matter and help return nutrients to the ecosystem.", [
        ("Breaking down organic matter and recycling nutrients", True), ("Stopping all nutrient movement", False), ("Producing sunlight", False), ("Preventing primary production", False)]),
    ("ecosystems", "Which example best illustrates a biotic component of an ecosystem?", "EASY", "Biotic components are living organisms; soil, water, and sunlight are abiotic components.", [
        ("A population of grasses", True), ("Sunlight", False), ("Soil minerals", False), ("Air temperature", False)]),
]


def upgrade():
    op.create_table(
        "questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("topic_id", sa.Integer(), sa.ForeignKey("topics.id", name="fk_questions_topic_id_topics", ondelete="CASCADE"), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("difficulty", sa.String(16), nullable=False),
        sa.Column("question_type", sa.String(16), nullable=False),
        sa.Column("source", sa.String(200), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_questions_topic_published", "questions", ["topic_id", "is_published"])
    op.create_index("ix_questions_type_difficulty", "questions", ["question_type", "difficulty"])
    op.create_table(
        "question_options",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("question_id", sa.Integer(), sa.ForeignKey("questions.id", name="fk_question_options_question_id_questions", ondelete="CASCADE"), nullable=False),
        sa.Column("option_text", sa.Text(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.UniqueConstraint("question_id", "display_order", name="uq_question_options_question_order"),
    )
    op.create_index("ix_question_options_question", "question_options", ["question_id"])
    op.create_index("uq_question_options_one_correct", "question_options", ["question_id"], unique=True,
                    sqlite_where=sa.text("is_correct = 1"), postgresql_where=sa.text("is_correct IS TRUE"))
    op.create_table(
        "user_question_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=False), sa.ForeignKey("profiles.id", name="fk_user_question_attempts_user_id_profiles", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", sa.Integer(), sa.ForeignKey("questions.id", name="fk_user_question_attempts_question_id_questions", ondelete="CASCADE"), nullable=False),
        sa.Column("selected_option_id", sa.Integer(), sa.ForeignKey("question_options.id", name="fk_user_question_attempts_selected_option_id_question_options"), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("attempted_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_user_question_attempts_user_time", "user_question_attempts", ["user_id", "attempted_at"])
    op.create_index("ix_user_question_attempts_question", "user_question_attempts", ["question_id"])

    bind = op.get_bind()
    # Reflect the just-created tables so the INSERT result exposes its generated
    # primary key on both SQLite and PostgreSQL.
    topic_table = sa.Table("topics", sa.MetaData(), autoload_with=bind)
    question_table = sa.Table("questions", sa.MetaData(), autoload_with=bind)
    option_table = sa.Table("question_options", sa.MetaData(), autoload_with=bind)
    topic_ids = {slug: topic_id for topic_id, slug in bind.execute(sa.select(topic_table.c.id, topic_table.c.slug))}
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for topic_slug, question_text, difficulty, explanation, options in DEMO_QUESTIONS:
        if topic_slug not in topic_ids:
            raise RuntimeError(f"Required demo topic is missing: {topic_slug}")
        if sum(1 for _, is_correct in options if is_correct) != 1:
            raise RuntimeError("Each demo question must have exactly one correct option")
        inserted = bind.execute(question_table.insert().values(
            topic_id=topic_ids[topic_slug], question_text=question_text, explanation=explanation,
            difficulty=difficulty, question_type="MCQ", source="Prashna demo questions",
            is_published=True, created_at=now, updated_at=now))
        question_id = inserted.inserted_primary_key[0]
        bind.execute(option_table.insert(), [
            {"question_id": question_id, "option_text": option_text, "is_correct": is_correct, "display_order": order}
            for order, (option_text, is_correct) in enumerate(options)
        ])


def downgrade():
    op.drop_index("ix_user_question_attempts_question", table_name="user_question_attempts")
    op.drop_index("ix_user_question_attempts_user_time", table_name="user_question_attempts")
    op.drop_table("user_question_attempts")
    op.drop_index("uq_question_options_one_correct", table_name="question_options")
    op.drop_index("ix_question_options_question", table_name="question_options")
    op.drop_table("question_options")
    op.drop_index("ix_questions_type_difficulty", table_name="questions")
    op.drop_index("ix_questions_topic_published", table_name="questions")
    op.drop_table("questions")
