import { useEffect, useRef, useState } from 'react';

type API = <T>(url: string, init?: RequestInit) => Promise<T>;
type Write = <T>(url: string, body: unknown, key?: string, actor?: string, method?: string) => Promise<T>;
type Settings = {connection_timeout_seconds: number; connection_retry_count: number; config_snapshot_retention_days: number; diagnostic_scope: 'minimal' | 'standard'};
type View = {revision: string; configured: boolean; effective: Settings};
const path = '/api/v1/admin/security-config';
const initial: Settings = {connection_timeout_seconds: 30, connection_retry_count: 0, config_snapshot_retention_days: 30, diagnostic_scope: 'minimal'};

export function SecuritySettings({api, write, actor, onBusy, onAuthFailure}: {api: API; write: Write; actor: string; onBusy: (value: boolean) => void; onAuthFailure: (error: unknown) => void}) {
  const [current, setCurrent] = useState<View | null>(null);
  const [draft, setDraft] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [message, setMessage] = useState('');
  const alive = useRef(true);
  const read = () => api<View>(path, {headers: {'X-Expected-Actor': actor}});
  function accept(value: View) { setCurrent(value); setDraft(value.effective); setUncertain(false); }
  function fail(error: unknown, writing: boolean) {
    const e = error as {status?: number; code?: string};
    if (e.status === 401 || e.code === 'PERMISSION_CSRF_REJECTED') onAuthFailure(error);
    if (e.status === 412) { setUncertain(true); setMessage('安全配置已被其他管理员修改。草稿保留，请核查当前配置。'); }
    else if (e.status === 404) { setUncertain(true); setMessage('安全配置不可用，请核查当前账号权限。'); }
    else if ([400, 413, 415, 422, 428].includes(e.status ?? 0)) setMessage('输入未通过校验：超时和保留天数须为正整数，重试次数为0–5。');
    else { if (writing) setUncertain(true); setMessage(writing ? '保存结果尚未确认。请读取当前配置，避免覆盖其他管理员的修改。' : '读取安全配置失败，请重试。'); }
  }
  async function run(action: () => Promise<void>, writing = false) {
    setBusy(true); onBusy(true); setMessage('');
    try { await action(); } catch (e) { if (alive.current) fail(e, writing); }
    finally { if (alive.current) { setBusy(false); onBusy(false); } }
  }
  useEffect(() => {
    alive.current = true;
    void read().then(value => { if (alive.current) accept(value); }).catch(e => { if (alive.current) fail(e, false); });
    return () => { alive.current = false; };
  }, [actor]);
  async function load() { await run(async () => { const value = await read(); if (alive.current) { accept(value); setMessage('已加载当前安全配置。'); } }); }
  async function save() {
    if (!current) return;
    if (![draft.connection_timeout_seconds, draft.config_snapshot_retention_days].every(v => Number.isSafeInteger(v) && v > 0) || !Number.isSafeInteger(draft.connection_retry_count) || draft.connection_retry_count < 0 || draft.connection_retry_count > 5) { setMessage('请输入范围内的整数。'); return; }
    await run(async () => { const value = await write<View>(path, {...draft, expected_revision: current.revision}, undefined, actor, 'PUT'); if (alive.current) { accept(value); setMessage('安全配置已保存。'); } }, true);
  }
  return <section className="form-card" aria-label="基础安全设置" aria-busy={busy}>
    <h2>基础安全设置</h2>
    <p>设置配置连接测试的预算与脱敏诊断；不会修改个人配置，也不会重发已提交且结果未知的请求。</p>
    {message && <p role="status">{message}</p>}
    {!current && <button disabled={busy} onClick={() => void load()}>重新读取安全配置</button>}
    {current && <p>{current.configured ? '当前使用管理员保存的设置。' : '当前使用系统默认值。'}</p>}
    {uncertain && <button disabled={busy} onClick={() => void load()}>核查安全配置（加载将放弃草稿）</button>}
    <form onSubmit={event => { event.preventDefault(); void save(); }}>
      <label>连接测试超时（秒）<input type="number" min={1} step={1} required value={draft.connection_timeout_seconds || ''} disabled={busy || uncertain || !current} onChange={e => setDraft({...draft, connection_timeout_seconds: Number(e.target.value)})}/></label>
      <label>连接建立重试次数<input type="number" min={0} max={5} step={1} required value={draft.connection_retry_count} disabled={busy || uncertain || !current} onChange={e => setDraft({...draft, connection_retry_count: Number(e.target.value)})}/></label>
      <p className="hint">仅重试能够确认尚未提交请求的连接失败，不重发模型生成或未知结果。</p>
      <label>诊断快照保留天数<input type="number" min={1} step={1} required value={draft.config_snapshot_retention_days || ''} disabled={busy || uncertain || !current} onChange={e => setDraft({...draft, config_snapshot_retention_days: Number(e.target.value)})}/></label>
      <p className="hint">仅适用于可清理诊断，不删除运行冻结输入、人工确认内容或引用依赖。</p>
      <label>诊断信息范围<select aria-label="诊断信息范围" value={draft.diagnostic_scope} disabled={busy || uncertain || !current} onChange={e => setDraft({...draft, diagnostic_scope: e.target.value as Settings['diagnostic_scope']})}><option value="minimal">最小诊断</option><option value="standard">标准诊断</option></select></label>
      <p className="hint">两级均不包含密钥或私人正文。标准诊断增加耗时、内部尝试次数和协议类别。</p>
      <div className="list-pages"><button type="submit" disabled={busy || uncertain || !current}>保存安全配置</button><button type="button" disabled={busy || !current} onClick={() => { if (uncertain) void load(); else if (current) { accept(current); setMessage(''); } }}>取消安全编辑</button></div>
    </form>
  </section>;
}
