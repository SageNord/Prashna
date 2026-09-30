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
from app.models import (Article, ArticleTopic, DailyQuizAttempt, LearningContent, Profile, Question,
                        QuestionOption, QuizOption, QuizQuestion, Subject, Topic, UserActivity,
                        UserBookmark, UserQuestionAttempt, UserRevision, UserTopicProgress)
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
    assert TestClient(app).get("/api/topics/private-topic/questions").status_code == 401
    assert TestClient(app).get("/api/me/progress").status_code == 401
    assert TestClient(app).post("/api/topics/private-topic/reading-complete").status_code == 401


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


def test_learning_catalog_and_user_scoped_topic_progress(harness):
    client, factory, user, _, _, _ = harness
    db = factory()
    subject = Subject(name="Indian Polity", slug="indian-polity", description="Constitution and institutions.",
                      icon="landmark", color="#416c52", display_order=1, is_active=True)
    db.add(subject); db.flush()
    topic = Topic(subject_id=subject.id, name="Constitution Basics", slug="constitution-basics",
                  description="Constitutional structure and values.", display_order=1, is_active=True)
    db.add(topic); db.flush()
    db.add(LearningContent(subject_id=subject.id, topic_id=topic.id, title="A first look at the Constitution",
        slug="demo-constitution-basics", content_type="LESSON", summary="Demo lesson summary.",
        body="Demo lesson body.", difficulty="FOUNDATION", estimated_minutes=8,
        source="Prashna demo material", is_published=True))
    db.commit(); db.close()

    subjects = client.get("/api/subjects")
    assert subjects.status_code == 200
    assert subjects.json()[0]["slug"] == "indian-polity"
    assert subjects.json()[0]["topic_count"] == 1
    assert subjects.json()[0]["progress_percent"] == 0

    subject_response = client.get("/api/subjects/indian-polity")
    assert subject_response.json()["topics"][0]["slug"] == "constitution-basics"
    topic_response = client.get("/api/topics/constitution-basics")
    assert topic_response.json()["content"][0]["title"] == "A first look at the Constitution"
    assert topic_response.json()["completed"] is False

    assert client.post("/api/topics/constitution-basics/complete").json()["completed"] is True
    assert client.post("/api/topics/constitution-basics/complete").json()["completed"] is True
    db = factory()
    assert db.query(UserTopicProgress).filter_by(user_id=user.id, topic_id=topic.id).count() == 1
    db.close()
    assert client.get("/api/subjects").json()[0]["progress_percent"] == 100

    other_id = str(uuid4())
    db = factory(); db.add(Profile(id=other_id, email="other@example.com")); db.commit(); db.close()
    app.dependency_overrides[current_user] = lambda: AuthUser(other_id, "other@example.com", {}, {})
    assert client.get("/api/subjects").json()[0]["progress_percent"] == 0


def add_practice_question(db, *, slug="practice-topic", question_text="Which option is correct?", published=True):
    subject = db.query(Subject).filter_by(slug="practice-subject").first()
    if subject is None:
        subject = Subject(name="Practice Subject", slug="practice-subject", description="Demo subject.",
                          icon="book-open", color="#416c52", display_order=1, is_active=True)
        db.add(subject); db.flush()
    topic = db.query(Topic).filter_by(slug=slug).first()
    if topic is None:
        topic = Topic(subject_id=subject.id, name="Practice Topic", slug=slug, description="Demo topic.",
                      display_order=1, is_active=True)
        db.add(topic); db.flush()
    question = Question(topic_id=topic.id, question_text=question_text,
        explanation="The first option is supported by the explanation.", difficulty="MEDIUM",
        question_type="MCQ", source="Prashna demo questions", is_published=published)
    question.options = [QuestionOption(option_text="Correct answer", is_correct=True, display_order=0),
                        QuestionOption(option_text="Incorrect answer", is_correct=False, display_order=1)]
    db.add(question); db.flush()
    return topic, question, question.options[0], question.options[1]


