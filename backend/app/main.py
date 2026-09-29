from collections import defaultdict
from datetime import date, datetime, timezone, timedelta
import hmac
from hashlib import sha256
import logging
import os
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, joinedload, selectinload

from .auth import AuthUser, current_user, require_admin
from .database import get_db, SessionLocal
from .models import (Article, ArticleGSTag, ArticleSource, ArticleTopic, DailyQuizAttempt, IngestionRun, KeyFact, Profile,
    LearningContent, Question, QuestionOption, QuizOption, QuizQuestion, Subject, Topic, UserActivity,
    UserBookmark, UserQuestionAttempt, UserQuizAttempt, UserRevision, UserTopicProgress)
from .schemas import ArticleIn, AttemptIn, IngestIn, ProfileUpdate, QuestionAttemptIn, RevisionIn
from .services.ingestion import process_stored_article, run_ingestion
from .services.relevance import classify_relevance, event_fingerprint, utc_naive
from .services.sources import canonicalize_url, configured_sources
from .services.streaks import streak_metrics

logger = logging.getLogger("prashna.api")
app=FastAPI(title="Prashna API",version="2.0.0")
cors_origins=[x.strip() for x in os.getenv("CORS_ORIGINS","http://localhost:5173,http://127.0.0.1:5173").split(",") if x.strip()]
app.add_middleware(CORSMiddleware,allow_origins=cors_origins,allow_methods=["GET","POST","PATCH","DELETE","OPTIONS"],allow_headers=["Authorization","Content-Type","X-User-Timezone","X-Cron-Secret"],max_age=600)

def local_today(tz_name:str|None)->date:
    try:tz=ZoneInfo(tz_name or "UTC")
    except (ZoneInfoNotFoundError,ValueError):tz=ZoneInfo("UTC")
    return datetime.now(tz).date()

def ensure_profile(db:Session,user:AuthUser)->Profile:
    profile=db.get(Profile,user.id)
    if profile:return profile
    name=str(user.user_metadata.get("display_name") or user.user_metadata.get("full_name") or "").strip()[:120]
    profile=Profile(id=user.id,display_name=name,email=user.email[:320],avatar_url=user.user_metadata.get("avatar_url"),preferred_subjects=[])
    db.add(profile)
    try:db.flush()
    except Exception:
        db.rollback();profile=db.get(Profile,user.id)
        if profile:return profile
        raise
    return profile

def profile_for_update(db:Session,user:AuthUser)->Profile:
    ensure_profile(db,user)
    return db.query(Profile).filter(Profile.id==user.id).with_for_update().one()

def record_activity(db:Session,user:AuthUser,activity_type:str,today:date,metadata:dict|None=None)->None:
    profile=profile_for_update(db,user)
    values={"user_id":user.id,"activity_type":activity_type,"activity_date":today,"metadata_json":metadata or {}}
    dialect=db.get_bind().dialect.name
    if dialect=="postgresql":
        db.execute(pg_insert(UserActivity).values(**values).on_conflict_do_nothing(index_elements=["user_id","activity_type","activity_date"]))
    elif dialect=="sqlite":
        db.execute(sqlite_insert(UserActivity).values(**values).on_conflict_do_nothing(index_elements=["user_id","activity_type","activity_date"]))
    elif not db.query(UserActivity).filter_by(user_id=user.id,activity_type=activity_type,activity_date=today).first():
        db.add(UserActivity(**values));db.flush()
    days=set(db.scalars(select(UserActivity.activity_date).where(UserActivity.user_id==user.id)).all())
    current,longest=streak_metrics(days,today)
    profile.current_streak=current
    profile.longest_streak=max(profile.longest_streak,longest)
    profile.last_activity_date=max(days) if days else None
    profile.updated_at=datetime.now(timezone.utc)

