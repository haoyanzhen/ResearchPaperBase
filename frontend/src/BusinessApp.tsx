import { useEffect, useState, type FormEvent } from 'react';

type User = { id: string; username: string; is_admin: boolean };
type Project = { id: string; name: string; description: string; research_scope: string; status: string; default_knowledge_version_id: string | null };
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
async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { credentials: 'same-origin', ...init });
  const value = await response.json();
  if (!response.ok) throw new ApiError(response.status, value.error?.code ?? 'UNKNOWN', value.error?.message ?? '请求未完成。');
  return value.data as T;
}
async function post<T>(path: string, body: unknown, key?: string, expectedActor?: string): Promise<T> {
  const csrf = await json<{ csrf_token: string }>('/api/v1/auth/csrf');
  // Order is deliberate: the token binds this request to the session observed
  // before identity validation. A later login rotation makes this token invalid.
  if (expectedActor) {
    const current = await json<User>('/api/v1/me');
    if (current.id !== expectedActor) throw new ApiError(401, 'AUTH_SESSION_INVALID', '登录账号已变化，请重新确认。');
  }
  return json<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf.csrf_token, ...(key ? { 'Idempotency-Key': key } : {}) }, body: JSON.stringify(body) });
}

export function BusinessApp() {
  const [user, setUser] = useState<User | null>(null);
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
  function clearPrivate(discardPending = false) {
    try { if (discardPending) for (const key of Object.keys(sessionStorage)) if (key.startsWith('rpb:create:')) sessionStorage.removeItem(key); } catch { /* Authentication state must clear even when storage is unavailable. */ }
    setUser(null); setProject(null); setPending(null); setName(''); setDescription(''); setScope('');
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
    <header><a className="brand" href="/workspace">Research Paper Base</a>{user && <div className="account-bar"><span>{user.username}</span><button disabled={busy} onClick={() => void logout()}>退出登录</button></div>}</header>
    <main id="content" tabIndex={-1} aria-busy={busy}>
      <p className="eyebrow">你的研究，始于一个问题</p>
      <h1>{user ? '研究项目' : mode === 'login' ? '欢迎回来' : '创建账号'}</h1>
      {notice && <p className="notice" role="status">{notice}</p>}
      {error && <p className="error" role="alert">{error}</p>}
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
        <div className="project-heading"><span className="badge">{project.status === 'active' ? '进行中' : '已归档 · 只读'}</span><a href="/workspace">新建项目</a></div>
        <h2>{project.name}</h2>
        <h3>研究描述</h3><p className="preserve">{project.description || '未填写'}</p>
        <h3>研究范围</h3><p className="preserve">{project.research_scope || '未填写'}</p>
        <p className="knowledge-state">{project.default_knowledge_version_id ? '已有知识版本' : '尚未构建知识版本'}</p>
        <a href={`/workspace?project=${encodeURIComponent(project.id)}`}>项目链接</a>
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
    </main>
  </div>;
}
