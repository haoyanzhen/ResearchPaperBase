import { useEffect, useRef, useState } from 'react';

type Session = { id: string; title: string; latest_knowledge_version_id: string; no_project_evidence: boolean };
type Project = { id: string; status: string; default_knowledge_version_id: string | null };
type Props = {
  project: Project; actor: string;
  api: <T>(url: string, init?: RequestInit) => Promise<T>;
  envelope: <T>(url: string, init?: RequestInit) => Promise<{ data: T; meta: { next_cursor: string | null; has_more: boolean } }>;
  write: <T>(url: string, body: unknown, key?: string, actor?: string) => Promise<T>;
  onAuthFailure: (error: unknown) => void;
};

export function ResearchSessions({ project, actor, api, envelope, write, onAuthFailure }: Props) {
  const root = `/api/v1/projects/${project.id}/research-sessions`;
  const storageKey = `rpb-research:${actor}:${project.id}`;
  const [items, setItems] = useState<Session[]>([]);
  const [current, setCurrent] = useState<Session | null>(null);
  const [title, setTitle] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState(false);
  const [cursor, setCursor] = useState<string | null>(null);
  const pending = useRef<{ key: string; body: { title: string } } | null>(null);
  const mounted = useRef(true);
  const requestNumber = useRef(0);
  const openNumber = useRef(0);
  const opening = useRef(false);
  const accessEpoch = useRef(0);
  const headers = { 'X-Expected-Actor': actor };

  function failed(reason: unknown) {
    const code = (reason as { code?: string }).code;
    if (code?.startsWith('AUTH_')) onAuthFailure(reason);
    if (code === 'PERMISSION_RESOURCE_UNAVAILABLE' || code?.startsWith('AUTH_')) {
      accessEpoch.current++; requestNumber.current++; openNumber.current++;
      opening.current = false; pending.current = null;
      setCurrent(null); setItems([]); setCursor(null); setBusy(false); localStorage.removeItem(storageKey);
    }
    setError(code === 'PERMISSION_RESOURCE_UNAVAILABLE' ? '研究会话或知识版本不可用。' : '研究会话操作失败，请重试。');
  }

  async function list(next: string | null = null) {
    const epoch = accessEpoch.current;
    const number = ++requestNumber.current;
    try {
      const result = await envelope<{ items: Session[] }>(root + '?page_size=20' + (next ? `&cursor=${encodeURIComponent(next)}` : ''), { headers });
      if (!mounted.current || number !== requestNumber.current || epoch !== accessEpoch.current) return;
      setItems(result.data.items); setCursor(result.meta.next_cursor); setError('');
    } catch (reason) { if (mounted.current && number === requestNumber.current && epoch === accessEpoch.current) failed(reason); }
  }

  async function open(id: string) {
    const epoch = accessEpoch.current;
    const number = ++openNumber.current;
    opening.current = true;
    try {
      const result = await api<Session>(root + '/' + encodeURIComponent(id), { headers });
      if (!mounted.current || number !== openNumber.current || epoch !== accessEpoch.current) return;
      setCurrent(result); setNotice(false); setError(''); localStorage.setItem(storageKey, result.id);
    } catch (reason) { if (mounted.current && number === openNumber.current && epoch === accessEpoch.current) failed(reason); }
    finally { if (number === openNumber.current && epoch === accessEpoch.current) opening.current = false; }
  }

  useEffect(() => {
    mounted.current = true;
    if (project.default_knowledge_version_id) {
      void list();
      const saved = localStorage.getItem(storageKey);
      if (saved) void open(saved);
    }
    return () => { mounted.current = false; requestNumber.current++; openNumber.current++; };
  }, [!!project.default_knowledge_version_id]); // Latest pointer refresh preserves the title draft.

  useEffect(() => {
    if (!current) return;
    let cancelled = false;
    const id = current.id;
    let inFlight = false;
    const timer = window.setInterval(() => {
      if (inFlight || opening.current) return;
      inFlight = true;
      const generation = openNumber.current;
      const epoch = accessEpoch.current;
      void api<Session>(root + '/' + id, { headers }).then(result => {
        if (cancelled || generation !== openNumber.current || epoch !== accessEpoch.current) return;
        setCurrent(previous => {
          if (!previous || previous.id !== id) return previous;
          if (previous.latest_knowledge_version_id !== result.latest_knowledge_version_id) setNotice(true);
          return result;
        });
      }).catch(reason => { if (!cancelled && generation === openNumber.current && epoch === accessEpoch.current) failed(reason); }).finally(() => { inFlight = false; });
    }, 3000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [current?.id]);

  async function create() {
    const epoch = accessEpoch.current;
    setBusy(true); setError('');
    pending.current ??= { key: crypto.randomUUID(), body: { title: title.trim() || '新研究会话' } };
    try {
      const result = await write<Session>(root, pending.current.body, pending.current.key, actor);
      if (!mounted.current || epoch !== accessEpoch.current) return;
      pending.current = null; setTitle('');
      await list();
      if (mounted.current && epoch === accessEpoch.current) await open(result.id);
    } catch (reason) {
      if (mounted.current && epoch === accessEpoch.current) {
        if ((reason as { status?: number }).status && (reason as { status: number }).status < 500) pending.current = null;
        failed(reason);
      }
    } finally { if (mounted.current) setBusy(false); }
  }

  return <section aria-label="研究会话">
    <h3>研究会话</h3>
    {!project.default_knowledge_version_id ? <p>发布知识版本后可创建研究会话。</p> : <>
      <form onSubmit={event => { event.preventDefault(); void create(); }}>
        <label>研究会话标题<input maxLength={200} value={title} disabled={busy || !!pending.current} onChange={event => setTitle(event.target.value)} /></label>
        <button disabled={busy || project.status !== 'active'}>{busy ? '创建中…' : pending.current ? '重试创建会话' : '创建研究会话'}</button>
      </form>
      <button disabled={busy} onClick={() => void list()}>刷新研究会话</button>
      <ul>{items.map(item => <li key={item.id}><button disabled={busy} onClick={() => void open(item.id)}>{item.title}</button></li>)}</ul>
      {cursor && <button onClick={() => void list(cursor)}>更多研究会话</button>}
      {current && <article aria-label="当前研究会话">
        <h4>{current.title}</h4>
        {notice && <p role="status">检测到知识库版本更新</p>}
        <p>当前知识版本：<span>{current.latest_knowledge_version_id}</span></p>
        {current.no_project_evidence && <p>当前版本没有项目证据。后续问答需要显式选择无证据继续。</p>}
        <p>此会话尚无研究轮次。问答功能待接入。</p>
      </article>}
    </>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