def article_json(article:Article)->dict:
    published=article.published_at
    if published and published.tzinfo is None:published=published.replace(tzinfo=timezone.utc)
    ingested=article.ingested_at
    if ingested and ingested.tzinfo is None:ingested=ingested.replace(tzinfo=timezone.utc)
    processed=article.processed_at
    if processed and processed.tzinfo is None:processed=processed.replace(tzinfo=timezone.utc)
    return {"id":article.id,"title":article.title,"original_title":article.original_title or article.title,
        "source":article.source,"source_url":article.source_url,"source_identifier":article.source_identifier,
        "published_at":published,"ingested_at":ingested,"category":article.category,"summary":article.summary,
        "what_happened":article.what_happened or article.summary,"why_it_matters":article.why_it_matters,
        "background":article.background or "","upsc_relevance":article.upsc_relevance,
        "topics":[row.topic for row in article.topics],"gs_papers":[row.gs_paper for row in article.gs_tags],
        "key_facts":[row.fact for row in article.facts],"prelims_points":article.prelims_points or [],
        "mains_angles":article.mains_angles or [],"important_terms":article.important_terms or [],
        "relevance_score":article.relevance_score,"relevance_category":article.relevance_category,
        "alternative_sources":[{"source":row.source_name,"source_url":row.source_url,"published_at":row.published_at}
                               for row in article.alternative_sources],
        "processing_status":article.processing_status,"processing_model":article.processing_model,"processed_at":processed}

def article_query(db:Session):
    return db.query(Article).options(joinedload(Article.topics),joinedload(Article.gs_tags),joinedload(Article.facts),selectinload(Article.alternative_sources))

@app.get("/api/health")
def health():return {"status":"ok"}


def learning_content_json(row: LearningContent) -> dict:
    return {"id": row.id, "title": row.title, "slug": row.slug, "content_type": row.content_type,
        "summary": row.summary, "body": row.body, "difficulty": row.difficulty,
        "estimated_minutes": row.estimated_minutes, "source": row.source, "source_url": row.source_url}


def subject_json(db: Session, subject: Subject, user_id: str) -> dict:
    topic_ids = db.query(Topic.id).filter(Topic.subject_id == subject.id, Topic.is_active.is_(True)).all()
    ids = [row[0] for row in topic_ids]
    completed = (db.query(UserTopicProgress.topic_id).filter(
        UserTopicProgress.user_id == user_id, UserTopicProgress.topic_id.in_(ids),
        UserTopicProgress.completed_at.is_not(None)).all() if ids else [])
    completed_ids = {row[0] for row in completed}
    total, done = len(ids), len(completed_ids)
    return {"id": subject.id, "name": subject.name, "slug": subject.slug,
        "description": subject.description, "icon": subject.icon, "color": subject.color,
        "display_order": subject.display_order, "topic_count": total, "completed_topics": done,
        "progress_percent": round(done * 100 / total) if total else 0}


@app.get("/api/subjects")
def list_subjects(db: Session = Depends(get_db), user: AuthUser = Depends(current_user)):
    subjects = db.query(Subject).filter(Subject.is_active.is_(True)).order_by(Subject.display_order, Subject.name).all()
    return [subject_json(db, subject, user.id) for subject in subjects]


@app.get("/api/subjects/{slug}")
def get_subject(slug: str, db: Session = Depends(get_db), user: AuthUser = Depends(current_user)):
    subject = db.query(Subject).filter(Subject.slug == slug, Subject.is_active.is_(True)).first()
    if subject is None:
        raise HTTPException(404, "Subject not found")
    result = subject_json(db, subject, user.id)
    topics = db.query(Topic).filter(Topic.subject_id == subject.id, Topic.is_active.is_(True)).order_by(Topic.display_order, Topic.name).all()
    progress_rows = db.query(UserTopicProgress.topic_id, UserTopicProgress.completed_at).filter(
        UserTopicProgress.user_id == user.id, UserTopicProgress.topic_id.in_([topic.id for topic in topics])
    ).all() if topics else []
    progress_by_topic = {topic_id: completed_at for topic_id, completed_at in progress_rows}
    result["topics"] = [{"id": topic.id, "name": topic.name, "slug": topic.slug,
        "description": topic.description, "parent_topic_id": topic.parent_topic_id,
        "display_order": topic.display_order, "completed": progress_by_topic.get(topic.id) is not None,
        "completed_at": progress_by_topic.get(topic.id)} for topic in topics]
    return result


