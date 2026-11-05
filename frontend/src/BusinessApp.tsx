import { ResearchSessions } from './ResearchSessions';
import { SearchTerms } from './SearchTerms';
import { ConstructionRuns } from './ConstructionRuns';
import { SMTPSettings } from './SMTPSettings';
import { SecuritySettings } from './SecuritySettings';
import { AdminUsers } from './AdminUsers';
import { SourceSettings } from './SourceSettings';
import { LLMSettings, ModelPicker } from './LLMSettings';
import { useEffect, useRef, useState, type FormEvent } from 'react';

type User = { id: string; revision: string; username: string; email: string; display_name: string | null; is_admin: boolean };
type Project = { id: string; revision: string; name: string; description: string; research_scope: string; status: string; default_knowledge_version_id: string | null; last_construction_at: string | null; last_activity_at: string | null };
type ProjectInput = { name: string; description: string; research_scope: string };
class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message); }
}
const messages: Record<string, string> = {
  AUTH_INVALID_CREDENTIALS: '用户名、邮箱或密码不正确。',
  AUTH_ACCOUNT_DISABLED: '账号已禁用，请联系管理员。',
  AUTH_SESSION_INVALID: '会话已失效，请重新登录。',
  AUTH_REQUIRED: '请先登录。',
  PERMISSION_RESOURCE_UNAVAILABLE: '资源不可用。',
  STATE_OPERATION_NOT_ALLOWED: '用户名或邮箱已被使用。',
  PERMISSION_CSRF_REJECTED: '会话校验失败，请刷新后重试。',
};
async function envelope<T>(url: string, init?: RequestInit): Promise<{ data: T; meta: { next_cursor: string | null; has_more: boolean } }> {
  const response = await fetch(url, { credentials: 'same-origin', ...init });
  if (response.status === 204) return { data: undefined as T, meta: { next_cursor: null, has_more: false } };
  const value = await response.json();
  if (!response.ok) throw new ApiError(response.status, value.error?.code ?? 'UNKNOWN', value.error?.message ?? '请求未完成。');
  return value;
}
async function json<T>(url: string, init?: RequestInit): Promise<T> {
  return (await envelope<T>(url, init)).data;
}
async function post<T>(path: string, body: unknown, key?: string, expectedActor?: string, method = 'POST'): Promise<T> {
  const csrf = await json<{ csrf_token: string }>('/api/v1/auth/csrf');
  // Order is deliberate: the token binds this request to the session observed
  // before identity validation. A later login rotation makes this token invalid.
  if (expectedActor) {
    const current = await json<User>('/api/v1/me');
    if (current.id !== expectedActor) throw new ApiError(401, 'AUTH_SESSION_INVALID', '登录账号已变化，请重新确认。');
  }
  return json<T>(path, { method, headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf.csrf_token, ...(key ? { 'Idempotency-Key': key } : {}), ...(expectedActor ? { 'X-Expected-Actor': expectedActor } : {}) }, body: method === 'DELETE' ? undefined : JSON.stringify(body) });
}