def test_question_listing_hides_answer_and_excludes_unpublished(harness):
    client, factory, _, _, _, _ = harness
    db = factory()
    topic, question, correct_option, _ = add_practice_question(db)
    add_practice_question(db, slug="practice-topic", question_text="Unpublished sample?", published=False)
    db.commit()

    response = client.get(f"/api/topics/{topic.slug}/questions")
    assert response.status_code == 200
    assert len(response.json()) == 1
    item = response.json()[0]
    assert item["id"] == question.id
    assert item["question_type"] == "MCQ"
    assert item["source"] == "Prashna demo questions"
    assert all(set(option) == {"id", "text"} for option in item["options"])
    assert "correct_option_id" not in item
    assert all("is_correct" not in option for option in item["options"])
    assert correct_option.id in [option["id"] for option in item["options"]]


def test_question_attempt_correct_incorrect_and_persists_user_identity(harness):
    client, factory, user, _, _, _ = harness
    db = factory()
    _, correct_q, correct_option, wrong_option = add_practice_question(db, slug="correct-topic")
    _, wrong_q, wrong_q_correct, wrong_q_wrong_option = add_practice_question(db, slug="wrong-topic", question_text="Second practice question?")
    db.commit()

    correct = client.post(f"/api/questions/{correct_q.id}/attempt", json={"option_id": correct_option.id,
        "user_id": str(uuid4())})
    assert correct.status_code == 200
    assert correct.json()["is_correct"] is True
    assert correct.json()["correct_option_id"] == correct_option.id
    assert correct.json()["correct_answer"] == "Correct answer"
    assert correct.json()["explanation"] == correct_q.explanation

    incorrect = client.post(f"/api/questions/{wrong_q.id}/attempt", json={"option_id": wrong_q_wrong_option.id})
    assert incorrect.status_code == 200
    assert incorrect.json()["is_correct"] is False
    assert incorrect.json()["correct_option_id"] == wrong_q_correct.id
    assert incorrect.json()["correct_answer"] == "Correct answer"

    db = factory()
    saved = db.query(UserQuestionAttempt).order_by(UserQuestionAttempt.id).all()
    assert len(saved) == 2
    assert all(row.user_id == user.id for row in saved)
    assert [row.is_correct for row in saved] == [True, False]
    assert db.query(UserActivity).filter_by(user_id=user.id, activity_type="QUESTION_ATTEMPT").count() == 1
    assert client.get("/api/me/question-attempts?topic_slug=wrong-topic").json()[0]["selected_answer"] == "Incorrect answer"
    db.close()


def test_reading_completion_is_authenticated_idempotent_and_separate_from_topic_completion(harness):
    client, factory, user, _, _, _ = harness
    db = factory(); topic, _, _, _ = add_practice_question(db, slug="reading-topic")
    db.commit(); db.close()

    assert client.post(f"/api/topics/{topic.slug}/reading-complete").status_code == 200
    first = client.get(f"/api/topics/{topic.slug}").json()
    assert first["reading_completed"] is True
    assert first["completed"] is False
    assert first["progress_percent"] == 50
    assert first["reading_completed_at"]
    assert client.post(f"/api/topics/{topic.slug}/reading-complete").status_code == 200
    db = factory(); progress = db.query(UserTopicProgress).filter_by(user_id=user.id, topic_id=topic.id).one()
    saved_time = progress.reading_completed_at
    assert saved_time is not None
    assert progress.completed_at is None
    assert db.query(UserActivity).filter_by(user_id=user.id, activity_type="READING_COMPLETE").count() == 1
    db.close()
    assert client.post(f"/api/topics/{topic.slug}/complete").json()["completed"] is True
    assert client.get(f"/api/topics/{topic.slug}").json()["completed"] is True