@app.get("/api/topics/{slug}")
def get_topic(slug: str, db: Session = Depends(get_db), user: AuthUser = Depends(current_user)):
    topic = db.query(Topic).filter(Topic.slug == slug, Topic.is_active.is_(True)).first()
    if topic is None:
        raise HTTPException(404, "Topic not found")
    progress = db.query(UserTopicProgress).filter_by(user_id=user.id, topic_id=topic.id).first()
    content_rows = db.query(LearningContent).filter(LearningContent.topic_id == topic.id,
        LearningContent.is_published.is_(True)).order_by(LearningContent.id).all()
    question_count = db.query(Question.id).filter(Question.topic_id == topic.id,
        Question.is_published.is_(True), Question.question_type == "MCQ").count()
    children = db.query(Topic).filter(Topic.parent_topic_id == topic.id, Topic.is_active.is_(True)).order_by(Topic.display_order).all()
    return {"id": topic.id, "name": topic.name, "slug": topic.slug, "description": topic.description,
        "parent_topic_id": topic.parent_topic_id,
        "subject": {"id": topic.subject.id, "name": topic.subject.name, "slug": topic.subject.slug},
        "completed": bool(progress and progress.completed_at),
        "children": [{"id": child.id, "name": child.name, "slug": child.slug, "description": child.description} for child in children],
        "content": [learning_content_json(row) for row in content_rows], "question_count": question_count}


@app.post("/api/topics/{slug}/complete")
def complete_topic(slug: str, db: Session = Depends(get_db), user: AuthUser = Depends(current_user),
                   timezone_name: str | None = Header(default=None, alias="X-User-Timezone")):
    topic = db.query(Topic).filter(Topic.slug == slug, Topic.is_active.is_(True)).first()
    if topic is None:
        raise HTTPException(404, "Topic not found")
    ensure_profile(db, user)
    progress = db.query(UserTopicProgress).filter_by(user_id=user.id, topic_id=topic.id).first()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    newly_completed = False
    if progress is None:
        progress = UserTopicProgress(user_id=user.id, topic_id=topic.id, completed_at=now, updated_at=now)
        db.add(progress)
        newly_completed = True
    elif progress.completed_at is None:
        progress.completed_at = now
        progress.updated_at = now
        newly_completed = True
    if newly_completed:
        record_activity(db, user, "TOPIC_COMPLETE", local_today(timezone_name))
    db.commit()
    return {"topic_slug": topic.slug, "completed": True, "completed_at": progress.completed_at}


def question_public_json(question: Question) -> dict:
    return {"id": question.id, "question_text": question.question_text,
        "difficulty": question.difficulty, "question_type": question.question_type,
        "source": question.source,
        "options": [{"id": option.id, "text": option.option_text} for option in question.options]}


@app.get("/api/topics/{slug}/questions")
def topic_questions(slug: str, db: Session = Depends(get_db), user: AuthUser = Depends(current_user)):
    topic = db.query(Topic).filter(Topic.slug == slug, Topic.is_active.is_(True)).first()
    if topic is None:
        raise HTTPException(404, "Topic not found")
    questions = db.query(Question).options(selectinload(Question.options)).filter(
        Question.topic_id == topic.id, Question.is_published.is_(True), Question.question_type == "MCQ"
    ).order_by(Question.id).all()
    return [question_public_json(question) for question in questions]