type LifecyclePreview = { action: 'archive' | 'delete'; subject_revision: string; confirmation_token: string; risks: { id: string; message: string }[]; retained_items: { reason: string }[] };
function ProjectMaintenance({ project, actor, onChange, onDeleted, onUnavailable, onBusy, onAuthFailure }: {
  project: Project; actor: string; onChange: (p: Project) => void; onDeleted: () => void; onUnavailable: () => void;
  onBusy: (value: boolean) => void; onAuthFailure: (error: unknown) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<ProjectInput>({ name: project.name, description: project.description, research_scope: project.research_scope });
  const [preview, setPreview] = useState<LifecyclePreview | null>(null);
  const [acknowledged, setAcknowledged] = useState<string[]>([]);
  const [pendingArchive, setPendingArchive] = useState<{ key: string; body: unknown } | null>(null);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');
  const [uncertain, setUncertain] = useState(false);
  async function run(action: () => Promise<void>, writing = false) {
    setWorking(true); onBusy(true); setError('');
    try { await action(); }
    catch (reason) {
      if (reason instanceof ApiError && (reason.status === 401 || reason.code === 'PERMISSION_CSRF_REJECTED')) onAuthFailure(reason);
      else if (reason instanceof ApiError && [400, 413, 415, 422, 428].includes(reason.status)) { setError('输入未通过校验，请修正后再保存。'); if (!uncertain) setPendingArchive(null); }
      else if (reason instanceof ApiError && reason.status === 412) { setError('项目已被修改。草稿已保留，请核对最新内容后再编辑。'); setUncertain(true); }
      else if (reason instanceof ApiError && reason.status === 404) onUnavailable();
      else if (reason instanceof ApiError && reason.code.startsWith('STATE_CONFIRMATION_')) { setPreview(null); setPendingArchive(null); setError('确认依据已失效，请重新预览。'); }
      else if (reason instanceof ApiError && reason.code === 'STATE_PROJECT_READ_ONLY') { setError('项目已只读，请加载当前内容。'); setUncertain(true); }
      else { setError(writing ? '提交结果尚未确认，请先核查当前内容。' : '读取未完成，请重试。'); if (writing) setUncertain(true); }
    } finally { setWorking(false); onBusy(false); }
  }
  function loadCurrent() {
    void run(async () => {
      const current = await json<Project>(`/api/v1/projects/${project.id}`);
      onChange(current); setDraft({ name: current.name, description: current.description, research_scope: current.research_scope });
      setEditing(false); setPreview(null); setPendingArchive(null); setUncertain(false);
    });
  }
  function save(event: FormEvent) {
    event.preventDefault();
    void run(async () => {
      const current = await post<Project>(`/api/v1/projects/${project.id}`, { ...draft, expected_revision: project.revision }, undefined, actor, 'PATCH');
      onChange(current); setEditing(false); setUncertain(false);
    }, true);
  }
  function requestPreview(action: 'archive' | 'delete') {
    void run(async () => {
      const result = await post<LifecyclePreview>(`/api/v1/projects/${project.id}/action-preview`, { action, expected_revision: project.revision }, undefined, actor);
      setPreview(result); setAcknowledged([]); setEditing(false); setPendingArchive(null);
    });
  }
  function confirm() {
    if (!preview) return;
    void run(async () => {
      const body = { expected_revision: preview.subject_revision, confirmation_token: preview.confirmation_token, acknowledged_risk_ids: acknowledged };
      if (preview.action === 'archive') {
        const command = pendingArchive ?? { key: crypto.randomUUID(), body };
        setPendingArchive(command);
        const current = await post<Project>(`/api/v1/projects/${project.id}/archive`, command.body, command.key, actor);
        onChange(current); setPendingArchive(null); setPreview(null); setUncertain(false);
      } else {
        const query = new URLSearchParams({ expected_revision: preview.subject_revision, confirmation_token: preview.confirmation_token });
        acknowledged.forEach(id => query.append('acknowledged_risk_ids', id));
        await post(`/api/v1/projects/${project.id}?${query}`, undefined, undefined, actor, 'DELETE');
        onDeleted();
      }
    }, true);
  }
  return <section className="maintenance" aria-label="项目维护" aria-busy={working}>
    {error && <p className="error" role="alert">{error}</p>}
    {uncertain && <button disabled={working} onClick={loadCurrent}>核查并加载当前内容（放弃草稿）</button>}
    {project.status === 'active' && !editing && !preview && !uncertain && <div className="list-pages">
      <button disabled={working} onClick={() => { setDraft({ name: project.name, description: project.description, research_scope: project.research_scope }); setEditing(true); }}>编辑信息</button>
      <button disabled={working} onClick={() => requestPreview('archive')}>归档项目</button>
      <button disabled={working} onClick={() => requestPreview('delete')}>删除项目</button>
    </div>}
    {editing && <form onSubmit={save}>
      <h3>编辑项目</h3>
      <label>项目名称<input required maxLength={200} value={draft.name} disabled={working} onChange={e => setDraft({ ...draft, name: e.target.value })} /></label>
      <label>描述<textarea maxLength={10000} value={draft.description} disabled={working} onChange={e => setDraft({ ...draft, description: e.target.value })} /></label>
      <label>研究范围<textarea maxLength={10000} value={draft.research_scope} disabled={working} onChange={e => setDraft({ ...draft, research_scope: e.target.value })} /></label>
      <div className="list-pages"><button type="submit" disabled={working || uncertain}>保存修改</button><button type="button" disabled={working} onClick={() => setEditing(false)}>取消编辑</button></div>
    </form>}
    {preview && <div className="confirmation" role="group" aria-label="操作确认">
      <h3>{preview.action === 'archive' ? '确认归档' : '确认软删除'}</h3>
      <p>将操作：{project.name}</p>
      {preview.risks.map(r => <label className="checkbox" key={r.id}><input type="checkbox" disabled={working || !!pendingArchive} checked={acknowledged.includes(r.id)} onChange={e => setAcknowledged(e.target.checked ? [...acknowledged, r.id] : acknowledged.filter(id => id !== r.id))} />{r.message}</label>)}
      <ul>{preview.retained_items.map((item, i) => <li key={i}>{item.reason}</li>)}</ul>
      <div className="list-pages"><button disabled={working || acknowledged.length !== preview.risks.length || (uncertain && !pendingArchive)} onClick={confirm}>{pendingArchive ? '核查原归档请求' : '确认执行'}</button><button disabled={working || uncertain} onClick={() => { setPreview(null); setPendingArchive(null); }}>取消操作</button></div>
    </div>}
  </section>;
}

function Profile({ user, onChange, onAuthFailure, onBusy }: { user: User; onChange: (u: User) => void; onAuthFailure: (e: unknown) => void; onBusy: (value: boolean) => void }) {
  const [email, setEmail] = useState(user.email);
  const [name, setName] = useState(user.display_name ?? '');
  const [working, setWorking] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [message, setMessage] = useState('');
  async function run(save: boolean) {
    setWorking(true); onBusy(true); setMessage('');
    try {
      const current = save
        ? await post<User>('/api/v1/me', { expected_revision: user.revision, email, display_name: name || null }, undefined, user.id, 'PATCH')
        : await json<User>('/api/v1/me');
      if (current.id !== user.id) throw new ApiError(401, 'AUTH_SESSION_INVALID', '登录账号已变化。');
      onChange(current); setEmail(current.email); setName(current.display_name ?? ''); setUncertain(false); setMessage(save ? '个人资料已保存。' : '已加载当前资料。');
    } catch (reason) {
      if (reason instanceof ApiError && (reason.status === 401 || reason.code === 'PERMISSION_CSRF_REJECTED')) onAuthFailure(reason);
      else if (reason instanceof ApiError && [400, 409, 413, 415, 422, 428].includes(reason.status)) setMessage(reason.status === 409 ? '邮箱已被使用，请换一个邮箱。' : '输入未通过校验，请修正后保存。');
      else { setMessage('资料可能已变化或提交结果未知。草稿已保留，请核查当前资料。'); setUncertain(true); }
    } finally { setWorking(false); onBusy(false); }
  }
  return <section className="form-card" aria-label="个人资料" aria-busy={working}>
    <h2>个人资料</h2><p>用户名：{user.username}</p>
    {message && <p role="status">{message}</p>}
    <form onSubmit={e => { e.preventDefault(); void run(true); }}>
      <label>个人邮箱<input type="email" required maxLength={254} value={email} disabled={working} onChange={e => setEmail(e.target.value)} /></label>
      <label>显示名<input maxLength={200} value={name} disabled={working} onChange={e => setName(e.target.value)} /></label>
      <div className="list-pages"><button disabled={working || uncertain} type="submit">保存个人资料</button><button type="button" disabled={working} onClick={() => { setEmail(user.email); setName(user.display_name ?? ''); }}>取消资料编辑</button></div>
    </form>
    {uncertain && <button disabled={working} onClick={() => void run(false)}>核查并加载当前资料（放弃草稿）</button>}
  </section>;
}

function ProjectList({ actor, onAuthFailure }: { actor: string; onAuthFailure: (error: unknown) => void }) {
  const [cursor, setCursor] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const [items, setItems] = useState<Project[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState('');
  const onFailure = useRef(onAuthFailure);
  onFailure.current = onAuthFailure;
  useEffect(() => {
    let alive = true;
    const controller = new AbortController();
    setLoading(true); setItems([]); setNext(null); setFailure('');
    const query = new URLSearchParams({ page_size: '20' });
    if (cursor) query.set('cursor', cursor);
    void envelope<{ items: Project[] }>(`/api/v1/projects?${query}`, {
      signal: controller.signal, headers: { 'X-Expected-Actor': actor },
    }).then(result => {
      if (alive) { setItems(result.data.items); setNext(result.meta.next_cursor); }
    }).catch(reason => {
      if (!alive) return;
      if (reason instanceof ApiError && reason.status === 401) onFailure.current(reason);
      else setFailure(reason instanceof ApiError && reason.code.startsWith('VALIDATION_CURSOR_')
        ? '列表位置已失效，请返回第一页。' : '项目列表读取失败，请重试。');
    }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; controller.abort(); };
  }, [actor, cursor, reload]);
  return <section className="form-card project-list" aria-label="我的项目" aria-busy={loading}>
    <div className="project-heading"><h2>我的项目</h2><button disabled={loading} onClick={() => { setCursor(null); setReload(n => n + 1); }}>刷新列表</button></div>
    {loading ? <p>正在读取项目…</p> : failure ? <div><p role="alert">{failure}</p><button onClick={() => setReload(n => n + 1)}>重试列表</button></div> : items.length === 0 ? <p className="hint">还没有可显示的项目，可在下方创建。</p> : <ul>
      {items.map(item => <li key={item.id}><a href={`/workspace?project=${encodeURIComponent(item.id)}`}>{item.name}</a><span className="badge">{item.status === 'active' ? '进行中' : '已归档 · 只读'}</span><p className="preserve">{item.description || '未填写描述'}</p><p className="hint">{item.default_knowledge_version_id ? '已有知识版本' : '尚无知识版本'} · 最近构建：{item.last_construction_at ?? '暂无'} · 最近活动：{item.last_activity_at ?? '暂无'}</p></li>)}
    </ul>}
    <div className="list-pages">{cursor && <button disabled={loading} onClick={() => setCursor(null)}>返回第一页</button>}{next && <button disabled={loading} onClick={() => setCursor(next)}>下一页</button>}</div>
  </section>;
}

export function BusinessApp() {
  const [user, setUser] = useState<User | null>(null);
  const [profile, setProfile] = useState(false);
  const [adminSMTP, setAdminSMTP] = useState(false);
  const [adminSMTPOpened, setAdminSMTPOpened] = useState(false);
  const [adminSecurity, setAdminSecurity] = useState(false);
  const [adminSecurityOpened, setAdminSecurityOpened] = useState(false);
  const [adminSources, setAdminSources] = useState(false);
  const [adminSourcesOpened, setAdminSourcesOpened] = useState(false);
  const [adminLLM, setAdminLLM] = useState(false);
  const [adminUsers, setAdminUsers] = useState(false);
  const [sourceOpened, setSourceOpened] = useState(false);
  const [sourceSettings, setSourceSettings] = useState(false);
  const [llmSettings, setLlmSettings] = useState(false);
  const [modelRevision, setModelRevision] = useState(0);
  const [project, setProject] = useState<Project | null>(null);
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [scope, setScope] = useState('');
  const [pending, setPending] = useState<{ key: string; body: ProjectInput } | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  // The project badge only distinguishes an unpublished project from one with a version.
  const projectId = project?.id;
  const waitingForFirstVersion = project?.status === 'active' && !project.default_knowledge_version_id;
  useEffect(() => {
    if (!user || !projectId || !waitingForFirstVersion) return;
    const controller = new AbortController();
    let timer: number;
    async function check() {
      try {
        if (!document.hidden) {
          const latest = await json<Project>(`/api/v1/projects/${projectId}`, { signal: controller.signal });
          if (controller.signal.aborted) return;
          if (latest.default_knowledge_version_id) {
            setProject(current => current && current.id === projectId
              ? { ...current, default_knowledge_version_id: latest.default_knowledge_version_id }
              : current);
            return;
          }
        }
      } catch (error) {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && [401, 403, 404].includes(error.status)) {
          if (error.status !== 401) leaveProject();
          explain(error);
          return;
        }
      }
      timer = window.setTimeout(check, 5000);
    }
    timer = window.setTimeout(check, 5000);
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [user?.id, projectId, waitingForFirstVersion]);

  function restorePending(current: User) {
    try {
      const saved = sessionStorage.getItem(`rpb:create:${current.id}`);
      if (!saved) return;
      const value = JSON.parse(saved);
      if (typeof value.key !== 'string' || !value.body || !['name', 'description', 'research_scope'].every(k => typeof value.body[k] === 'string')) throw new Error('Invalid saved request');
      setPending(value); setName(value.body.name); setDescription(value.body.description); setScope(value.body.research_scope);
    } catch { setError('待确认请求无法恢复，请先核查已有项目链接。'); }
  }
  function forgetPending() {
    try { if (user) sessionStorage.removeItem(`rpb:create:${user.id}`); } catch { /* In-memory state still clears. */ }
    setPending(null);
  }
  function leaveProject() {
    setProject(null); setName(''); setDescription(''); setScope(''); setNotice('');
    window.history.replaceState(null, '', '/workspace');
  }
  function clearPrivate(discardPending = false) {
    try { if (discardPending) for (const key of Object.keys(sessionStorage)) if (key.startsWith('rpb:create:')) sessionStorage.removeItem(key); } catch { /* Authentication state must clear even when storage is unavailable. */ }
    setAdminSMTP(false); setAdminSMTPOpened(false); setAdminSecurity(false); setAdminSecurityOpened(false); setAdminSourcesOpened(false); setAdminSources(false); setUser(null); setAdminLLM(false); setAdminUsers(false); setSourceOpened(false); setSourceSettings(false); setProfile(false); setLlmSettings(false); setProject(null); setPending(null); setName(''); setDescription(''); setScope('');
    setPassword(''); setConfirmation(''); setShowPassword(false);
    window.history.replaceState(null, '', '/workspace');
  }
  function explain(reason: unknown) {
    if (reason instanceof ApiError) {
      if (reason.status === 401 || reason.code === 'PERMISSION_CSRF_REJECTED') clearPrivate();
      setError(messages[reason.code] ?? reason.message);
    } else setError('连接未完成，请检查连接后重试。');
  }
  async function selectedProject() {
    const id = new URLSearchParams(window.location.search).get('project');
    if (id) setProject(await json<Project>(`/api/v1/projects/${encodeURIComponent(id)}`));
  }
  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const current = await json<User>('/api/v1/me');
        if (!alive) return;
        setUser(current); restorePending(current);
        const query = new URLSearchParams(window.location.search);
        if (current.is_admin && query.has('smtp_oauth')) {
          setAdminSMTP(true); setAdminSMTPOpened(true);
          setNotice('授权流程已结束，请核查SMTP授权状态并测试连接。');
          query.delete('smtp_oauth');
          window.history.replaceState(null, '', '/workspace' + (query.size ? '?' + query.toString() : ''));
        }
        await selectedProject();
      } catch (reason) {
        if (alive && reason instanceof ApiError && reason.status === 401) {
          clearPrivate();
          if (reason.code === 'AUTH_ACCOUNT_DISABLED') explain(reason);
        } else if (alive) explain(reason);
      } finally { if (alive) setBusy(false); }
    }
    void load();
    return () => { alive = false; };
  }, []);

  async function authenticate(event: FormEvent) {
    event.preventDefault(); setError(''); setNotice('');
    if (mode === 'register' && password !== confirmation) { setError('两次密码不一致。'); return; }
    setBusy(true);
    try {
      if (mode === 'register') {
        await post<User>('/api/v1/auth/register', { username, email, password });
        setMode('login'); setPassword(''); setConfirmation(''); setShowPassword(false); setNotice('注册成功，请登录。');
      } else {
        const result = await post<{ user: User }>('/api/v1/auth/login', { identifier: username, password });
        setUser(result.user); restorePending(result.user); setPassword(''); setShowPassword(false); await selectedProject();
      }
    } catch (reason) { explain(reason); } finally { setBusy(false); }
  }
  async function createProject(event: FormEvent) {
    event.preventDefault(); setError(''); setNotice(''); setBusy(true);
    const command = pending ?? { key: crypto.randomUUID(), body: { name, description, research_scope: scope } };
    setPending(command);
    try {
      sessionStorage.setItem(`rpb:create:${user!.id}`, JSON.stringify(command));
    } catch {
      setPending(null); setBusy(false); setError('浏览器无法保留待确认请求，请允许本站会话存储后重试。'); return;
    }
    try {
      const created = await post<Project>('/api/v1/projects', command.body, command.key, user!.id);
      // Read the durable resource before presenting the completed result.
      const current = await json<Project>(`/api/v1/projects/${created.id}`);
      setProject(current); forgetPending(); setNotice('Project 已创建。');
      window.history.replaceState(null, '', `/workspace?project=${encodeURIComponent(current.id)}`);
    } catch (reason) {
      if (!pending && reason instanceof ApiError && [400, 403, 413, 415, 422].includes(reason.status)) forgetPending();
      explain(reason);
    } finally { setBusy(false); }
  }
  async function logout() {
    setBusy(true); setError(''); setNotice('');
    try { await post('/api/v1/auth/logout', {}, undefined, user!.id); clearPrivate(true); setNotice('已退出当前会话。'); }
    catch (reason) { explain(reason); } finally { setBusy(false); }
  }

  return <div className="app business">
    <a className="skip" href="#content">跳到内容</a>
    <header><a className="brand" href="/workspace">Research Paper Base</a>{user && <div className="account-bar"><span>{user.display_name || user.username}</span><button disabled={busy} onClick={() => { setAdminSMTP(false); setAdminSecurity(false); setAdminSources(false); setAdminLLM(false); setAdminUsers(false); setSourceSettings(false); setLlmSettings(false); setProfile(!profile); }}>{profile ? '返回项目' : '个人资料'}</button><button disabled={busy} onClick={() => { setAdminSMTP(false); setAdminSecurity(false); setAdminSources(false); setAdminLLM(false); setAdminUsers(false); setSourceSettings(false); setProfile(false); setLlmSettings(!llmSettings); }}>{llmSettings ? '返回项目' : 'LLM设置'}</button><button disabled={busy} onClick={() => { setAdminSMTP(false); setAdminSecurity(false); setAdminSources(false); setAdminLLM(false); setAdminUsers(false); setSourceOpened(true); setLlmSettings(false); setProfile(false); setSourceSettings(!sourceSettings); }}>{sourceSettings ? '返回项目' : '数据源设置'}</button>{user.is_admin && <button disabled={busy} onClick={() => { setAdminSMTP(false); setAdminSecurity(false); setAdminSources(false); setAdminLLM(false); setAdminUsers(!adminUsers); setSourceSettings(false); setProfile(false); setLlmSettings(false); }}>管理员用户</button>}<>{user.is_admin && <button disabled={busy} onClick={() => { setAdminSMTP(false); setAdminSecurity(false); setAdminSources(false); setAdminLLM(!adminLLM); setAdminUsers(false); setSourceSettings(false); setProfile(false); setLlmSettings(false); }}>系统LLM</button>}</>{user.is_admin && <button disabled={busy} onClick={() => { setAdminSMTP(false); setAdminSecurity(false); setAdminSourcesOpened(true); setAdminSources(!adminSources); setAdminLLM(false); setAdminUsers(false); setSourceSettings(false); setProfile(false); setLlmSettings(false); }}>系统数据源</button>}{user.is_admin && <><button disabled={busy} onClick={() => { setAdminSMTPOpened(true); setAdminSMTP(!adminSMTP); setAdminSecurity(false); setAdminSources(false); setAdminLLM(false); setAdminUsers(false); setSourceSettings(false); setProfile(false); setLlmSettings(false); }}>系统SMTP</button><button disabled={busy} onClick={() => { setAdminSecurityOpened(true); setAdminSecurity(!adminSecurity); setAdminSMTP(false); setAdminSources(false); setAdminLLM(false); setAdminUsers(false); setSourceSettings(false); setProfile(false); setLlmSettings(false); }}>基础安全</button></>}<button disabled={busy} onClick={() => void logout()}>退出登录</button></div>}</header>
    <main id="content" tabIndex={-1} aria-busy={busy}>
      <p className="eyebrow">你的研究，始于一个问题</p>
      <h1>{user ? adminSMTP ? '系统SMTP管理' : adminSecurity ? '基础安全设置' : adminSources ? '系统数据源管理' : adminLLM ? '系统LLM管理' : adminUsers ? '管理员账号管理' : sourceSettings ? '数据源设置' : profile ? '账户设置' : '研究项目' : mode === 'login' ? '欢迎回来' : '创建账号'}</h1>
      {notice && <p className="notice" role="status">{notice}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {user && <><ModelPicker key={user.id + '-model'} api={json} write={post} actor={user.id} revision={modelRevision} onAuthFailure={explain} /><LLMSettings active={llmSettings} key={user.id + '-llm'} api={json} pageApi={envelope} write={post} actor={user.id} onChange={() => setModelRevision(v => v + 1)} onBusy={setBusy} onAuthFailure={explain} />{user.is_admin && <LLMSettings system active={adminLLM} key={user.id + '-system-llm'} api={json} pageApi={envelope} write={post} actor={user.id} onChange={() => setModelRevision(v => v + 1)} onBusy={setBusy} onAuthFailure={explain} />}</>}
      {user && adminUsers && <AdminUsers key={user.id + "-admin"} actor={user.id} api={json} pageApi={envelope} write={post} onAuthFailure={explain} onBusy={setBusy}/>}
      {user && sourceOpened && <div hidden={!sourceSettings}><SourceSettings key={user.id + '-sources'} api={json} pageApi={envelope} write={post} actor={user.id} onChange={() => {}} onBusy={setBusy} onAuthFailure={explain}/></div>}
      {user && <div hidden={!profile}><Profile key={user.id} user={user} onChange={setUser} onAuthFailure={explain} onBusy={setBusy} /></div>}
      {user?.is_admin && adminSourcesOpened && <div hidden={!adminSources}><SourceSettings system key={user.id + "-system-sources"} api={json} pageApi={envelope} write={post} actor={user.id} onChange={() => {}} onBusy={setBusy} onAuthFailure={explain}/></div>}
      {user?.is_admin && adminSMTPOpened && <div hidden={!adminSMTP}><SMTPSettings key={user.id + '-smtp'} actor={user.id} api={json} write={post} onBusy={setBusy} onAuthFailure={explain}/></div>}
      {user?.is_admin && adminSecurityOpened && <div hidden={!adminSecurity}><SecuritySettings key={user.id + '-security'} actor={user.id} api={json} write={post} onBusy={setBusy} onAuthFailure={explain}/></div>}
      <div hidden={!!user && (adminSMTP || adminSecurity || adminSources || profile || sourceSettings || adminUsers || adminLLM || llmSettings)}>
      {user && !project && !busy && !adminUsers && <ProjectList key={user.id} actor={user.id} onAuthFailure={explain} />}
      {!user ? <section className="form-card auth-card" aria-label="账号认证">
        <div className="auth-tabs"><button disabled={busy} aria-pressed={mode === 'login'} onClick={() => { setMode('login'); setError(''); setConfirmation(''); }}>登录</button><button disabled={busy} aria-pressed={mode === 'register'} onClick={() => { setMode('register'); setError(''); setPassword(''); }}>注册</button></div>
        <form onSubmit={event => void authenticate(event)}>
          <label>{mode === 'login' ? '用户名或邮箱' : '用户名'}<input required autoComplete="username" maxLength={mode === 'register' ? 64 : undefined} value={username} onChange={event => setUsername(event.target.value)} disabled={busy} /></label>
          {mode === 'register' && <label>邮箱<input required type="email" autoComplete="email" maxLength={254} value={email} onChange={event => setEmail(event.target.value)} disabled={busy} /></label>}
          <label>密码<input required type={showPassword ? 'text' : 'password'} autoComplete={mode === 'register' ? 'new-password' : 'current-password'} minLength={mode === 'register' ? 12 : undefined} maxLength={mode === 'register' ? 128 : undefined} value={password} onChange={event => setPassword(event.target.value)} disabled={busy} /></label>
          {mode === 'register' && <label>确认密码<input required type={showPassword ? 'text' : 'password'} autoComplete="new-password" value={confirmation} onChange={event => setConfirmation(event.target.value)} disabled={busy} /></label>}
          <label className="checkbox"><input type="checkbox" checked={showPassword} onChange={event => setShowPassword(event.target.checked)} />显示当前输入的密码</label>
          {mode === 'register' && <p className="hint">密码使用 12–128 个字符。用户名和邮箱均可用于登录。</p>}
          <button className="primary" disabled={busy} type="submit">{busy ? '处理中…' : mode === 'register' ? '创建账号' : '登录账号'}</button>
        </form>
      </section> : project ? <section className="form-card project-card" aria-label="当前项目">
        <div className="project-heading"><span className="badge">{project.status === 'active' ? '进行中' : '已归档 · 只读'}</span><a href="/workspace">我的项目</a><a href="/workspace">新建项目</a></div>
        <h2>{project.name}</h2>
        <h3>研究描述</h3><p className="preserve">{project.description || '未填写'}</p>
        <h3>研究范围</h3><p className="preserve">{project.research_scope || '未填写'}</p>
        <p className="knowledge-state">{project.default_knowledge_version_id ? '已有知识版本' : '尚未构建知识版本'}</p>
        <a href={`/workspace?project=${encodeURIComponent(project.id)}`}>项目链接</a>
        <SearchTerms envelope={envelope} key={user.id + project.id} project={project} actor={user.id} api={json} write={post} onAuthFailure={explain} />
        <ConstructionRuns envelope={envelope} key={"runs-" + user.id + project.id} project={project} actor={user.id} api={json} write={post} onAuthFailure={explain} />
        <ResearchSessions key={"research-" + user.id + project.id} project={project} actor={user.id} api={json} envelope={envelope} write={post} onAuthFailure={explain} />
        <ProjectMaintenance key={project.id} project={project} actor={user.id} onChange={setProject} onBusy={setBusy} onAuthFailure={explain} onUnavailable={() => { leaveProject(); setError('资源不可用。'); }} onDeleted={() => { leaveProject(); setNotice('Project 已软删除。'); }} />
      </section> : <section className="form-card" aria-label="新建研究项目">
        <h2>新建 Project</h2><p className="hint">定义研究问题与范围，建立自己的研究容器。</p>
        <form onSubmit={event => void createProject(event)}>
          <label>项目名称<input required maxLength={200} value={name} onChange={event => setName(event.target.value)} disabled={busy || !!pending} /></label>
          <label>描述<textarea maxLength={10000} value={description} onChange={event => setDescription(event.target.value)} disabled={busy || !!pending} /></label>
          <label>研究范围<textarea maxLength={10000} value={scope} onChange={event => setScope(event.target.value)} disabled={busy || !!pending} /></label>
          {pending && !busy && <p className="hint" role="status">创建结果尚未确认。重试将核查原请求的创建结果。</p>}
          <button className="primary" type="submit" disabled={busy}>{busy ? '处理中…' : pending ? '用原请求重试' : '创建 Project'}</button>
        </form>
      </section>}
      </div>
    </main>
  </div>;
}
