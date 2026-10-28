import { useEffect, useRef, useState } from 'react';

type User = { id: string; revision: string; username: string; email: string; enabled: boolean; is_admin: boolean; created_at: string; last_login_at: string | null };
type Preview = { confirmation_token: string; risks: { id: string; message: string }[] };
type Pending = { target: string; action: string; body: Record<string, unknown>; key: string };
type Props = { actor: string; api: <T>(url: string, init?: RequestInit) => Promise<T>; pageApi: <T>(url: string, init?: RequestInit) => Promise<{ data: T; meta: { next_cursor: string | null; has_more: boolean } }>; write: <T>(url: string, body: unknown, key?: string, actor?: string, method?: string) => Promise<T>; onAuthFailure: (e: unknown) => void; onBusy: (v: boolean) => void };
export function AdminUsers({ actor, pageApi, write, onAuthFailure, onBusy }: Props) {
  const [users, setUsers] = useState<User[]>([]), [cursor, setCursor] = useState<string | null>(null);
  const [selected, setSelected] = useState<User | null>(null), [action, setAction] = useState('change_email'), [email, setEmail] = useState('');
  const [preview, setPreview] = useState<Preview | null>(null), [ack, setAck] = useState(false), [pending, setPending] = useState<Pending | null>(null);
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [password, setPassword] = useState(''), [busy, setBusy] = useState(false);
  const alive = useRef(true);
  async function load(next: string | null = null) {
    const result = await pageApi<{ items: User[] }>('/api/v1/admin/users' + (next ? '?cursor=' + encodeURIComponent(next) : ''), { headers: { 'X-Expected-Actor': actor } });
    if (!alive.current) return;
    setUsers(old => next ? [...old, ...result.data.items] : result.data.items); setCursor(result.meta.next_cursor);
  }
  async function run(fn: () => Promise<void>) {
    setBusy(true); onBusy(true); setError('');
    try { await fn(); } catch (e) {
      if (!alive.current) return;
      const value = e as { status?: number; code?: string };
      if (value.status === 401 || value.code === 'PERMISSION_CSRF_REJECTED') onAuthFailure(e);
      else if (value.status === 403) { setUsers([]); setSelected(null); setPassword(''); setPending(null); setError('管理员权限已失效。'); }
      else setError(value.status === 412 ? '账号已变化，请刷新列表并重新预览。' : '操作未完成。请核查当前账号；未知提交结果请使用原请求核查。');
    } finally { if (alive.current) { setBusy(false); onBusy(false); } }
  }
  useEffect(() => { alive.current = true; void run(() => load()); return () => { alive.current = false; }; }, []);
  function choose(user: User) { setSelected(user); setEmail(user.email); setAction('change_email'); setPreview(null); setAck(false); setPassword(''); setNotice(''); }
  async function execute(command: Pending) {
    const base = '/api/v1/admin/users/' + command.target;
    let path = base, method = 'PATCH';
    if (command.action === 'reset_password') { path += '/reset-password'; method = 'POST'; }
    if (command.action === 'delete') {
      const query = new URLSearchParams({ expected_revision: String(command.body.expected_revision), confirmation_token: String(command.body.confirmation_token) });
      for (const risk of command.body.acknowledged_risk_ids as string[]) query.append('acknowledged_risk_ids', risk);
      path += '?' + query; method = 'DELETE';
    }
    const result = await write<{ new_password?: string; password_disclosed?: boolean }>(path, command.body, command.action === 'reset_password' ? command.key : undefined, actor, method);
    if (!alive.current) return;
    setPending(null); setPreview(null); setAck(false); setSelected(null);
    setPassword(result.new_password ?? '');
    setNotice(command.action === 'reset_password' && !result.password_disclosed ? '密码已重置；新密码不会再次披露。如首次响应丢失，请重新预览发起新的重置。' : '操作已完成。');
    if (!(command.action === 'reset_password' && command.target === actor)) await load();
  }
  return <section aria-label="管理员用户管理"><h2>管理员 / 用户</h2>
    <button disabled={busy} onClick={() => void run(async () => { await load(); setSelected(null); setPreview(null); setPassword(''); })}>刷新账号列表</button>
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {password && <div><p>新密码仅本次显示，请自行安全转交。</p><output aria-label="生成的新密码">{password}</output><button onClick={() => { void navigator.clipboard.writeText(password).catch(() => setError('复制失败，请手动复制。')); }}>复制新密码</button><button onClick={() => setPassword('')}>隐藏新密码</button></div>}
    {pending && <div><p>保留了待核查的原请求。重置重放不会再次生成或披露密码。</p><button disabled={busy} onClick={() => void run(async () => {
      if (pending.action === 'reset_password' || pending.action === 'delete') { await execute(pending); return; }
      let next: string | null = null; let current: User | undefined;
      do {
        const page: { data: { items: User[] }; meta: { next_cursor: string | null; has_more: boolean } } = await pageApi<{ items: User[] }>('/api/v1/admin/users' + (next ? '?cursor=' + encodeURIComponent(next) : ''), { headers: { 'X-Expected-Actor': actor } });
        current = page.data.items.find(row => row.id === pending.target); next = page.meta.next_cursor;
      } while (!current && next);
      if (!alive.current) return;
      setPending(null); setPreview(null); setSelected(current ?? null); setPassword('');
      setNotice(current ? '已读取当前账号状态，请核对列表。若仍需修改，请重新预览。' : '账号已不可用。');
      if (current) setEmail(current.email);
      await load();
    })}>核查原请求</button><button disabled={busy} onClick={() => { setPending(null); setPreview(null); setSelected(null); }}>放弃待核查请求</button></div>}
    <ul>{users.map(user => <li key={user.id}><button disabled={busy || !!pending} onClick={() => choose(user)}>{user.username} · {user.is_admin ? '管理员' : '普通用户'} · {user.enabled ? '启用' : '禁用'}</button><span> {user.email}</span></li>)}</ul>
    {cursor && <button disabled={busy} onClick={() => void run(() => load(cursor))}>更多账号</button>}
    {selected && <div><h3>账号：{selected.username}</h3><p>创建：{selected.created_at}；最近登录：{selected.last_login_at ?? '从未登录'}</p>
      <label>账号操作<select aria-label="账号操作" disabled={busy || !!pending} value={action} onChange={e => { setAction(e.target.value); setPreview(null); setAck(false); }}>
        <option value="change_email">修改邮箱</option><option value="reset_password">重置密码</option>
        {!selected.is_admin && <><option value={selected.enabled ? 'disable' : 'enable'}>{selected.enabled ? '禁用' : '启用'}</option><option value="delete">删除普通账号</option></>}
        {selected.id !== actor && <option value={selected.is_admin ? 'revoke_admin' : 'grant_admin'}>{selected.is_admin ? '撤销管理员' : '授予管理员'}</option>}
      </select></label>
      {action === 'change_email' && <label>新的邮箱<input value={email} disabled={busy || !!pending} onChange={e => { setEmail(e.target.value); setPreview(null); setAck(false); }}/></label>}
      <button disabled={busy || !!pending} onClick={() => void run(async () => {
        const value = await write<Preview>('/api/v1/admin/users/' + selected.id + '/action-preview', { action, expected_revision: selected.revision, ...(action === 'change_email' ? { email } : {}) }, undefined, actor);
        if (alive.current) { setPreview(value); setAck(false); }
      })}>预览账号操作</button>
      {preview && <div>{preview.risks.map(r => <p key={r.id}>{r.message}</p>)}<label><input type="checkbox" checked={ack} disabled={busy || !!pending} onChange={e => setAck(e.target.checked)}/>我已核对目标账号及上述影响</label>
        <button disabled={!ack || busy || !!pending} onClick={() => {
          const command = { target: selected.id, action, key: crypto.randomUUID(), body: { expected_revision: selected.revision, confirmation_token: preview.confirmation_token, acknowledged_risk_ids: preview.risks.map(r => r.id), ...(action === 'reset_password' || action === 'delete' ? {} : { action }), ...(action === 'change_email' ? { email } : {}) } };
          setPending(command); void run(() => execute(command));
        }}>确认执行账号操作</button></div>}
    </div>}
  </section>;
}
