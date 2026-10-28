import { useEffect, useRef, useState } from 'react';

type API = <T>(url: string, init?: RequestInit) => Promise<T>;
type Write = <T>(url: string, body: unknown, key?: string, actor?: string, method?: string) => Promise<T>;
type Secret = {configured: boolean; hint?: string | null};
type Config = {sender_email: string; provider: string; server: string; port: number; encryption: string; auth_type: string; username: string | null; secret: Secret; oauth: {client_id: string; tenant: string | null; client_secret: Secret} | null; oauth_status: string; connection_status: string; last_test_at: string | null};
type View = {revision: string; configured: boolean; config: Config | null};
type Task = {task_id: string; status_url: string; execution_status: string; error: {code: string} | null; result_refs: {url: string}[]};
type Draft = {sender_email: string; provider: string; server: string; port: string; encryption: string; auth_type: string; username: string; secret: string; clearSecret: boolean; clientId: string; clientSecret: string; clearClientSecret: boolean; tenant: string};
type Pending = {kind: 'test' | 'oauth'; path: string; key: string; body: unknown};
const base = '/api/v1/admin/smtp-config';
const presets: Record<string, {name: string; host: string; port: string; encryption: string; auth: string[]}> = {
  custom: {name: '自定义 SMTP', host: '', port: '587', encryption: 'starttls', auth: ['none', 'password']},
  qq: {name: 'QQ邮箱', host: 'smtp.qq.com', port: '465', encryption: 'ssl_tls', auth: ['password']},
  '163': {name: '163邮箱', host: 'smtp.163.com', port: '465', encryption: 'ssl_tls', auth: ['password']},
  gmail: {name: 'Gmail', host: 'smtp.gmail.com', port: '587', encryption: 'starttls', auth: ['token', 'password']},
  microsoft365: {name: 'Microsoft 365', host: 'smtp.office365.com', port: '587', encryption: 'starttls', auth: ['token']},
  sendgrid: {name: 'SendGrid', host: 'smtp.sendgrid.net', port: '587', encryption: 'starttls', auth: ['api_key']},
};
const labels: Record<string, string> = {none: '无认证', password: '用户名＋密码类凭据', token: 'OAuth 授权', api_key: 'API Key'};
const fresh = (): Draft => ({sender_email: '', provider: 'qq', server: presets.qq.host, port: '465', encryption: 'ssl_tls', auth_type: 'password', username: '', secret: '', clearSecret: false, clientId: '', clientSecret: '', clearClientSecret: false, tenant: ''});
function draftFor(c: Config | null): Draft { return c ? {sender_email: c.sender_email, provider: c.provider, server: c.server, port: String(c.port), encryption: c.encryption, auth_type: c.auth_type, username: c.username ?? '', secret: '', clearSecret: false, clientId: c.oauth?.client_id ?? '', clientSecret: '', clearClientSecret: false, tenant: c.oauth?.tenant ?? ''} : fresh(); }
const oauthLabels: Record<string, string> = {not_connected: '尚未授权', connected: '已授权，可按需刷新', reauthorization_required: '需要重新授权', refreshing: '正在刷新凭据；若刷新中断，请重新授权'};