def test_progress_accuracy_weak_topics_mistakes_and_user_isolation(harness):
    client, factory, user, _, _, _ = harness
    db = factory()
    topic, q1, correct1, wrong1 = add_practice_question(db, slug="weak-topic", question_text="Sample one?")
    _, q2, correct2, wrong2 = add_practice_question(db, slug="weak-topic", question_text="Sample two?")
    _, q3, correct3, wrong3 = add_practice_question(db, slug="weak-topic", question_text="Sample three?")
    completed_topic, _, _, _ = add_practice_question(db, slug="completed-topic", question_text="Completed sample?")
    db.add(UserTopicProgress(user_id=user.id, topic_id=completed_topic.id, completed_at=datetime.now(timezone.utc).replace(tzinfo=None)))
    db.commit(); db.close()
    for question, option in ((q1, correct1), (q2, wrong2), (q3, wrong3)):
        result = client.post(f"/api/questions/{question.id}/attempt", json={"option_id": option.id})
        assert result.status_code == 200
        if question.id == q1.id:
            assert client.get(f"/api/topics/{topic.slug}").json()["progress_percent"] == 17
    summary = client.get("/api/me/progress").json()
    assert summary["topics_completed"] == 1
    assert summary["topics_in_progress"] == 1
    assert summary["practice_questions_attempted"] == 3
    assert summary["practice_accuracy"] == 33
    assert summary["weak_topics"] == [{"id": topic.id, "name": topic.name, "slug": topic.slug,
        "questions_attempted": 3, "attempts": 3, "accuracy": 33}]
    assert summary["recently_completed"][0]["slug"] == completed_topic.slug
    mistakes = client.get("/api/me/question-attempts?mistakes_only=true").json()
    assert len(mistakes) == 2
    assert all(row["topic_slug"] == topic.slug and row["source"] == "Prashna demo questions" for row in mistakes)
    assert all(row["correct_answer"] == "Correct answer" and row["explanation"] for row in mistakes)

    other_id = str(uuid4())
    db = factory(); db.add(Profile(id=other_id, display_name="Other", email="other@example.com")); db.commit(); db.close()
    app.dependency_overrides[current_user] = lambda: AuthUser(other_id, "other@example.com", {}, {})
    isolated = client.get("/api/me/progress").json()
    assert isolated["topics_completed"] == isolated["topics_in_progress"] == 0
    assert isolated["practice_questions_attempted"] == isolated["review_mistakes_count"] == 0
    assert client.get("/api/me/question-attempts?mistakes_only=true").json() == []


def test_question_attempt_rejects_invalid_or_foreign_options(harness):
    client, factory, _, _, _, _ = harness
    db = factory()
    _, question, _, _ = add_practice_question(db, slug="first-topic")
    _, other_question, other_option, _ = add_practice_question(db, slug="second-topic", question_text="Another question?")
    db.commit()
    assert other_question.id != question.id
    assert client.post(f"/api/questions/{question.id}/attempt", json={"option_id": 999999}).status_code == 422
    assert client.post(f"/api/questions/{question.id}/attempt", json={"option_id": other_option.id}).status_code == 422


def test_unpublished_question_cannot_be_retrieved_or_attempted(harness):
    client, factory, _, _, _, _ = harness
    db = factory()
    topic, question, option, _ = add_practice_question(db, slug="unpublished-topic", published=False)
    db.commit()
    assert client.get(f"/api/topics/{topic.slug}/questions").json() == []
    assert client.post(f"/api/questions/{question.id}/attempt", json={"option_id": option.id}).status_code == 404


def test_question_attempt_history_is_scoped_to_authenticated_user(harness):
    client, factory, _, _, _, _ = harness
    db = factory()
    _, question, _, wrong_option = add_practice_question(db)
    db.commit()
    assert client.post(f"/api/questions/{question.id}/attempt", json={"option_id": wrong_option.id}).status_code == 200
    assert len(client.get("/api/me/question-attempts").json()) == 1

    other_id = str(uuid4())
    db = factory(); db.add(Profile(id=other_id, email="other@example.com")); db.commit(); db.close()
    app.dependency_overrides[current_user] = lambda: AuthUser(other_id, "other@example.com", {}, {})
    assert client.get("/api/me/question-attempts").json() == []
    assert client.get(f"/api/me/question-attempts?user_id={harness[2].id}").json() == []


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
