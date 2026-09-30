import { useEffect, useState } from 'react';
import { AlertCircle, ArrowLeft, ArrowUpRight, Atom, BookOpen, Brain, Building2, Check, CheckCircle2, ChevronRight, Clock3, Compass, Globe2, Landmark, Leaf, Palette, RefreshCw, RotateCcw, Scale, Shield, Users, XCircle } from 'lucide-react';
import { api } from '../services/api';

type Subject = { id: number; name: string; slug: string; description: string; icon: string; color: string; topic_count: number; completed_topics: number; progress_percent: number };
type Topic = { id: number; name: string; slug: string; description: string; completed: boolean };
type Content = { id: number; title: string; summary: string; body: string; estimated_minutes: number; source: string };
type TopicDetail = Topic & { subject: { name: string; slug: string }; content: Content[]; children: Topic[]; question_count: number; reading_completed: boolean; practice_attempted: number; practice_completed: boolean; progress_percent: number };
type PracticeQuestion = { id: number; question_text: string; difficulty: string; question_type: string; source: string; options: { id: number; text: string }[] };

const icons: Record<string, any> = { newspaper: BookOpen, landmark: Landmark, history: Landmark, 'globe-2': Globe2, 'chart-no-axes-combined': Compass, leaf: Leaf, atom: Atom, palette: Palette, globe: Globe2, users: Users, 'building-2': Building2, shield: Shield, scale: Scale, brain: Brain };

