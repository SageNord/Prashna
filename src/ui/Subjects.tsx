import { useEffect, useState } from 'react';
import { ArrowLeft, ArrowUpRight, Atom, BookOpen, Brain, Building2, Check, ChevronRight, Clock3, Compass, Globe2, Landmark, Leaf, Palette, RefreshCw, Scale, Shield, Users } from 'lucide-react';
import { api } from '../services/api';

type Subject = { id: number; name: string; slug: string; description: string; icon: string; color: string; topic_count: number; completed_topics: number; progress_percent: number };
type Topic = { id: number; name: string; slug: string; description: string; completed: boolean };
type Content = { id: number; title: string; summary: string; body: string; estimated_minutes: number; source: string };
type TopicDetail = Topic & { subject: { name: string; slug: string }; content: Content[]; children: Topic[] };

const icons: Record<string, any> = { newspaper: BookOpen, landmark: Landmark, history: Landmark, 'globe-2': Globe2, 'chart-no-axes-combined': Compass, leaf: Leaf, atom: Atom, palette: Palette, globe: Globe2, users: Users, 'building-2': Building2, shield: Shield, scale: Scale, brain: Brain };

export default function Subjects({ notify, onCurrentAffairs }: { notify: (message: string) => void; onCurrentAffairs: () => void }) {
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [activeSubject, setActiveSubject] = useState<(Subject & { topics: Topic[] }) | null>(null);
  const [activeTopic, setActiveTopic] = useState<TopicDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadSubjects = async () => {
    setLoading(true); setError('');
    try { setSubjects(await api<Subject[]>('/api/subjects')); }
    catch (e) { setError(e instanceof Error ? e.message : 'Subjects could not be loaded.'); }
    finally { setLoading(false); }
  };
  useEffect(() => { void loadSubjects(); }, []);

  const openSubject = async (subject: Subject) => {
    if (subject.slug === 'current-affairs') { onCurrentAffairs(); return; }
    setLoading(true); setError('');
    try { setActiveSubject(await api(`/api/subjects/${subject.slug}`)); setActiveTopic(null); }
    catch (e) { setError(e instanceof Error ? e.message : 'This subject could not be loaded.'); }
    finally { setLoading(false); }
  };
  const openTopic = async (topic: Topic) => {
    setLoading(true); setError('');
    try { setActiveTopic(await api(`/api/topics/${topic.slug}`)); }
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

  const back = () => { if (activeTopic) setActiveTopic(null); else if (activeSubject) setActiveSubject(null); };
  if (loading && !subjects.length && !activeSubject && !activeTopic) return <section className="learning-page"><div className="learning-loading"><RefreshCw className="spinning"/> Loading your subjects…</div></section>;
  if (error && !subjects.length && !activeSubject && !activeTopic) return <section className="learning-page"><div className="learning-error"><b>Subjects are unavailable</b><span>{error}</span><button className="outline-btn" onClick={loadSubjects}>Try again</button></div></section>;

  return <section className="learning-page">
    {(activeSubject || activeTopic) && <button className="learning-back" onClick={back}><ArrowLeft size={16}/>{activeTopic ? activeTopic.subject.name : 'All subjects'}</button>}
    {activeTopic ? <>
      <div className="learning-eyebrow">{activeTopic.subject.name.toUpperCase()} · TOPIC</div>
      <div className="learning-title-row"><div><h1>{activeTopic.name}<span className="brand-dot">.</span></h1><p>{activeTopic.description}</p></div><span className={'completion-chip '+(activeTopic.completed?'complete':'')}>{activeTopic.completed ? <><Check size={14}/> Completed</> : 'In progress'}</span></div>
      {activeTopic.children.length > 0 && <div className="learning-subtopics">{activeTopic.children.map(child => <button key={child.slug} onClick={() => openTopic(child)}>{child.name}<ChevronRight size={15}/></button>)}</div>}
      {activeTopic.content.length ? activeTopic.content.map(item => <article className="lesson-card" key={item.id}>
        <div className="lesson-meta"><span className="demo-chip">DEMO LESSON</span><span><Clock3 size={14}/> {item.estimated_minutes} min</span></div>
        <h2>{item.title}</h2><p className="lesson-summary">{item.summary}</p>
        <div className="lesson-body">{item.body.split(/\n\n+/).map((part, index) => part.startsWith('## ')
          ? <h3 key={index}>{part.slice(3)}</h3>
          : <p key={index}>{part.replace(/\*\*/g, '')}</p>)}</div>
        <div className="lesson-source">{item.source} · Sample content for demonstration; not official UPSC material.</div>
      </article>) : <div className="learning-empty"><BookOpen size={23}/><b>Learning material is on the way</b><span>This topic is in the catalog. Lessons will be added in a later content phase.</span></div>}
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
