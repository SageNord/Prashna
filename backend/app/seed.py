from datetime import datetime, timezone
from .database import SessionLocal
from .models import Article,ArticleTopic,ArticleGSTag,KeyFact,QuizQuestion,QuizOption
from . import _seeddata
def seed():
    db=SessionLocal()
    try:
        # Safe for local setup and deploy retries: never erase user progress or replace live content.
        if db.query(Article).count():
            print("Articles already exist; leaving content and user data untouched")
            return
        lenses=("Institutions and implementation","Challenges and way forward")
        for i,item in enumerate(_seeddata.ITEMS):
            title=item[2] if i<12 else f"{item[2]} — {lenses[(i//12)-1]}"
            a=Article(title=title,category=item[0],source="Prashna Editorial Learning Sample",source_url=None,published_at=datetime.now(timezone.utc),summary=item[3],why_it_matters=item[4],upsc_relevance=item[5],processing_status="SAMPLE",relevance_category="LOW",relevance_score=0)
            a.topics=[ArticleTopic(topic=item[1])];a.gs_tags=[ArticleGSTag(gs_paper=item[5])];a.facts=[KeyFact(fact=f"Connect this issue with {item[1].lower()} in the syllabus."),KeyFact(fact="Consider implementation challenges alongside policy intent."),KeyFact(fact="Use a balanced perspective: outcomes depend on institutions and context.")]
            db.add(a);db.flush();q=QuizQuestion(article_id=a.id,question=f"Which syllabus topic is most closely connected to {title}?",question_type="mcq",explanation=f"This sample is primarily relevant to {item[5]}, especially {item[1]}.")
            q.options=[QuizOption(option_text=item[1],is_correct=True),QuizOption(option_text="Ancient Indian architecture",is_correct=False),QuizOption(option_text="Medieval trade routes",is_correct=False),QuizOption(option_text="Literary criticism",is_correct=False)];db.add(q)
        db.commit();print(f"Seeded {len(_seeddata.ITEMS)} demo articles and questions")
    finally:db.close()
if __name__=="__main__":seed()