export function SMTPSettings({api: baseApi, write, actor, onBusy, onAuthFailure}: {api: API; write: Write; actor: string; onBusy: (value: boolean) => void; onAuthFailure: (error: unknown) => void}) {
  const [current, setCurrent] = useState<View | null>(null);
  const [draft, setDraft] = useState<Draft>(fresh);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [message, setMessage] = useState('');
  const [task, setTask] = useState<Task | null>(null);
  const [details, setDetails] = useState<string | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const [showSecret, setShowSecret] = useState(false);
  const alive = useRef(true);
  const api: API = (url, init) => baseApi(url, {...init, headers: {...init?.headers, 'X-Expected-Actor': actor}});
  function accept(value: View) { setCurrent(value); setDraft(draftFor(value.config)); setDirty(false); setUncertain(false); setShowSecret(false); }
  function change(value: Partial<Draft>) { setDraft(previous => ({...previous, ...value})); setDirty(true); }
  function fail(error: unknown, writing: boolean) {
    const e = error as {status?: number; code?: string};
    if (e.status === 401 || e.code === 'PERMISSION_CSRF_REJECTED') onAuthFailure(error);
    if (e.status === 412) { setUncertain(true); setPending(null); setMessage('SMTP配置已被其他操作修改。草稿保留，请核查当前配置。'); }
    else if ([400, 403, 404, 409, 413, 415, 422, 428].includes(e.status ?? 0)) { setPending(null); setMessage(e.status === 404 ? 'SMTP配置不可用，请核查账号权限。' : '操作未完成，请检查配置、凭据及授权状态后重试。'); }
    else { if (writing) setUncertain(true); setMessage(writing ? '请求结果尚未确认，请先核查当前状态。' : '读取SMTP配置失败，请重试。'); }
  }
  async function run(action: () => Promise<void>, writing = false) {
    setBusy(true); onBusy(true); setMessage('');
    try { await action(); } catch (e) { if (alive.current) fail(e, writing); }
    finally { if (alive.current) { setBusy(false); onBusy(false); } }
  }
  useEffect(() => {
    alive.current = true;
    void api<View>(base).then(value => { if (alive.current) accept(value); }).catch(e => { if (alive.current) fail(e, false); });
    return () => { alive.current = false; };
  }, [actor]);
  async function load() {
    await run(async () => { const value = await api<View>(base); if (alive.current) { accept(value); setTask(null); setDetails(null); setMessage('已加载当前SMTP配置。'); } });
  }
  function secretWrite(value: string, clear: boolean) { return clear ? {operation: 'clear'} : value ? {operation: 'set', value} : undefined; }
  async function save() {
    if (!current) return;
    const port = Number(draft.port);
    if (!Number.isSafeInteger(port) || port < 1 || port > 65535) { setMessage('端口须为1–65535的整数。'); return; }
    const body = {
      expected_revision: current.revision, sender_email: draft.sender_email, provider: draft.provider,
      server: draft.server, port, encryption: draft.encryption, auth_type: draft.auth_type,
      username: draft.auth_type === 'none' || draft.auth_type === 'api_key' ? null : draft.username,
      ...(draft.auth_type === 'password' || draft.auth_type === 'api_key' ? {secret: secretWrite(draft.secret, draft.clearSecret)} : {}),
      oauth: draft.auth_type === 'token' ? {client_id: draft.clientId, tenant: draft.provider === 'microsoft365' ? draft.tenant : null, client_secret: secretWrite(draft.clientSecret, draft.clearClientSecret)} : null,
    };
    await run(async () => { const value = await write<View>(base, body, undefined, actor, 'PUT'); if (alive.current) { accept(value); setTask(null); setDetails(null); setMessage('SMTP配置已保存；保存不会连接外部服务。'); } }, true);
  }
  async function submit(command: Pending) {
    if (command.kind === 'test') { const value = await write<Task>(command.path, command.body, command.key, actor); if (alive.current) { setTask(value); setDetails(null); setPending(null); setUncertain(false); } }
    else {
      const value = await write<{authorization_url: string; expires_at: string}>(command.path, command.body, command.key, actor);
      if (!alive.current) return;
      setPending(null); setUncertain(false);
      if (!Number.isFinite(Date.parse(value.expires_at)) || Date.parse(value.expires_at) <= Date.now()) { setMessage('本次授权链接已过期，请重新连接账号。'); return; }
      const url = new URL(value.authorization_url);
      if (url.protocol !== 'https:' || !['accounts.google.com', 'login.microsoftonline.com'].includes(url.hostname)) throw new Error('Invalid authorization destination');
      window.location.assign(url.href);
    }
  }
  async function start(kind: Pending['kind']) {
    if (!current) return;
    await run(async () => { const command: Pending = {kind, key: crypto.randomUUID(), path: base + (kind === 'test' ? '/test' : '/oauth/start'), body: kind === 'test' ? {} : {expected_revision: current.revision}}; setPending(command); await submit(command); }, true);
  }
  async function recover() { if (pending) await run(() => submit(pending), true); else await load(); }
  async function poll() {
    if (!task || !current) return;
    await run(async () => {
      const value = await api<Task>(task.status_url); if (!alive.current) return; setTask(value);
      if (!['succeeded', 'failed'].includes(value.execution_status)) return;
      if (value.result_refs.length) { const result = await api<{payload: {reason_code: string | null}}>(value.result_refs[0].url); if (!alive.current) return; setDetails(result.payload.reason_code ?? '成功'); }
      const latest = await api<View>(base); if (!alive.current) return;
      if (latest.revision !== current.revision) { setUncertain(true); setMessage('SMTP配置已变化，请核查当前配置；原测试不代表新配置可用。'); }
      else { setCurrent(latest); setMessage(value.execution_status === 'succeeded' ? 'SMTP连接测试成功。' : 'SMTP连接测试失败，请修复配置或重新授权。'); }
    });
  }
  const disabled = busy || uncertain || !!pending || !current;
  return <section className="form-card" aria-label="系统SMTP设置" aria-busy={busy}>
    <h2>系统 SMTP</h2><p>维护一套平台发件配置。测试仅验证连接和认证，不发送邮件。</p>
    {message && <p role="status">{message}</p>}
    {!current && <button disabled={busy} onClick={() => void load()}>重新读取SMTP配置</button>}
    {(uncertain || pending) && <button disabled={busy} onClick={() => void recover()}>{pending ? '核查同一SMTP请求' : '核查SMTP配置（加载将放弃草稿）'}</button>}
    <form onSubmit={event => { event.preventDefault(); void save(); }}>
      <label>邮件服务<select aria-label="邮件服务" value={draft.provider} disabled={disabled} onChange={e => { const provider = e.target.value; const preset = presets[provider]; change({provider, server: preset.host, port: preset.port, encryption: preset.encryption, auth_type: preset.auth[0], secret: '', clearSecret: true, clientId: '', clientSecret: '', clearClientSecret: true, tenant: ''}); }}>{Object.entries(presets).map(([key, value]) => <option key={key} value={key}>{value.name}</option>)}</select></label>
      <label>发件邮箱<input type="email" required value={draft.sender_email} disabled={disabled} onChange={e => change({sender_email: e.target.value})}/></label>
      <label>SMTP服务器<input required value={draft.server} disabled={disabled} onChange={e => change({server: e.target.value})}/></label>
      <label>SMTP端口<input type="number" required min={1} max={65535} step={1} value={draft.port} disabled={disabled} onChange={e => change({port: e.target.value})}/></label>
      <label>连接加密<select aria-label="连接加密" value={draft.encryption} disabled={disabled} onChange={e => change({encryption: e.target.value})}><option value="none">None</option><option value="ssl_tls">SSL-TLS</option><option value="starttls">STARTTLS</option></select></label>
      <label>SMTP认证方式<select aria-label="SMTP认证方式" value={draft.auth_type} disabled={disabled} onChange={e => change({auth_type: e.target.value, secret: '', clearSecret: true, clientSecret: '', clearClientSecret: true})}>{(presets[draft.provider]?.auth ?? []).map(value => <option key={value} value={value}>{labels[value]}</option>)}</select></label>
      {['password', 'token'].includes(draft.auth_type) && <label>SMTP账号<input required autoComplete="off" value={draft.username} disabled={disabled} onChange={e => change({username: e.target.value})}/></label>}
      {['password', 'api_key'].includes(draft.auth_type) && <>
        <label>{draft.auth_type === 'api_key' ? 'SMTP API Key' : 'SMTP授权码或应用密码'}<input type={showSecret ? 'text' : 'password'} autoComplete="new-password" value={draft.secret} disabled={disabled} onChange={e => change({secret: e.target.value, clearSecret: false})}/></label>
        <p className="hint">{current?.config?.secret.configured ? '已保存凭据，留空保持；无法读取明文。' : '尚无已保存凭据。'}{['qq', '163', 'gmail'].includes(draft.provider) ? '请使用服务提供的授权码或应用专用密码，不要填写邮箱登录密码。' : ''}</p>
        <label className="checkbox"><input type="checkbox" checked={draft.clearSecret} disabled={disabled} onChange={e => change({clearSecret: e.target.checked, secret: ''})}/>清除SMTP凭据</label>
      </>}
      {draft.auth_type === 'token' && <fieldset disabled={disabled}><legend>OAuth 应用</legend>
        <p>先由部署方注册对应服务的 OAuth 应用，再保存应用配置并连接发件账号。无需手动粘贴短期 Token。</p>
        <label>OAuth回调地址<input readOnly value={window.location.origin + base + '/oauth/callback'}/></label>
        <p className="hint">{draft.provider === 'gmail' ? 'Google SMTP 授权请求 https://mail.google.com/ 邮箱权限；本平台仅用于SMTP连接和认证测试。' : 'Microsoft 授权请求 SMTP.Send 与 offline_access，用于连接认证和自动刷新。'}</p>
        <label>OAuth Client ID<input required value={draft.clientId} onChange={e => change({clientId: e.target.value})}/></label>
        {draft.provider === 'microsoft365' && <label>Microsoft租户<input required value={draft.tenant} onChange={e => change({tenant: e.target.value})}/></label>}
        <label>OAuth Client Secret<input type={showSecret ? 'text' : 'password'} autoComplete="new-password" value={draft.clientSecret} onChange={e => change({clientSecret: e.target.value, clearClientSecret: false})}/></label>
        <p className="hint">{current?.config?.oauth?.client_secret.configured ? '已保存应用凭据，留空保持；无法读取明文。' : '尚无已保存应用凭据。'}</p>
        <label className="checkbox"><input type="checkbox" checked={draft.clearClientSecret} onChange={e => change({clearClientSecret: e.target.checked, clientSecret: ''})}/>清除OAuth应用凭据</label>
      </fieldset>}
      {draft.auth_type !== 'none' && <label className="checkbox"><input type="checkbox" checked={showSecret} disabled={disabled} onChange={e => setShowSecret(e.target.checked)}/>显示当前输入的凭据</label>}
      <div className="list-pages"><button type="submit" disabled={disabled}>保存SMTP配置</button><button type="button" disabled={busy || !!pending || !current} onClick={() => { if (uncertain) void load(); else if (current) { accept(current); setMessage(''); } }}>取消SMTP编辑</button></div>
    </form>
    {current?.config && <div>
      <p>最近连接状态：{current.config.connection_status}；测试时间：{current.config.last_test_at ?? '未测试'}</p>
      {current.config.auth_type === 'token' && <div><p>OAuth状态：{oauthLabels[current.config.oauth_status] ?? current.config.oauth_status}</p><p className="hint">授权完成后仍须测试连接；授权失效会提示重新授权，不切换其他账号。</p><button disabled={disabled || dirty} onClick={() => void start('oauth')}>{current.config.oauth_status === 'not_connected' ? '连接发件账号' : '重新授权发件账号'}</button></div>}
      <button disabled={disabled || dirty} onClick={() => void start('test')}>测试SMTP连接</button>
      {task && <div role="status">SMTP任务状态：{task.execution_status}<button disabled={busy} onClick={() => void poll()}>刷新SMTP测试状态</button></div>}
      {details !== null && <p aria-label="SMTP测试详情">诊断：{details}</p>}
    </div>}
  </section>;
}