@app.post("/api/questions/{question_id}/attempt")
def submit_question_attempt(question_id: int, data: QuestionAttemptIn, db: Session = Depends(get_db),
                            user: AuthUser = Depends(current_user),
                            timezone_name: str | None = Header(default=None, alias="X-User-Timezone")):
    question = db.query(Question).options(selectinload(Question.options)).filter(
        Question.id == question_id, Question.is_published.is_(True), Question.question_type == "MCQ"
    ).first()
    if question is None:
        raise HTTPException(404, "Question not found")
    selected = next((option for option in question.options if option.id == data.option_id), None)
    if selected is None:
        raise HTTPException(422, "Selected option does not belong to this question")
    correct_options = [option for option in question.options if option.is_correct]
    if len(correct_options) != 1:
        logger.error("Published MCQ has invalid answer key question_id=%s", question_id)
        raise HTTPException(500, "Question answer key is unavailable")
    correct = correct_options[0]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    attempt = UserQuestionAttempt(user_id=user.id, question_id=question.id,
        selected_option_id=selected.id, is_correct=(selected.id == correct.id), attempted_at=now)
    ensure_profile(db, user)
    db.add(attempt)
    record_activity(db, user, "QUESTION_ATTEMPT", local_today(timezone_name))
    db.commit()
    db.refresh(attempt)
    return {"attempt_id": attempt.id, "is_correct": attempt.is_correct,
        "selected_option_id": selected.id, "selected_answer": selected.option_text,
        "correct_option_id": correct.id, "correct_answer": correct.option_text,
        "explanation": question.explanation}


@app.get("/api/me/question-attempts")
def question_attempt_history(topic_slug: str | None = None,
                             limit: int = Query(100, ge=1, le=100),
                             db: Session = Depends(get_db), user: AuthUser = Depends(current_user)):
    query = db.query(UserQuestionAttempt).join(Question).options(
        joinedload(UserQuestionAttempt.question).selectinload(Question.options),
        joinedload(UserQuestionAttempt.selected_option)
    ).filter(UserQuestionAttempt.user_id == user.id)
    if topic_slug:
        query = query.join(Topic, Question.topic_id == Topic.id).filter(Topic.slug == topic_slug)
    attempts = query.order_by(UserQuestionAttempt.attempted_at.desc(), UserQuestionAttempt.id.desc()).limit(limit).all()
    result = []
    for attempt in attempts:
        correct = next((option for option in attempt.question.options if option.is_correct), None)
        result.append({"id": attempt.id, "question_id": attempt.question_id,
            "question_text": attempt.question.question_text, "selected_option_id": attempt.selected_option_id,
            "selected_answer": attempt.selected_option.option_text,
            "correct_option_id": correct.id if correct else None,
            "correct_answer": correct.option_text if correct else None,
            "is_correct": attempt.is_correct, "explanation": attempt.question.explanation,
            "attempted_at": attempt.attempted_at})
    return result

@app.get("/api/feed")
def feed(category:str|None=None,limit:int=Query(30,ge=1,le=100),offset:int=Query(0,ge=0,le=10000),db:Session=Depends(get_db)):
    query=article_query(db)
    freshness_cutoff=datetime.now(timezone.utc).replace(tzinfo=None)-timedelta(days=60)
    query=query.filter(Article.processing_status=="COMPLETED",Article.relevance_category.in_(["HIGH","MEDIUM"]),Article.source_url.is_not(None))
    query=query.filter(or_(Article.published_at>=freshness_cutoff,Article.published_at.is_(None)))
    if category:query=query.filter(func.lower(Article.category)==category.lower())
    return [article_json(a) for a in query.order_by(Article.published_at.desc().nullslast(),Article.relevance_score.desc(),Article.id.desc()).offset(offset).limit(limit).all()]

@app.get("/api/articles/{article_id}")
def get_article(article_id:int,db:Session=Depends(get_db)):
    article=article_query(db).filter(Article.id==article_id).first()
    if not article:raise HTTPException(404,"Article not found")
    return article_json(article)