export default function Subjects({ notify, onCurrentAffairs, initialTopicSlug }: { notify: (message: string) => void; onCurrentAffairs: () => void; initialTopicSlug?: string | null }) {
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [activeSubject, setActiveSubject] = useState<(Subject & { topics: Topic[] }) | null>(null);
  const [activeTopic, setActiveTopic] = useState<TopicDetail | null>(null);
  const [practiceMode, setPracticeMode] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadSubjects = async () => {
    setLoading(true); setError('');
    try { setSubjects(await api<Subject[]>('/api/subjects')); }
    catch (e) { setError(e instanceof Error ? e.message : 'Subjects could not be loaded.'); }
    finally { setLoading(false); }
  };
  useEffect(() => { void loadSubjects(); }, []);
  useEffect(() => {
    if (!initialTopicSlug) return;
    let active = true;
    setLoading(true);
    api<TopicDetail>(`/api/topics/${initialTopicSlug}`).then(topic => { if (active) { setActiveTopic(topic); setActiveSubject(null); setPracticeMode(false); } })
      .catch(e => { if (active) setError(e instanceof Error ? e.message : 'This topic could not be loaded.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [initialTopicSlug]);

  const openSubject = async (subject: Subject) => {
    if (subject.slug === 'current-affairs') { onCurrentAffairs(); return; }
    setLoading(true); setError('');
    try { setActiveSubject(await api(`/api/subjects/${subject.slug}`)); setActiveTopic(null); }
    catch (e) { setError(e instanceof Error ? e.message : 'This subject could not be loaded.'); }
    finally { setLoading(false); }
  };
  const openTopic = async (topic: Topic) => {
    setLoading(true); setError('');
    try { setPracticeMode(false); setActiveTopic(await api(`/api/topics/${topic.slug}`)); }
    catch (e) { setError(e instanceof Error ? e.message : 'This topic could not be loaded.'); }
    finally { setLoading(false); }
  };
  const markComplete = async () => {
    if (!activeTopic) return;
    try {
      await api(`/api/topics/${activeTopic.slug}/complete`, { method: 'POST' });
      setActiveTopic({ ...activeTopic, completed: true });
      if (activeSubject) {
        const updated = await api<any>(`/api/subjects/${activeSubject.slug}`);
        setActiveSubject(updated);
      }
      await loadSubjects();
      notify('Topic marked complete');
    } catch (e) { notify(e instanceof Error ? e.message : 'Progress could not be saved.'); }
  };
  const markReadingComplete = async () => {
    if (!activeTopic || activeTopic.reading_completed) return;
    try {
      await api(`/api/topics/${activeTopic.slug}/reading-complete`, { method: 'POST' });
      setActiveTopic({ ...activeTopic, reading_completed: true, progress_percent: activeTopic.completed ? 100 : Math.round((50 + (activeTopic.question_count ? activeTopic.practice_attempted / activeTopic.question_count * 50 : 0))) });
      notify('Reading marked complete');
    } catch (e) { notify(e instanceof Error ? e.message : 'Reading progress could not be saved.'); }
  };
  const refreshActiveTopic = async () => {
    if (!activeTopic) return;
    try { setActiveTopic(await api(`/api/topics/${activeTopic.slug}`)); }
    catch { /* Keep the already loaded topic and its result visible. */ }
  };

  const back = () => { if (practiceMode) setPracticeMode(false); else if (activeTopic) setActiveTopic(null); else if (activeSubject) setActiveSubject(null); };
  if (loading && !subjects.length && !activeSubject && !activeTopic) return <section className="learning-page"><div className="learning-loading"><RefreshCw className="spinning"/> Loading your subjects…</div></section>;
  if (error && !subjects.length && !activeSubject && !activeTopic) return <section className="learning-page"><div className="learning-error"><b>Subjects are unavailable</b><span>{error}</span><button className="outline-btn" onClick={loadSubjects}>Try again</button></div></section>;

  return <section className="learning-page">
    {(activeSubject || activeTopic) && !practiceMode && <button className="learning-back" onClick={back}><ArrowLeft size={16}/>{activeTopic ? activeTopic.subject.name : 'All subjects'}</button>}
    {activeTopic && practiceMode ? <PracticeFlow topicSlug={activeTopic.slug} topicName={activeTopic.name} readingCompleted={activeTopic.reading_completed} onBack={() => { setPracticeMode(false); void refreshActiveTopic(); }} /> : activeTopic ? <>
      <div className="learning-eyebrow">{activeTopic.subject.name.toUpperCase()} · TOPIC</div>
      <div className="learning-title-row"><div><h1>{activeTopic.name}<span className="brand-dot">.</span></h1><p>{activeTopic.description}</p></div><span className={'completion-chip '+(activeTopic.completed?'complete':'')}>{activeTopic.completed ? <><Check size={14}/> Completed</> : 'In progress'}</span></div>
      <div className="topic-progress-panel"><div className="topic-progress-heading"><div><span>LEARNING PROGRESS</span><b>{activeTopic.progress_percent}%</b></div><div className="topic-progress-track"><i style={{ width: `${activeTopic.progress_percent}%` }}/></div></div><div className="topic-progress-states"><span className={activeTopic.reading_completed?'is-done':''}><CheckCircle2 size={15}/> Reading {activeTopic.reading_completed?'complete':'not complete'}</span><span className={activeTopic.practice_completed?'is-done':''}><Brain size={15}/> Practice {activeTopic.practice_attempted}/{activeTopic.question_count}</span></div><small>Progress combines reading completion (50%) and distinct practice questions attempted (50%).</small></div>
      <div className="topic-learning-actions"><div><b>{activeTopic.content.length} {activeTopic.content.length === 1 ? 'lesson' : 'lessons'}</b><span>{activeTopic.question_count} practice questions available</span></div><div><button className="outline-btn" onClick={() => document.getElementById('topic-lessons')?.scrollIntoView({ behavior: 'smooth' })} disabled={!activeTopic.content.length}>Start learning</button><button className="dark-button" onClick={() => setPracticeMode(true)} disabled={!activeTopic.question_count}>Practice {Math.min(5, activeTopic.question_count)} questions <ChevronRight size={15}/></button></div></div>
      {!activeTopic.question_count && <div className="learning-inline-error">Practice questions are not available for this topic yet.</div>}
      {activeTopic.children.length > 0 && <div className="learning-subtopics">{activeTopic.children.map(child => <button key={child.slug} onClick={() => openTopic(child)}>{child.name}<ChevronRight size={15}/></button>)}</div>}
      {activeTopic.content.length ? <div id="topic-lessons">{activeTopic.content.map(item => <article className="lesson-card" key={item.id}>
        <div className="lesson-meta"><span className="demo-chip">DEMO LESSON</span><span><Clock3 size={14}/> {item.estimated_minutes} min</span></div>
        <h2>{item.title}</h2><p className="lesson-summary">{item.summary}</p>
        <div className="lesson-body">{item.body.split(/\n\n+/).map((part, index) => part.startsWith('## ')
          ? <h3 key={index}>{part.slice(3)}</h3>
          : <p key={index}>{part.replace(/\*\*/g, '')}</p>)}</div>
        <div className="lesson-source">{item.source} · Sample content for demonstration; not official UPSC material.</div>
      </article>)}<button className="learning-complete reading-complete" onClick={markReadingComplete} disabled={activeTopic.reading_completed}>{activeTopic.reading_completed ? <><Check size={17}/> Reading complete</> : <>Mark reading complete <CheckCircle2 size={16}/></>}</button></div> : <div className="learning-empty"><BookOpen size={23}/><b>Learning material is on the way</b><span>This topic is in the catalog. Lessons will be added in a later content phase.</span></div>}
      <button className="learning-complete" onClick={markComplete} disabled={activeTopic.completed}>{activeTopic.completed ? <><Check size={17}/> Topic completed</> : <>Mark topic complete <ArrowUpRight size={16}/></>}</button>
    </> : activeSubject ? <>
      <div className="learning-eyebrow">SUBJECT · {activeSubject.topic_count} TOPICS</div>
      <div className="learning-title-row"><div><h1>{activeSubject.name}<span className="brand-dot">.</span></h1><p>{activeSubject.description}</p></div><div className="learning-progress"><b>{activeSubject.progress_percent}%</b><span>complete</span></div></div>
      <div className="learning-progress-track"><i style={{ width: `${activeSubject.progress_percent}%` }}/></div>
      <div className="learning-section-title"><div><span className="learning-eyebrow">LEARNING PATH</span><h2>Topics</h2></div><span>{activeSubject.completed_topics} of {activeSubject.topic_count} complete</span></div>
      <div className="topic-list">{activeSubject.topics.map((topic, index) => <button className="topic-row" key={topic.slug} onClick={() => openTopic(topic)}><span className={'topic-number '+(topic.completed?'done':'')}>{topic.completed?<Check size={15}/>:String(index+1).padStart(2,'0')}</span><span className="topic-copy"><b>{topic.name}</b><small>{topic.description}</small></span><span className="topic-state">{topic.completed?'Complete':'Explore'}<ChevronRight size={15}/></span></button>)}</div>
    </> : <>
      <div className="learning-eyebrow">YOUR LEARNING SPACE · UPSC</div>
      <div className="learning-title-row"><div><h1>Choose a subject<span className="brand-dot">.</span></h1><p>Build understanding topic by topic, then come back to what you want to strengthen.</p></div></div>
      {error && <div className="learning-inline-error">{error}</div>}
      {loading ? <div className="learning-loading"><RefreshCw className="spinning"/> Refreshing progress…</div> : <div className="learning-subject-grid">{subjects.map(subject => { const Icon = icons[subject.icon] || BookOpen; const currentAffairs = subject.slug === 'current-affairs'; return <button className="learning-subject-card" key={subject.slug} onClick={() => openSubject(subject)}><span className="subject-icon" style={{ color: subject.color, background: `${subject.color}18` }}><Icon size={20}/></span><span className="subject-progress-label">{currentAffairs ? 'LIVE' : `${subject.progress_percent}%`}</span><h2>{subject.name}</h2><p>{subject.description}</p><div className="learning-progress-track"><i style={{ width: `${subject.progress_percent}%`, background: subject.color }}/></div><div className="subject-card-footer"><span>{currentAffairs ? 'Latest stories and analysis' : `${subject.completed_topics} / ${subject.topic_count} topics`}</span><span>{currentAffairs ? 'Open briefing' : 'Continue'} <ChevronRight size={14}/></span></div></button>; })}</div>}
      <div className="catalog-note"><BookOpen size={16}/><span>Small demo catalog to show the learning structure. More topics and lessons can be added without changing the subject model.</span></div>
    </>}
  </section>;
}

type AttemptResult = { attempt_id: number; is_correct: boolean; selected_option_id: number; selected_answer: string; correct_option_id: number; correct_answer: string; explanation: string };
type SessionAttempt = { question: PracticeQuestion; result: AttemptResult };

function PracticeFlow({ topicSlug, topicName, readingCompleted, onBack }: { topicSlug: string; topicName: string; readingCompleted: boolean; onBack: () => void }) {
  const [questions, setQuestions] = useState<PracticeQuestion[]>([]);
  const [attempts, setAttempts] = useState<SessionAttempt[]>([]);
  const [index, setIndex] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const [submission, setSubmission] = useState<AttemptResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [reviewMode, setReviewMode] = useState(false);
  const [showResults, setShowResults] = useState(false);

  const start = async () => {
    setLoading(true); setError(''); setQuestions([]); setAttempts([]); setIndex(0);
    setSelected(null); setSubmission(null); setReviewMode(false); setShowResults(false);
    try {
      const rows = await api<PracticeQuestion[]>(`/api/topics/${topicSlug}/questions`);
      const shuffled = [...rows].sort(() => Math.random() - 0.5).slice(0, 5);
      setQuestions(shuffled);
    } catch (e) { setError(e instanceof Error ? e.message : 'Practice questions could not be loaded.'); }
    finally { setLoading(false); }
  };
  useEffect(() => { void start(); }, [topicSlug]);

  const question = questions[index];
  const complete = showResults && questions.length > 0 && attempts.length === questions.length;
  const mistakes = attempts.filter(attempt => !attempt.result.is_correct);
  const submit = async () => {
    if (!question || selected === null || submission || submitting) return;
    setSubmitting(true); setError('');
    try {
      const result = await api<AttemptResult>(`/api/questions/${question.id}/attempt`, {
        method: 'POST', body: JSON.stringify({ option_id: selected }),
      });
      setSubmission(result); setAttempts(previous => [...previous, { question, result }]);
    } catch (e) { setError(e instanceof Error ? e.message : 'Your answer could not be submitted.'); }
    finally { setSubmitting(false); }
  };
  const next = () => {
    if (index + 1 >= questions.length) { setShowResults(true); return; }
    setIndex(value => value + 1); setSelected(null); setSubmission(null);
  };

  return <div className="practice-flow">
    <button className="learning-back" onClick={onBack}><ArrowLeft size={16}/>{topicName}</button>
    {reviewMode ? <>
      <div className="learning-eyebrow">REVIEW · {topicName.toUpperCase()}</div><div className="learning-title-row"><div><h1>Review mistakes<span className="brand-dot">.</span></h1><p>Revisit the questions you missed and the reasoning behind each answer.</p></div></div>
      {mistakes.length ? mistakes.map(({ question: missed, result }, mistakeIndex) => <article className="mistake-card" key={result.attempt_id}><span className="mistake-count">QUESTION {mistakeIndex + 1} · {missed.source}</span><h2>{missed.question_text}</h2><p><b>Your answer</b><span>{result.selected_answer}</span></p><p className="answer-correct"><b>Correct answer</b><span>{result.correct_answer}</span></p><div className="mistake-explanation"><b>Why?</b><span>{result.explanation}</span></div></article>) : <div className="learning-empty"><CheckCircle2 size={22}/><b>No mistakes to review</b><span>Great work. Every answer in this practice was correct.</span></div>}
      <button className="outline-btn" onClick={() => setReviewMode(false)}>Back to results</button>
    </> : complete ? <>
      <div className="practice-complete-icon"><CheckCircle2 size={28}/></div><div className="learning-eyebrow">PRACTICE COMPLETE</div><div className="learning-title-row"><div><h1>Nice work<span className="brand-dot">.</span></h1><p>You finished this {topicName} practice set.</p></div></div>
      <div className="practice-score-card"><div className="practice-score"><b>{attempts.filter(attempt => attempt.result.is_correct).length} / {questions.length}</b><span>{Math.round(attempts.filter(attempt => attempt.result.is_correct).length / questions.length * 100)}% accuracy</span></div><div className="practice-score-stats"><span><CheckCircle2 size={16}/> Correct <b>{attempts.filter(attempt => attempt.result.is_correct).length}</b></span><span><XCircle size={16}/> Incorrect <b>{mistakes.length}</b></span><span><Brain size={16}/> Answered <b>{attempts.length}/{questions.length}</b></span><span><BookOpen size={16}/> Reading <b>{readingCompleted?'Complete':'Not complete'}</b></span></div></div>
      <div className="practice-result-actions"><button className="outline-btn" onClick={() => setReviewMode(true)} disabled={!mistakes.length}>Review mistakes <ChevronRight size={15}/></button><button className="dark-button" onClick={() => void start()}><RotateCcw size={15}/> Practice again</button><button className="practice-back-link" onClick={onBack}>Back to topic</button></div>
    </> : loading ? <div className="learning-loading"><RefreshCw className="spinning"/> Preparing your practice…</div>
      : error && !questions.length ? <div className="learning-error"><AlertCircle size={20}/><b>Practice is unavailable</b><span>{error}</span><button className="outline-btn" onClick={() => void start()}>Try again</button></div>
      : !questions.length ? <div className="learning-empty"><BookOpen size={22}/><b>No practice questions yet</b><span>Questions for this topic will appear here when they are ready.</span><button className="outline-btn" onClick={onBack}>Back to topic</button></div>
      : question && <>
        <div className="practice-header"><div><div className="learning-eyebrow">PRACTICE · {topicName.toUpperCase()}</div><h1>Question {index + 1}<span> / {questions.length}</span></h1></div><span className="demo-chip">DEMO QUESTIONS</span></div>
        <div className="practice-progress"><i style={{ width: `${(index + (submission ? 1 : 0)) / questions.length * 100}%` }}/></div>
        <article className="practice-question-card"><span className="practice-difficulty">{question.difficulty}</span><h2>{question.question_text}</h2><div className="practice-options">{question.options.map((option, optionIndex) => {
          const isSelected = selected === option.id;
          const isCorrect = submission?.correct_option_id === option.id;
          const isWrongSelection = !!submission && isSelected && !submission.is_correct;
          return <button key={option.id} className={'practice-option '+(isSelected?'selected ':'')+(submission&&isCorrect?'correct ':'')+(isWrongSelection?'incorrect ':'')} disabled={!!submission || submitting} onClick={() => setSelected(option.id)}><span className="practice-option-letter">{String.fromCharCode(65 + optionIndex)}</span><span>{option.text}</span>{submission&&isCorrect&&<CheckCircle2 size={17}/>} {isWrongSelection&&<XCircle size={17}/>}</button>;
        })}</div>
        {error && <p className="practice-inline-error">{error}</p>}
        {submission && <div className={'practice-feedback '+(submission.is_correct?'is-correct':'is-incorrect')}><b>{submission.is_correct?'Correct':'Not quite'}</b><span>{submission.explanation}</span></div>}
        {!submission ? <button className="dark-button practice-check" disabled={selected===null||submitting} onClick={submit}>{submitting?'Checking…':'Check answer'} <ChevronRight size={16}/></button> : <button className="dark-button practice-check" onClick={next}>{index + 1 < questions.length?'Next question':'See results'} <ChevronRight size={16}/></button>}
      </article>
    </>}
  </div>;
}
