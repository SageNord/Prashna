import { useEffect, useState } from 'react';
import { AlertCircle, BookOpen, CheckCircle2, ChevronRight, RefreshCw, Target } from 'lucide-react';
import { api } from '../services/api';

type ProgressData = {
  topics_completed: number; topics_in_progress: number; practice_questions_attempted: number; practice_accuracy: number;
  recently_completed: { id: number; name: string; slug: string; completed_at: string }[];
  weak_topics: { id: number; name: string; slug: string; questions_attempted: number; attempts: number; accuracy: number }[]; review_mistakes_count: number;
};
type Mistake = { id: number; question_text: string; selected_answer: string; correct_answer: string; explanation: string; topic: string; topic_slug: string; source: string; attempted_at: string };

export default function Progress({ onOpenTopic }: { onOpenTopic: (slug: string) => void }) {
  const [data, setData] = useState<ProgressData | null>(null);
  const [mistakes, setMistakes] = useState<Mistake[]>([]);
  const [reviewing, setReviewing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  useEffect(() => { let active = true; Promise.all([api<ProgressData>('/api/me/progress'), api<Mistake[]>('/api/me/question-attempts?mistakes_only=true&limit=100')])
    .then(([summary, rows]) => { if (active) { setData(summary); setMistakes(rows); } })
    .catch(e => { if (active) setError(e instanceof Error ? e.message : 'Progress could not be loaded.'); })
    .finally(() => { if (active) setLoading(false); }); return () => { active = false; } }, []);

  if (loading) return <section className="other-page"><div className="learning-loading"><RefreshCw className="spinning"/> Loading your progress…</div></section>;
  if (error || !data) return <section className="other-page"><div className="learning-error"><AlertCircle size={20}/><b>Progress is unavailable</b><span>{error || 'Please try again.'}</span></div></section>;
  return <section className="other-page progress-page">
    <div className="learning-eyebrow">YOUR LEARNING JOURNEY</div><h1>Progress<span className="brand-dot">.</span></h1><p className="page-sub">A clear view of what you have learned and what to revisit.</p>
    <div className="progress-stats"><article><BookOpen/><b>{data.topics_completed}</b><span>Topics completed</span></article><article><Target/><b>{data.topics_in_progress}</b><span>In progress</span></article><article><CheckCircle2/><b>{data.practice_questions_attempted}</b><span>Questions attempted</span></article><article><Target/><b>{data.practice_accuracy}%</b><span>Practice accuracy</span></article></div>
    <div className="progress-columns"><div className="progress-panel"><div className="learning-section-title"><div><div className="learning-eyebrow">KEEP GOING</div><h2>Recently completed</h2></div></div>
      {data.recently_completed.length ? data.recently_completed.map(topic => <button className="progress-topic-row" key={topic.id} onClick={() => onOpenTopic(topic.slug)}><span><CheckCircle2 size={17}/></span><b>{topic.name}</b><small>{new Date(topic.completed_at).toLocaleDateString()}</small><ChevronRight size={15}/></button>) : <div className="progress-empty">Complete a topic to see it here.</div>}
    </div><div className="progress-panel"><div className="learning-section-title"><div><div className="learning-eyebrow">BASED ON YOUR ANSWERS</div><h2>Needs revision</h2></div></div>
      {data.weak_topics.length ? data.weak_topics.map(topic => <button className="progress-topic-row weak" key={topic.id} onClick={() => onOpenTopic(topic.slug)}><span><Target size={17}/></span><b>{topic.name}</b><small>{topic.accuracy}% · {topic.questions_attempted} questions, {topic.attempts} attempts</small><ChevronRight size={15}/></button>) : <div className="progress-empty">No topics meet the revision rule yet. A topic appears after at least 3 distinct questions and accuracy below 60%.</div>}
    </div></div>
    <div className="progress-panel mistakes-panel"><div className="learning-section-title"><div><div className="learning-eyebrow">LEARN FROM EACH ATTEMPT</div><h2>Mistake review <span className="count-badge">{data.review_mistakes_count}</span></h2></div><button className="outline-btn" onClick={() => setReviewing(!reviewing)} disabled={!mistakes.length}>{reviewing ? 'Hide review' : 'Review mistakes'} <ChevronRight size={15}/></button></div>
      {reviewing && <div className="mistake-review-list">{mistakes.map(row => <article className="mistake-card" key={row.id}><span className="mistake-count">{row.topic.toUpperCase()} · {row.source}</span><h2>{row.question_text}</h2><p><b>Your answer</b><span>{row.selected_answer}</span></p><p className="answer-correct"><b>Correct answer</b><span>{row.correct_answer || 'Answer unavailable'}</span></p><div className="mistake-explanation"><b>Explanation</b><span>{row.explanation}</span></div><button className="practice-back-link" onClick={() => onOpenTopic(row.topic_slug)}>Study this topic <ChevronRight size={14}/></button></article>)}</div>}
      {!mistakes.length && <div className="progress-empty">No incorrect answers yet. Mistakes you make in topic practice will be available here.</div>}
    </div>
  </section>;
}