@app.post("/api/articles",status_code=201)
def create_article(data:ArticleIn,db:Session=Depends(get_db),_:AuthUser=Depends(require_admin)):
    article=Article(title=data.title,source=data.source,source_url=str(data.source_url) if data.source_url else None,category=data.category,summary=data.summary,why_it_matters=data.why_it_matters,upsc_relevance=data.upsc_relevance,processing_status="COMPLETED",processed_at=datetime.now(timezone.utc),processing_model="manual")
    article.topics=[ArticleTopic(topic=x) for x in data.topics];article.gs_tags=[ArticleGSTag(gs_paper=x) for x in data.gs_papers];article.facts=[KeyFact(fact=x) for x in data.key_facts]
    db.add(article);db.commit();db.refresh(article);return article_json(article)

@app.get("/api/articles/{article_id}/quiz")
def article_quiz(article_id:int,db:Session=Depends(get_db),_:AuthUser=Depends(current_user)):
    rows=db.query(QuizQuestion).options(joinedload(QuizQuestion.options)).filter_by(article_id=article_id).all()
    return [{"id":q.id,"question":q.question,"question_type":q.question_type,"explanation":q.explanation,"options":[{"id":o.id,"option_text":o.option_text} for o in q.options]} for q in rows]

@app.get("/api/bookmarks")
def bookmarks(db:Session=Depends(get_db),user:AuthUser=Depends(current_user)):
    rows=article_query(db).join(UserBookmark,UserBookmark.article_id==Article.id).filter(UserBookmark.user_id==user.id).order_by(UserBookmark.created_at.desc()).all()
    return [article_json(a) for a in rows]

@app.post("/api/bookmarks",status_code=201)
def bookmark(article_id:int,db:Session=Depends(get_db),user:AuthUser=Depends(current_user)):
    if not db.get(Article,article_id):raise HTTPException(404,"Article not found")
    values={"user_id":user.id,"article_id":article_id}
    if db.get_bind().dialect.name=="postgresql":db.execute(pg_insert(UserBookmark).values(**values).on_conflict_do_nothing(index_elements=["user_id","article_id"]))
    elif db.get_bind().dialect.name=="sqlite":db.execute(sqlite_insert(UserBookmark).values(**values).on_conflict_do_nothing(index_elements=["user_id","article_id"]))
    elif not db.query(UserBookmark).filter_by(**values).first():db.add(UserBookmark(**values))
    db.commit();return {"saved":True,"article_id":article_id}

@app.delete("/api/bookmarks/{article_id}")
def unbookmark(article_id:int,db:Session=Depends(get_db),user:AuthUser=Depends(current_user)):
    db.query(UserBookmark).filter_by(user_id=user.id,article_id=article_id).delete(synchronize_session=False);db.commit()
    return {"saved":False,"article_id":article_id}

def question_json(question:QuizQuestion)->dict:
    return {"id":question.id,"article_id":question.article_id,"question":question.question,"question_type":question.question_type,"explanation":question.explanation,"options":[{"id":o.id,"option_text":o.option_text} for o in question.options]}

@app.get("/api/quiz/today")
def quiz_today(db:Session=Depends(get_db),_:AuthUser=Depends(current_user)):
    rows=db.query(QuizQuestion).options(joinedload(QuizQuestion.options)).order_by(QuizQuestion.id).limit(5).all()
    return [question_json(q) for q in rows]

@app.post("/api/quiz/attempt")
def attempt(data:AttemptIn,db:Session=Depends(get_db),user:AuthUser=Depends(current_user),timezone_name:str|None=Header(default=None,alias="X-User-Timezone")):
    question=db.get(QuizQuestion,data.question_id);option=db.get(QuizOption,data.selected_option)
    if not question or not option or option.question_id!=question.id:raise HTTPException(422,"Question or option is invalid")
    today=local_today(timezone_name);correct=bool(option.is_correct)
    db.add(UserQuizAttempt(user_id=user.id,question_id=question.id,selected_option=option.id,is_correct=correct,activity_date=today,attempted_at=datetime.now(timezone.utc)))
    db.commit();return {"correct":correct,"explanation":question.explanation}

