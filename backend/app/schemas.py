from pydantic import BaseModel, Field, HttpUrl

class ArticleIn(BaseModel):
    title: str = Field(min_length=5, max_length=300)
    source: str = Field(default="Prashna Editorial Learning Sample", max_length=200)
    source_url: HttpUrl | None = None
    category: str = Field(default="Governance", max_length=80)
    summary: str = Field(min_length=10)
    why_it_matters: str = Field(min_length=10)
    upsc_relevance: str = ""
    topics: list[str] = Field(default_factory=list)
    gs_papers: list[str] = Field(default_factory=list)
    key_facts: list[str] = Field(default_factory=list)

class IngestIn(BaseModel):
    title: str = Field(min_length=5, max_length=300)
    source: str = Field(min_length=2, max_length=200)
    source_url: HttpUrl | None = None
    published_at: str | None = None
    content: str = Field(min_length=100, max_length=50000)

class AttemptIn(BaseModel):
    question_id: int = Field(gt=0)
    selected_option: int = Field(gt=0)

class RevisionIn(BaseModel):
    difficulty: str = Field(pattern="^(easy|good|difficult)$")

class ProfileUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    target_exam: str | None = Field(default=None, max_length=80)
    target_year: int | None = Field(default=None, ge=2026, le=2100)
    preferred_subjects: list[str] = Field(default_factory=list, max_length=12)
