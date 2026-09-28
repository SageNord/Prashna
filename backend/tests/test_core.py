from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import AuthUser, current_user
from app.database import Base, get_db
import app.main as api_module
from app.main import app, require_admin
from app.models import (Article, ArticleTopic, DailyQuizAttempt, Profile, QuizOption,
                        QuizQuestion, UserActivity, UserBookmark, UserRevision)
from app.services.llm import MockProvider, get_provider, transform_source
from app.services.streaks import streak_metrics


@pytest.fixture
def harness():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    user_id = str(uuid4())
    user = AuthUser(user_id, "learner@example.com", {"display_name": "Learner"}, {})

    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    def override_user():
        return user

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[current_user] = override_user
    db = TestingSession()
    db.add(Profile(id=user_id, display_name="Learner", email=user.email, onboarding_complete=True))
    article = Article(title="Sample policy", source="Sample", category="Polity", summary="A source-backed sample.",
                      why_it_matters="Study the implementation.", upsc_relevance="GS-II")
    db.add(article)
    db.flush()
    question = QuizQuestion(article_id=article.id, question="What should be studied?", explanation="Implementation matters.")
    question.options = [QuizOption(option_text="Implementation", is_correct=True),
                        QuizOption(option_text="Unrelated answer", is_correct=False)]
    db.add(question)
    db.commit()
    article_id, question_id = article.id, question.id
    correct_option_id = question.options[0].id
    db.close()
    try:
        yield TestClient(app), TestingSession, user, article_id, question_id, correct_option_id
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_health_and_public_feed(harness):
    client, _, _, _, _, _ = harness
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/feed?limit=3").status_code == 200


def test_auth_required_without_bearer():
    response = TestClient(app).get("/api/bookmarks")
    assert response.status_code == 401


def test_bookmark_idempotency_and_user_isolation(harness):
    client, factory, user, article_id, _, _ = harness
    assert client.post(f"/api/bookmarks?article_id={article_id}").status_code == 201
    assert client.post(f"/api/bookmarks?article_id={article_id}").status_code == 201
    assert len(client.get("/api/bookmarks").json()) == 1
    other_id = str(uuid4())
    db = factory(); db.add(Profile(id=other_id, display_name="Other", email="other@example.com")); db.commit(); db.close()
    app.dependency_overrides[current_user] = lambda: AuthUser(other_id, "other@example.com", {}, {})
    assert client.get("/api/bookmarks").json() == []
    assert client.delete(f"/api/bookmarks/{article_id}").status_code == 200
    app.dependency_overrides[current_user] = lambda: user
    assert client.get("/api/bookmarks").json() == [{**client.get("/api/articles/"+str(article_id)).json()}]


def test_quiz_attempt_completion_history_and_scope(harness):
    client, factory, user, _, question_id, option_id = harness
    response = client.post("/api/quiz/attempt", json={"question_id": question_id, "selected_option": option_id})
    assert response.status_code == 200 and response.json()["correct"] is True
    complete = client.post("/api/quiz/complete")
    assert complete.status_code == 200 and complete.json()["score"] == 1
    assert client.post("/api/quiz/complete").json()["already_completed"] is True
    assert len(client.get("/api/quiz/history").json()) == 1
    other_id = str(uuid4()); db = factory(); db.add(Profile(id=other_id, email="other@example.com")); db.commit(); db.close()
    app.dependency_overrides[current_user] = lambda: AuthUser(other_id, "other@example.com", {}, {})
    assert client.get("/api/quiz/history").json() == []
    assert client.post("/api/quiz/complete").status_code == 422
    app.dependency_overrides[current_user] = lambda: user


def test_revision_is_persisted_per_user_and_updates_profile(harness):
    client, factory, user, article_id, _, _ = harness
    response = client.post(f"/api/revision/{article_id}", json={"difficulty": "good"})
    assert response.status_code == 200 and response.json()["review_count"] == 1
    assert client.get("/api/me").json()["revisions_completed"] == 1
    other_id = str(uuid4()); db = factory(); db.add(Profile(id=other_id, email="other@example.com")); db.commit(); db.close()
    app.dependency_overrides[current_user] = lambda: AuthUser(other_id, "other@example.com", {}, {})
    assert client.get("/api/revision").json() == []


def test_article_read_activity_and_streak_are_idempotent(harness):
    client, factory, _, article_id, _, _ = harness
    first = client.post(f"/api/activity/article-read?article_id={article_id}").json()
    again = client.post(f"/api/activity/article-read?article_id={article_id}").json()
    assert first["current_streak"] == again["current_streak"] == 1
    db = factory()
    assert db.query(UserActivity).filter_by(activity_type="ARTICLE_READ").count() == 1
    assert db.get(Profile, harness[2].id).longest_streak == 1
    db.close()


def test_streak_date_transitions():
    today = date(2026, 9, 29)
    assert streak_metrics({today - timedelta(days=2), today - timedelta(days=1)}, today) == (2, 2)
    assert streak_metrics({today - timedelta(days=1)}, today) == (1, 1)
    assert streak_metrics({today - timedelta(days=4)}, today) == (0, 1)


def test_ai_falls_back_to_mock_without_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    assert isinstance(get_provider(), MockProvider)
    assert transform_source("Source says a policy was introduced.")["summary"]


def test_invalid_quiz_option_is_rejected(harness):
    client, _, _, _, question_id, _ = harness
    response = client.post("/api/quiz/attempt", json={"question_id": question_id, "selected_option": 999999})
    assert response.status_code == 422


def test_profile_statistics_are_database_backed(harness):
    client, _, _, article_id, question_id, option_id = harness
    client.post(f"/api/bookmarks?article_id={article_id}")
    client.post(f"/api/activity/article-read?article_id={article_id}")
    client.post("/api/quiz/attempt", json={"question_id": question_id, "selected_option": option_id})
    client.post("/api/quiz/complete")
    profile = client.get("/api/me").json()
    assert profile["articles_read"] == 1
    assert profile["articles_saved"] == 1
    assert profile["questions_answered"] == 1
    assert profile["quiz_accuracy"] == 100
    assert profile["quizzes_completed"] == 1


def test_admin_ingestion_deduplicates_identical_source(harness, monkeypatch):
    client, _, user, _, _, _ = harness
    api_module.app.dependency_overrides[require_admin] = lambda: user
    monkeypatch.setattr(api_module, "process_article", lambda article_id: None)
    payload = {"title": "A sample source report", "source": "Sample source",
               "content": "This is supplied source content for a duplicate ingestion test. " * 3}
    first = client.post("/api/ingest", json=payload)
    second = client.post("/api/ingest", json=payload)
    assert first.status_code == 202 and first.json()["duplicate"] is False
    assert second.status_code == 202 and second.json()["duplicate"] is True