@app.post("/api/quiz/complete")
def complete_daily_quiz(db:Session=Depends(get_db),user:AuthUser=Depends(current_user),timezone_name:str|None=Header(default=None,alias="X-User-Timezone")):
    today=local_today(timezone_name)
    prior=db.query(DailyQuizAttempt).filter_by(user_id=user.id,quiz_date=today).first()
    if prior:return {"completed":prior.completed,"score":prior.score,"quiz_date":str(prior.quiz_date),"current_streak":db.get(Profile,user.id).current_streak if db.get(Profile,user.id) else 0,"already_completed":True}
    attempts=db.query(UserQuizAttempt.question_id,UserQuizAttempt.is_correct).filter_by(user_id=user.id,activity_date=today).all()
    if not attempts:raise HTTPException(422,"Answer at least one quiz question first.")
    by_question=defaultdict(bool)
    for question_id,correct in attempts:by_question[question_id]=by_question[question_id] or correct
    score=min(5,sum(by_question.values()))
    row=DailyQuizAttempt(user_id=user.id,quiz_date=today,completed=True,score=score,completed_at=datetime.now(timezone.utc));db.add(row)
    try:
        record_activity(db,user,"QUIZ_COMPLETED",today,{"score":score})
        db.commit()
    except Exception:
        db.rollback();row=db.query(DailyQuizAttempt).filter_by(user_id=user.id,quiz_date=today).first()
        if row:return {"completed":row.completed,"score":row.score,"quiz_date":str(row.quiz_date),"already_completed":True}
        raise
    profile=db.get(Profile,user.id)
    return {"completed":True,"score":score,"quiz_date":str(today),"current_streak":profile.current_streak,"already_completed":False}

@app.get("/api/quiz/history")
def quiz_history(db:Session=Depends(get_db),user:AuthUser=Depends(current_user)):
    rows=db.query(DailyQuizAttempt).filter_by(user_id=user.id).order_by(DailyQuizAttempt.quiz_date.desc()).limit(90).all()
    return [{"date":str(r.quiz_date),"completed":r.completed,"score":r.score,"completed_at":r.completed_at} for r in rows]

@app.post("/api/activity/article-read")
def article_read(article_id:int=Query(gt=0),db:Session=Depends(get_db),user:AuthUser=Depends(current_user),timezone_name:str|None=Header(default=None,alias="X-User-Timezone")):
    if not db.get(Article,article_id):raise HTTPException(404,"Article not found")
    today=local_today(timezone_name);record_activity(db,user,"ARTICLE_READ",today,{"article_id":article_id});db.commit()
    return {"recorded":True,"current_streak":db.get(Profile,user.id).current_streak}

@app.get("/api/revision")
def revision(db:Session=Depends(get_db),user:AuthUser=Depends(current_user)):
    now=datetime.now(timezone.utc).replace(tzinfo=None)
    rows=db.query(UserRevision).filter_by(user_id=user.id).filter(UserRevision.next_review_at<=now).order_by(UserRevision.next_review_at).all()
    output=[]
    for row in rows:
        article=article_query(db).filter(Article.id==row.article_id).first()
        if article:output.append({"article":article_json(article),"difficulty":row.difficulty,"review_count":row.review_count,"next_review_at":row.next_review_at})
    return output

