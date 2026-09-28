from collections import defaultdict, deque
from datetime import date, datetime, timezone, timedelta
from hashlib import sha256
import os
from threading import Lock
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, joinedload

from .auth import AuthUser, current_user, require_admin
from .database import Base, engine, get_db
from .models import (Article, ArticleGSTag, ArticleTopic, DailyQuizAttempt, KeyFact, Profile,
    QuizOption, QuizQuestion, UserActivity, UserBookmark, UserQuizAttempt, UserRevision)
from .schemas import ArticleIn, AttemptIn, IngestIn, ProfileUpdate, RevisionIn
from .services.llm import MockProvider, get_provider, process_with_retry
from .services.streaks import streak_metrics

Base.metadata.create_all(bind=engine)
app=FastAPI(title="Prashna API",version="2.0.0")
cors_origins=[x.strip() for x in os.getenv("CORS_ORIGINS","http://localhost:5173,http://127.0.0.1:5173").split(",") if x.strip()]
app.add_middleware(CORSMiddleware,allow_origins=cors_origins,allow_methods=["GET","POST","PATCH","DELETE","OPTIONS"],allow_headers=["Authorization","Content-Type","X-User-Timezone"],max_age=600)

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
    return {"id":article.id,"title":article.title,"source":article.source,"source_url":article.source_url,
        "published_at":article.published_at,"category":article.category,"summary":article.summary,
        "why_it_matters":article.why_it_matters,"upsc_relevance":article.upsc_relevance,
        "topics":[row.topic for row in article.topics],"gs_papers":[row.gs_paper for row in article.gs_tags],
        "key_facts":[row.fact for row in article.facts],"prelims_points":article.prelims_points or [],
        "mains_angles":article.mains_angles or [],"processing_status":article.processing_status,
        "processing_model":article.processing_model,"processed_at":article.processed_at}

def article_query(db:Session):
    return db.query(Article).options(joinedload(Article.topics),joinedload(Article.gs_tags),joinedload(Article.facts))

@app.get("/api/health")
def health():return {"status":"ok"}

@app.get("/api/feed")
def feed(category:str|None=None,limit:int=Query(30,ge=1,le=100),db:Session=Depends(get_db)):
    query=article_query(db)
    if category:query=query.filter(func.lower(Article.category)==category.lower())
    return [article_json(a) for a in query.order_by(Article.published_at.desc()).limit(limit).all()]

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

@app.post("/api/ingest",status_code=202)
def ingest(data:IngestIn,background:BackgroundTasks,db:Session=Depends(get_db),_:AuthUser=Depends(require_admin)):
    digest=sha256(data.content.encode()).hexdigest()
    existing=db.query(Article).filter(or_(Article.content_hash==digest,Article.source_url==str(data.source_url) if data.source_url else False)).first()
    if existing:return {"id":existing.id,"processing_status":existing.processing_status,"duplicate":True}
    article=Article(title=data.title,source=data.source,source_url=str(data.source_url) if data.source_url else None,published_at=datetime.fromisoformat(data.published_at.replace("Z","+00:00")) if data.published_at else datetime.now(timezone.utc),category="Governance",summary=data.content[:1000],why_it_matters="Editorial processing pending.",upsc_relevance="",processing_status="PENDING",raw_content=data.content,content_hash=digest)
    db.add(article)
    try:db.commit()
    except Exception:
        db.rollback();existing=db.query(Article).filter_by(content_hash=digest).first()
        if existing:return {"id":existing.id,"processing_status":existing.processing_status,"duplicate":True}
        raise
    db.refresh(article);background.add_task(process_article,article.id)
    return {"id":article.id,"processing_status":article.processing_status,"duplicate":False}

_ingestion_times=deque();_ingestion_lock=Lock()
def process_article(article_id:int)->None:
    now=time.monotonic()
    with _ingestion_lock:
        while _ingestion_times and now-_ingestion_times[0]>60:_ingestion_times.popleft()
        if len(_ingestion_times)>=5:
            db=next(get_db());article=db.get(Article,article_id)
            if article:article.processing_status="FAILED";article.processing_error="Local ingestion rate limit reached; retry later.";db.commit()
            db.close();return
        _ingestion_times.append(now)
    db=next(get_db())
    try:
        article=db.get(Article,article_id)
        if not article or article.processing_status=="COMPLETED":return
        article.processing_status="PROCESSING";db.commit()
        provider=get_provider()
        try:result=process_with_retry(provider,article.title,article.source,article.raw_content or "")
        except Exception as error:
            provider=MockProvider();result=provider.process(article.title,article.source,article.raw_content or "")
            article.processing_error=str(error)[:1000]
        article.title=str(result.get("title") or article.title)[:300]
        article.summary=str(result.get("summary") or article.raw_content or "")
        article.why_it_matters=str(result.get("why_it_matters") or "")
        article.upsc_relevance=str(result.get("upsc_relevance") or "")
        article.prelims_points=result.get("prelims_points") or [];article.mains_angles=result.get("mains_angles") or []
        article.topics=[ArticleTopic(topic=str(x)[:150]) for x in result.get("topics",[])[:20]]
        article.gs_tags=[ArticleGSTag(gs_paper=str(x)[:30]) for x in result.get("gs_papers",[])[:8]]
        article.facts=[KeyFact(fact=str(x)[:2000]) for x in result.get("key_facts",[])[:12]]
        for item in result.get("quiz_questions",[])[:5]:
            options=item.get("options",[]);correct_index=item.get("answer_index",0)
            question=QuizQuestion(article_id=article.id,question=str(item.get("question","")),question_type=str(item.get("question_type","mcq")),explanation=str(item.get("explanation","")))
            question.options=[QuizOption(option_text=str(opt.get("text",opt)) if isinstance(opt,dict) else str(opt),is_correct=(i==correct_index or (isinstance(opt,dict) and opt.get("is_correct",False)))) for i,opt in enumerate(options)]
            if question.question and question.options:article.quiz_questions.append(question)
        article.processing_model=provider.name;article.processed_at=datetime.now(timezone.utc);article.processing_status="COMPLETED";article.raw_content=None;db.commit()
    except Exception as error:
        db.rollback();article=db.get(Article,article_id)
        if article:article.processing_status="FAILED";article.processing_error=str(error)[:1000];db.commit()
    finally:db.close()
