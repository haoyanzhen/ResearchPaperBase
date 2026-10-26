import { useEffect, useRef, useState, type FormEvent } from 'react';
type API = <T>(url: string, init?: RequestInit) => Promise<T>;
type Write = <T>(url: string, body: unknown, key?: string, actor?: string, method?: string) => Promise<T>;
type Config = {id: string; revision: string; name: string; provider: string; base_url: string; access_mode: string; enabled: boolean; rate_limit_per_minute: number | null; secret: {configured: boolean}; connection_status: string; last_test_at: string | null};
type Task = {task_id: string; status_url: string; execution_status: string; error: {code: string} | null; result_refs: {url: string}[]; operation_id: string};
type Draft = {name: string; provider: string; base_url: string; access_mode: string; enabled: boolean; rate: string; secret: string; clearSecret: boolean};
const defaults: Record<string, string> = {arxiv: 'https://export.arxiv.org/api', openalex: 'https://api.openalex.org', semantic_scholar: 'https://api.semanticscholar.org/graph/v1', ads: 'https://api.adsabs.harvard.edu/v1'};
const fresh = (): Draft => ({name: '', provider: 'arxiv', base_url: defaults.arxiv, access_mode: 'anonymous', enabled: true, rate: '', secret: '', clearSecret: false});
const draftFor = (c: Config): Draft => ({name: c.name, provider: c.provider, base_url: c.base_url, access_mode: c.access_mode, enabled: c.enabled, rate: c.rate_limit_per_minute === null ? '' : String(c.rate_limit_per_minute), secret: '', clearSecret: false});
function errorText(e: unknown) { const value = e as {status?: number}; if (value.status === 412) return '配置已被其他操作修改。草稿保留，请核查当前内容。'; if ([400, 422].includes(value.status ?? 0)) return '输入未通过校验，请检查数据源类型、访问模式、地址和速率。'; return '请求结果尚未确认，请核查当前状态。'; }
export function SourceSettings({ api: baseApi, pageApi: basePageApi, write, actor, onChange, onBusy, onAuthFailure }: { api: API; pageApi: <T>(url: string, init?: RequestInit) => Promise<{ data: T; meta: {next_cursor: string | null; has_more: boolean} }>; write: Write; actor: string; onChange: () => void; onBusy: (v: boolean) => void; onAuthFailure: (e: unknown) => void }) {
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const api: API = (url, init) => baseApi(url, { ...init, headers: { ...init?.headers, 'X-Expected-Actor': actor } });
  const pageApi: typeof basePageApi = (url, init) => basePageApi(url, { ...init, headers: { ...init?.headers, 'X-Expected-Actor': actor } });
  const [configs, setConfigs] = useState<Config[]>([]);
  const [selected, setSelected] = useState<Config | null>(null);
  const [draft, setDraft] = useState<Draft>(fresh);
  const [dirty, setDirty] = useState(false);
  const [switchTo, setSwitchTo] = useState<Config | null | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [message, setMessage] = useState('');
  const [pending, setPending] = useState<{ key: string; path: string; body: unknown } | null>(null);
  const [consent, setConsent] = useState(false);
  const [task, setTask] = useState<Task | null>(null);
  const [testDetails, setTestDetails] = useState<{reason_code: string | null; access_mode: string} | null>(null);
  async function listing() { const all: Config[] = []; let cursor: string | null = null; do { const page: {data: {items: Config[]}; meta: {next_cursor: string | null; has_more: boolean}} = await pageApi<{items: Config[]}>('/api/v1/me/data-source-configs?page_size=100' + (cursor ? '&cursor=' + encodeURIComponent(cursor) : '')); all.push(...page.data.items); cursor = page.meta.has_more ? page.meta.next_cursor : null; } while (cursor); setConfigs(all); }
  useEffect(() => { void listing().catch(e => { if (alive.current) onAuthFailure(e); setMessage('配置列表读取失败。'); }); }, [actor]);
  function enter(c: Config | null) { setSelected(c); setDraft(c ? draftFor(c) : fresh()); setDirty(false); setSwitchTo(undefined); setUncertain(false); setPending(null); setTask(null); setTestDetails(null); setConsent(false); setMessage(''); }
  function switchConfig(c: Config | null) { if (dirty || uncertain || pending) setSwitchTo(c); else enter(c); }
  function change(value: Partial<Draft>) { setDraft(prev => ({ ...prev, ...value })); setDirty(true); }
  async function run(action: () => Promise<void>, writing = false) {
    setBusy(true); if (alive.current) onBusy(true); setMessage('');
    try { await action(); }
    catch (e) { if (alive.current) onAuthFailure(e); setMessage(errorText(e)); const status = (e as { status?: number }).status; if (writing && ![400, 403, 404, 409, 413, 415, 422, 428].includes(status ?? 0)) setUncertain(true); if ([400, 403, 404, 409, 413, 415, 422, 428].includes(status ?? 0)) setPending(null); }
    finally { setBusy(false); if (alive.current) onBusy(false); }
  }
  function body() {
    const rate = draft.rate === '' ? null : Number(draft.rate);
    if (rate !== null && (!Number.isSafeInteger(rate) || rate < 1)) throw new Error('rate');
    return { name: draft.name, provider: draft.provider, base_url: draft.base_url, access_mode: draft.access_mode, enabled: draft.enabled, rate_limit_per_minute: rate, ...(draft.clearSecret ? {secret: {operation: 'clear'}} : draft.secret ? {secret: {operation: 'set', value: draft.secret}} : {}), ...(selected ? {expected_revision: selected.revision} : {}) };
  }
  async function save(next?: Config | null) {
    let payload: unknown;
    try { payload = body(); } catch { setMessage('速率必须为正整数，留空使用数据源默认。'); return; }
    await run(async () => {
      const command = pending ?? { key: crypto.randomUUID(), path: '/api/v1/me/data-source-configs', body: payload };
      if (!selected) setPending(command);
      const result = await write<Config>(selected ? '/api/v1/me/data-source-configs/' + selected.id : command.path, selected ? payload : command.body, selected ? undefined : command.key, actor, selected ? 'PATCH' : 'POST');
      setTask(null); setTestDetails(null); setSelected(result); setDraft(draftFor(result)); setDirty(false); setPending(null); setUncertain(false); setMessage('配置已保存；保存不会调用外部服务。'); setConsent(false); await listing(); onChange(); if (next !== undefined) enter(next);
    }, true);
  }
  async function loadCurrent() {
    await run(async () => {
      if (pending && pending.path !== '/api/v1/me/data-source-configs') { const restored = await write<Task>(pending.path, pending.body, pending.key, actor); setTask(restored); setPending(null); setUncertain(false); }
      else if (pending) { const restored = await write<Config>(pending.path, pending.body, pending.key, actor); enter(restored); }
      else if (selected) { try { enter(await api<Config>('/api/v1/me/data-source-configs/' + selected.id)); } catch (e) { if ((e as {status?: number}).status === 404) enter(null); else throw e; } }
      await listing(); onChange();
    });
  }
  async function start() {
    if (!selected) return;
    await run(async () => {
      const command = pending ?? { key: crypto.randomUUID(), path: '/api/v1/me/data-source-configs/' + selected.id + '/test', body: {} };
      setTestDetails(null); setPending(command); const started = await write<Task>(command.path, command.body, command.key, actor); setTask(started); setPending(null); setUncertain(false);
    }, true);
  }
  async function poll() {
    if (!task) return;
    await run(async () => {
      const current = await api<Task>(task.status_url); setTask(current);
      if (['succeeded', 'failed'].includes(current.execution_status)) { if (current.result_refs.length) { const result = await api<{payload: {reason_code: string | null; access_mode: string}}>(current.result_refs[0].url); setTestDetails(result.payload); } setMessage(current.execution_status === 'succeeded' ? '连接测试成功。' : '操作失败：' + current.error?.code); if (selected) { const latest = await api<Config>('/api/v1/me/data-source-configs/' + selected.id); if (latest.revision !== selected.revision) { setMessage('配置已被其他操作修改。草稿保留，请核查当前内容。'); setUncertain(true); setTask(null); setTestDetails(null); } else { setSelected(previous => previous ? { ...previous, connection_status: latest.connection_status, last_test_at: latest.last_test_at } : previous); } } await listing(); onChange(); }
    });
  }
  return <section className="form-card" aria-label="数据源设置" aria-busy={busy}><h2>个人数据源配置{selected ? ' / ' + selected.name : ' / 新增'}</h2>
    <p>配置只供本人使用。检索服务入口与具体文件地址分开；保存不调用外部服务。</p>
    {message && <p role="alert">{message}</p>}
    <div className="list-pages"><button disabled={busy} onClick={() => switchConfig(null)}>新增数据源配置</button><button disabled={busy} onClick={() => void run(listing)}>刷新数据源列表</button>{configs.map(c => <button key={c.id} disabled={busy} onClick={() => switchConfig(c)}>{c.name} · {c.enabled ? '启用' : '禁用'}</button>)}</div>
    {switchTo !== undefined && <div role="group" aria-label="未保存修改"><p>有未保存或未核实的修改。</p><button disabled={busy || uncertain || !!pending} onClick={() => void save(switchTo)}>保存并切换</button><button disabled={busy || uncertain || !!pending} onClick={() => enter(switchTo)}>放弃并切换</button><button disabled={busy} onClick={() => setSwitchTo(undefined)}>留在当前配置</button></div>}
    {uncertain && <button disabled={busy} onClick={() => void loadCurrent()}>核查当前配置（加载将放弃草稿）</button>}
    <form onSubmit={(e: FormEvent) => { e.preventDefault(); void save(); }}>
      <label>数据源名称<input required maxLength={200} value={draft.name} disabled={busy || uncertain} onChange={e => change({name: e.target.value})}/></label>
      <label>数据源类型<select aria-label="数据源类型" value={draft.provider} disabled={busy || uncertain} onChange={e => { const provider = e.target.value; change({provider, base_url: defaults[provider], access_mode: provider === 'ads' ? 'api_key' : 'anonymous'}); }}>{Object.keys(defaults).map(p => <option key={p}>{p}</option>)}</select></label>
      <label>检索服务/API入口<input type="url" required value={draft.base_url} disabled={busy || uncertain} onChange={e => change({base_url: e.target.value})}/></label><p>填写对应服务API入口，不是搜索网页或单个文件地址。</p>
      <label>访问模式<select aria-label="访问模式" value={draft.access_mode} disabled={busy || uncertain} onChange={e => change({access_mode: e.target.value})}>{draft.provider !== 'ads' && <option value="anonymous">匿名</option>}{draft.provider !== 'arxiv' && <option value="api_key">API密钥</option>}</select></label>
      <label><input type="checkbox" checked={draft.enabled} disabled={busy || uncertain} onChange={e => change({enabled: e.target.checked})}/>启用数据源</label>
      <label>每分钟请求数<input type="number" min={1} step={1} value={draft.rate} disabled={busy || uncertain} onChange={e => change({rate: e.target.value})}/></label><p>留空采用适配器默认；服务端仍可能返回限流。连接测试不执行资料下载。</p>
      <label>数据源API密钥（留空保持已存值）<input type="password" autoComplete="new-password" value={draft.secret} disabled={busy || uncertain || draft.clearSecret} onChange={e => change({secret: e.target.value})}/></label>
      <p>{selected?.secret.configured ? '已保存凭据，无法读取明文。' : '尚无已保存凭据。'}匿名模式不会发送已保存密钥。</p>
      <label><input type="checkbox" checked={draft.clearSecret} disabled={busy || uncertain} onChange={e => change({clearSecret: e.target.checked, secret: ''})}/>清除数据源凭据</label>
      <button type="submit" disabled={busy || uncertain || !!pending}>保存数据源配置</button><button type="button" disabled={busy} onClick={() => { if (uncertain || pending) void loadCurrent(); else enter(selected); }}>取消数据源编辑</button>
    </form>
    {selected && <div><p>最近连接状态：{selected.connection_status}；测试时间：{selected.last_test_at ?? '未测试'}</p><label><input type="checkbox" checked={consent} disabled={busy} onChange={e => setConsent(e.target.checked)}/>我了解测试会向已保存的数据源发送固定查询，可能消耗服务额度。</label>
      <button disabled={busy || dirty || uncertain || !!pending || !consent} onClick={() => void start()}>测试数据源连接</button>
      {pending && <button disabled={busy} onClick={() => void loadCurrent()}>核查同一请求</button>}
      {task && <div role="status">任务状态：{task.execution_status}<button disabled={busy} onClick={() => void poll()}>刷新数据源测试状态</button></div>}
      {testDetails && <div aria-label="数据源测试详情"><p>诊断：{testDetails.reason_code ?? '成功'}</p><p>访问模式：{testDetails.access_mode}</p></div>}
      <button disabled={busy || dirty || uncertain || !!pending} onClick={() => { if (window.confirm('删除此数据源配置？已保存任务快照保持原义。')) void run(async () => { await write('/api/v1/me/data-source-configs/' + selected.id + '?expected_revision=' + selected.revision, undefined, undefined, actor, 'DELETE'); enter(null); await listing(); onChange(); }, true); }}>删除数据源配置</button>
    </div>}
  </section>;
}