@app.post("/api/revision/{article_id}")
def revise(article_id:int,data:RevisionIn,db:Session=Depends(get_db),user:AuthUser=Depends(current_user),timezone_name:str|None=Header(default=None,alias="X-User-Timezone")):
    if not db.get(Article,article_id):raise HTTPException(404,"Article not found")
    row=db.query(UserRevision).filter_by(user_id=user.id,article_id=article_id).with_for_update().first()
    if not row:row=UserRevision(user_id=user.id,article_id=article_id,review_count=0,next_review_at=datetime.now(timezone.utc).replace(tzinfo=None));db.add(row);db.flush()
    row.difficulty=data.difficulty;row.review_count+=1;row.last_reviewed_at=datetime.now(timezone.utc).replace(tzinfo=None)
    days=1 if data.difficulty=="difficult" else [1,3,7,14,30][min(row.review_count-1,4)] if data.difficulty=="good" else [3,7,14,30,30][min(row.review_count-1,4)]
    row.next_review_at=row.last_reviewed_at+timedelta(days=days);today=local_today(timezone_name)
    record_activity(db,user,"REVISION_COMPLETED",today,{"article_id":article_id,"difficulty":data.difficulty});db.commit()
    return {"article_id":article_id,"difficulty":row.difficulty,"review_count":row.review_count,"last_reviewed_at":row.last_reviewed_at,"next_review_at":row.next_review_at,"current_streak":db.get(Profile,user.id).current_streak}

@app.get("/api/search")
def search(q:str=Query(min_length=1),db:Session=Depends(get_db)):
    term=f"%{q}%";rows=article_query(db).outerjoin(ArticleTopic).outerjoin(ArticleGSTag).filter(or_(Article.title.ilike(term),Article.summary.ilike(term),Article.category.ilike(term),ArticleTopic.topic.ilike(term),ArticleGSTag.gs_paper.ilike(term))).distinct().limit(30).all()
    return [article_json(a) for a in rows]

def get_profile_stats(db:Session,user:AuthUser)->dict:
    profile=ensure_profile(db,user);db.flush()
    saved=db.query(UserBookmark).filter_by(user_id=user.id).count()
    attempts=db.query(UserQuizAttempt).filter_by(user_id=user.id).all()
    questions_answered=len(attempts);accuracy=round(sum(a.is_correct for a in attempts)*100/questions_answered) if questions_answered else 0
    quizzes=db.query(DailyQuizAttempt).filter_by(user_id=user.id,completed=True).count()
    activities=db.query(UserActivity).filter_by(user_id=user.id,activity_type="ARTICLE_READ").all()
    articles_read=len({(a.metadata_json or {}).get("article_id") for a in activities if (a.metadata_json or {}).get("article_id")})
    revisions=db.query(func.coalesce(func.sum(UserRevision.review_count),0)).filter_by(user_id=user.id).scalar()
    by_category=defaultdict(lambda:[0,0])
    for row in attempts:
        question=db.get(QuizQuestion,row.question_id);article=db.get(Article,question.article_id) if question else None
        if article:by_category[article.category][0]+=int(row.is_correct);by_category[article.category][1]+=1
    ordered=sorted(by_category,key=lambda c:by_category[c][0]/by_category[c][1],reverse=True)
    return {"id":profile.id,"display_name":profile.display_name,"email":profile.email,"avatar_url":profile.avatar_url,
        "target_exam":profile.target_exam,"target_year":profile.target_year,"preferred_subjects":profile.preferred_subjects or [],
        "onboarding_complete":profile.onboarding_complete,"current_streak":profile.current_streak,"longest_streak":profile.longest_streak,
        "last_activity_date":str(profile.last_activity_date) if profile.last_activity_date else None,"articles_read":articles_read,
        "quizzes_completed":quizzes,"questions_answered":questions_answered,"quiz_accuracy":accuracy,"articles_saved":saved,
        "revisions_completed":int(revisions or 0),"strongest_subjects":ordered[:2],"weakest_subjects":list(reversed(ordered[-2:])) if len(ordered)>1 else ordered}

@app.get("/api/me")
@app.get("/api/profile")
def me(db:Session=Depends(get_db),user:AuthUser=Depends(current_user)):
    result=get_profile_stats(db,user);db.commit();return result

@app.patch("/api/me/profile")
def update_profile(data:ProfileUpdate,db:Session=Depends(get_db),user:AuthUser=Depends(current_user)):
    profile=profile_for_update(db,user);profile.display_name=data.display_name.strip();profile.target_exam=data.target_exam
    profile.target_year=data.target_year;profile.preferred_subjects=data.preferred_subjects;profile.onboarding_complete=True
    profile.updated_at=datetime.now(timezone.utc);db.commit();return get_profile_stats(db,user)

def require_cron_secret(secret: str | None = Header(default=None, alias="X-Cron-Secret")) -> None:
    expected = os.getenv("CRON_SECRET", "")
    if not expected:
        raise HTTPException(503, "Scheduled ingestion is not configured")
    if not secret or not hmac.compare_digest(secret, expected):
        raise HTTPException(401, "Invalid scheduler credential")

def ingestion_run_json(run: IngestionRun) -> dict:
    return {"id": run.id, "status": run.status, "triggered_by": run.triggered_by,
            "started_at": run.started_at, "finished_at": run.finished_at, "duration_ms": run.duration_ms,
            "sources_configured": run.sources_configured, "sources_succeeded": run.sources_succeeded,
            "candidates": run.candidates, "ignored": run.ignored, "deduplicated": run.deduplicated,
            "processed": run.processed, "failed": run.failed, "queued": run.queued, "errors": run.errors or []}

@app.post("/api/ingest/run", status_code=202)
def start_ingestion(background: BackgroundTasks, db: Session = Depends(get_db), _: None = Depends(require_cron_secret)):
    active = db.query(IngestionRun).filter(IngestionRun.status.in_(["PENDING", "PROCESSING"])).first()
    if active:
        return {"id": active.id, "status": active.status, "already_running": True}
    run = IngestionRun(status="PENDING", triggered_by="github-actions")
    db.add(run); db.commit(); db.refresh(run)
    background.add_task(run_ingestion, run.id)
    return {"id": run.id, "status": run.status, "already_running": False}

@app.get("/api/ingest/runs/{run_id}")
def get_ingestion_run(run_id: int, db: Session = Depends(get_db), _: None = Depends(require_cron_secret)):
    run = db.get(IngestionRun, run_id)
    if not run: raise HTTPException(404, "Ingestion run not found")
    return ingestion_run_json(run)

@app.post("/api/ingest",status_code=202)
def ingest(data:IngestIn,background:BackgroundTasks,db:Session=Depends(get_db),_:AuthUser=Depends(require_admin)):
    source_url = canonicalize_url(str(data.source_url)) if data.source_url else None
    digest = sha256(data.content.encode()).hexdigest()
    duplicate_conditions = [Article.content_hash == digest]
    if source_url:
        duplicate_conditions.extend((Article.canonical_url == source_url, Article.source_url == source_url))
    existing = db.query(Article).filter(or_(*duplicate_conditions)).first()
    if existing:return {"id":existing.id,"processing_status":existing.processing_status,"duplicate":True}
    published = datetime.fromisoformat(data.published_at.replace("Z", "+00:00")) if data.published_at else datetime.now(timezone.utc)
    score, relevance, category = classify_relevance(data.title, data.content)
    article=Article(title=data.title,original_title=data.title,source=data.source,source_url=source_url,canonical_url=source_url,
        published_at=utc_naive(published),ingested_at=datetime.now(timezone.utc).replace(tzinfo=None),category=category or "Unclassified",
        summary=data.content[:6000],what_happened=data.content[:6000],why_it_matters="",upsc_relevance="",processing_status="PENDING",
        raw_content=data.content[:12000],content_hash=digest,event_fingerprint=event_fingerprint(data.title,published),relevance_score=score,
        relevance_category=relevance)
    if relevance == "LOW": article.processing_status = "IGNORED"
    db.add(article);db.commit();db.refresh(article)
    if article.processing_status == "PENDING": background.add_task(process_article, article.id)
    return {"id":article.id,"processing_status":article.processing_status,"duplicate":False}

def process_stored_article_by_id(article_id: int) -> None:
    with SessionLocal() as db:
        article = db.get(Article, article_id)
        if article: process_stored_article(db, article)

def process_article(article_id: int) -> None:
    """Compatibility entry point for the protected one-off admin ingestion route."""
    process_stored_article_by_id(article_id)
