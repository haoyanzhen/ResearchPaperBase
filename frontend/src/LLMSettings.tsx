import { parseParameterJson } from './parameterJson';
import { useEffect, useState, type FormEvent } from 'react';

type API = <T>(url: string, init?: RequestInit) => Promise<T>;
type Write = <T>(url: string, body: unknown, key?: string, actor?: string, method?: string) => Promise<T>;
type Option = { source: string; config_id: string; model_id: string; label: string; available: boolean };
type Selection = { revision: string; selection: Pick<Option, 'source' | 'config_id' | 'model_id'> | null; valid: boolean };
type Config = { id: string; revision: string; name: string; provider: string; protocol: string; base_url: string; api_version: string; timeout_seconds: number; parameters: Record<string, unknown>; secret: { configured: boolean }; models: Option[] };
type Task = { task_id: string; status_url: string; execution_status: string; error: { code: string } | null; result_refs: {url: string}[]; operation_id: string };
type Draft = { name: string; provider: string; protocol: string; base_url: string; api_version: string; secret: string; clearSecret: boolean; timeout: string; temperature: string; top_p: string; max_output_tokens: string; extra: string };
const fresh = (): Draft => ({ name: '', provider: 'openai', protocol: 'openai_chat', base_url: 'https://api.openai.com/v1', api_version: '', secret: '', clearSecret: false, timeout: '30', temperature: '', top_p: '', max_output_tokens: '', extra: '{}' });
function draftFor(c: Config): Draft {
  const { temperature, top_p, max_output_tokens, ...extra } = c.parameters;
  return { name: c.name, provider: c.provider, protocol: c.protocol, base_url: c.base_url, api_version: c.api_version, secret: '', clearSecret: false, timeout: String(c.timeout_seconds), temperature: temperature === undefined ? '' : String(temperature), top_p: top_p === undefined ? '' : String(top_p), max_output_tokens: max_output_tokens === undefined ? '' : String(max_output_tokens), extra: JSON.stringify(extra, null, 2) };
}
function errorText(e: unknown): string {
  const value = e as { status?: number; code?: string };
  if (value.status === 412) return '配置已被其他操作修改。草稿保留，请核查当前内容。';
  if (value.code === 'CONFIG_SECRET_UNAVAILABLE') return '凭据不可用，请配置密钥或检查服务端密钥保管设置。';
  if (value.code === 'CONFIG_CONNECTION_FAILED') return '该模型尚未通过当前配置的测试，请先测试或修复配置。';
  if (value.status === 422 || value.status === 400) return '输入未通过校验。请检查参数类型、范围、协议及重复字段。';
  return '请求结果尚未确认。请核查当前状态，勿重复新建请求。';
}

export function ModelPicker({ api: baseApi, write, actor, revision, onAuthFailure }: { api: API; write: Write; actor: string; revision: number; onAuthFailure: (e: unknown) => void }) {
  const api: API = (url, init) => baseApi(url, { ...init, headers: { ...init?.headers, 'X-Expected-Actor': actor } });
  const [selection, setSelection] = useState<Selection | null>(null);
  const [options, setOptions] = useState<Option[]>([]);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  async function load() {
    try { const [s, o] = await Promise.all([api<Selection>('/api/v1/me/model-selection'), api<{ items: Option[] }>('/api/v1/me/model-options')]); setSelection(s); setOptions(o.items.filter(v => v.available)); }
    catch (e) { onAuthFailure(e); setMessage('模型选择读取失败，请刷新。'); }
  }
  useEffect(() => { void load(); const handler = () => void load(); window.addEventListener('focus', handler); return () => window.removeEventListener('focus', handler); }, [actor, revision]);
  const identity = (o: Pick<Option, 'source' | 'config_id' | 'model_id'>) => JSON.stringify([o.source, o.config_id, o.model_id]);
  async function choose(value: string) {
    if (!selection) return;
    const item = options.find(o => identity(o) === value);
    setBusy(true); setMessage('');
    try { setSelection(await write<Selection>('/api/v1/me/model-selection', { expected_revision: selection.revision, selection: item ? { source: item.source, config_id: item.config_id, model_id: item.model_id } : null }, undefined, actor, 'PUT')); }
    catch (e) { onAuthFailure(e); setMessage(errorText(e)); }
    finally { setBusy(false); }
  }
  return <div aria-label="模型选择"><label>当前模型<select aria-label="当前模型" disabled={busy || !selection} value={selection?.selection ? identity(selection.selection) : ''} onChange={e => void choose(e.target.value)}><option value="">请选择模型</option>{selection?.selection && !selection.valid && <option value={identity(selection.selection)}>原模型已失效，请修复配置</option>}{options.map(o => <option key={identity(o)} value={identity(o)}>{o.label}</option>)}</select></label><button disabled={busy} onClick={() => void load()}>刷新模型选择</button>{message && <p role="alert">{message}</p>}</div>;
}

export function LLMSettings({ api: baseApi, pageApi: basePageApi, write, actor, onChange, onBusy, onAuthFailure, system = false, active = true }: { active?: boolean; system?: boolean; api: API; pageApi: <T>(url: string, init?: RequestInit) => Promise<{ data: T; meta: {next_cursor: string | null; has_more: boolean} }>; write: Write; actor: string; onChange: () => void; onBusy: (v: boolean) => void; onAuthFailure: (e: unknown) => void }) {
  const configPath = system ? '/api/v1/admin/llm-configs' : '/api/v1/me/llm-configs';
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
  const [customKey, setCustomKey] = useState('');
  const [customValue, setCustomValue] = useState('');
  const [model, setModel] = useState('');
  const [consent, setConsent] = useState(false);
  const [task, setTask] = useState<Task | null>(null);
  const [testDetails, setTestDetails] = useState<{reason_code: string | null; tested_parameters: unknown; test_overrides: unknown} | null>(null);
  async function listing() { const all: Config[] = []; let cursor: string | null = null; do { const page: {data: {items: Config[]}; meta: {next_cursor: string | null; has_more: boolean}} = await pageApi<{items: Config[]}>(configPath + '?page_size=100' + (cursor ? '&cursor=' + encodeURIComponent(cursor) : '')); all.push(...page.data.items); cursor = page.meta.has_more ? page.meta.next_cursor : null; } while (cursor); setConfigs(all); }
  useEffect(() => { if (active) void listing().catch(e => { onAuthFailure(e); setMessage('配置列表读取失败。'); }); }, [actor, active]);
  function enter(c: Config | null) { setSelected(c); setDraft(c ? draftFor(c) : fresh()); setDirty(false); setSwitchTo(undefined); setUncertain(false); setPending(null); setTask(null); setTestDetails(null); setConsent(false); setMessage(''); setModel(''); }
  function switchConfig(c: Config | null) { if (dirty || uncertain || pending) setSwitchTo(c); else enter(c); }
  function change(value: Partial<Draft>) { setDraft(prev => ({ ...prev, ...value })); setDirty(true); }
  async function run(action: () => Promise<void>, writing = false) {
    setBusy(true); onBusy(true); setMessage('');
    try { await action(); }
    catch (e) { onAuthFailure(e); setMessage(errorText(e)); const status = (e as { status?: number }).status; if (writing && ![400, 403, 404, 409, 413, 415, 422, 428].includes(status ?? 0)) setUncertain(true); if ([400, 403, 404, 409, 413, 415, 422, 428].includes(status ?? 0)) setPending(null); }
    finally { setBusy(false); onBusy(false); }
  }
  function body() {
    const parameters = parseParameterJson(draft.extra);
    if (!parameters || typeof parameters !== 'object' || Array.isArray(parameters)) throw new Error('参数必须是JSON对象');
    for (const key of ['temperature', 'top_p', 'max_output_tokens'] as const) {
      if (draft[key] !== '') { if (key in parameters) throw new Error('常用字段不能在高级参数中重复'); const value = Number(draft[key]); if (!Number.isFinite(value)) throw new Error('参数必须是有限数字'); parameters[key] = value; }
    }
    return { name: draft.name, provider: draft.provider, protocol: draft.protocol, base_url: draft.base_url, api_version: draft.api_version, parameters, timeout_seconds: Number(draft.timeout), ...(draft.clearSecret ? { secret: { operation: 'clear' } } : draft.secret ? { secret: { operation: 'set', value: draft.secret } } : {}), ...(selected ? { expected_revision: selected.revision } : {}) };
  }
  async function save(next?: Config | null) {
    let payload: unknown;
    try { payload = body(); } catch { setMessage('参数JSON无效或有重复字段，请修正后保存。'); return; }
    await run(async () => {
      const command = pending ?? { key: crypto.randomUUID(), path: configPath, body: payload };
      if (!selected) setPending(command);
      const result = await write<Config>(selected ? configPath + '/' + selected.id : command.path, selected ? payload : command.body, selected ? undefined : command.key, actor, selected ? 'PATCH' : 'POST');
      setSelected(result); setDraft(draftFor(result)); setDirty(false); setPending(null); setUncertain(false); setMessage('配置已保存；保存不会调用模型。'); setTask(null); setTestDetails(null); setConsent(false); await listing(); onChange(); if (next !== undefined) enter(next);
    }, true);
  }
  async function loadCurrent() {
    await run(async () => {
      if (pending && pending.path !== configPath) { const restored = await write<Task>(pending.path, pending.body, pending.key, actor); setTask(restored); setPending(null); setUncertain(false); }
      else if (pending) { const restored = await write<Config>(pending.path, pending.body, pending.key, actor); enter(restored); }
      else if (selected) { try { enter(await api<Config>(configPath + '/' + selected.id)); } catch (e) { if ((e as {status?: number}).status === 404) enter(null); else throw e; } }
      await listing(); onChange();
    });
  }
  async function start(kind: 'test' | 'refresh') {
    if (!selected) return;
    await run(async () => {
      const command = pending ?? { key: crypto.randomUUID(), path: configPath + '/' + selected.id + (kind === 'test' ? '/test' : '/models/refresh'), body: kind === 'test' ? { model_id: model.trim() } : {} };
      setTestDetails(null); setPending(command); const started = await write<Task>(command.path, command.body, command.key, actor); setTask(started); setPending(null); setUncertain(false);
    }, true);
  }
  async function poll() {
    if (!task) return;
    await run(async () => {
      const current = await api<Task>(task.status_url); setTask(current);
      if (['succeeded', 'failed'].includes(current.execution_status)) { if (current.result_refs.length) { const result = await api<{payload: {reason_code: string | null; tested_parameters: unknown; test_overrides: unknown}}>(current.result_refs[0].url); setTestDetails(result.payload); } setMessage(current.execution_status === 'succeeded' ? (['Config.RefreshModels', 'Admin.RefreshSystemModels'].includes(current.operation_id) ? '模型发现完成；候选模型仍须逐一测试。' : '模型测试成功，现在可选择。') : '操作失败：' + current.error?.code); if (selected) { const latest = await api<Config>(configPath + '/' + selected.id); setSelected(previous => previous ? { ...previous, models: latest.models } : previous); } await listing(); onChange(); }
    });
  }
  const extensionNames = draft.protocol === 'openai_chat' ? ['reasoning_effort', 'max_tokens', 'max_completion_tokens'] : draft.protocol === 'openai_responses' ? ['reasoning'] : draft.protocol === 'anthropic_messages' ? ['thinking'] : ['thinkingConfig'];
  function editExtension(remove = false) {
    try {
      if (!extensionNames.includes(customKey)) throw new Error('Unsupported field');
      const extra = parseParameterJson(draft.extra);
      const previous = extra.custom_params;
      if (previous !== undefined && (!previous || typeof previous !== 'object' || Array.isArray(previous))) throw new Error('Object required');
      const custom = { ...(previous as Record<string, unknown> | undefined) };
      if (remove) delete custom[customKey];
      else { const parsed: unknown = JSON.parse(customValue); custom[customKey] = parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parseParameterJson(customValue) : parsed; }
      change({ extra: JSON.stringify({ ...extra, custom_params: custom }, null, 2) });
      setMessage('扩展参数已加入草稿，保存时执行协议校验。');
    } catch { setMessage('扩展参数名称或JSON值无效；字符串需要双引号，数值和布尔值保留原类型。'); }
  }
  const protocols = draft.provider === 'anthropic' ? ['anthropic_messages'] : draft.provider === 'gemini' ? ['gemini_content'] : draft.provider === 'deepseek' ? ['openai_chat'] : ['openai_chat', 'openai_responses'];
  if (!active) return null;
  return <section className="form-card" aria-label="LLM设置" aria-busy={busy}><h2>{system ? "系统LLM配置" : "LLM配置"}</h2>
    <p>{system ? "系统模型可供用户显式选择，凭据不向用户公开。" : "配置只供本人使用。"}保存不调用外部服务；修改后需重新逐模型测试。</p>
    {message && <p role="alert">{message}</p>}
    <div className="list-pages"><button disabled={busy} onClick={() => switchConfig(null)}>新增LLM配置</button><button disabled={busy} onClick={() => void run(listing)}>刷新配置列表</button>{configs.map(c => <button key={c.id} disabled={busy} onClick={() => switchConfig(c)}>{c.name}</button>)}</div>
    {switchTo !== undefined && <div role="group" aria-label="未保存修改"><p>有未保存或未核实的修改。</p><button disabled={busy || uncertain || !!pending} onClick={() => void save(switchTo)}>保存并切换</button><button disabled={busy || uncertain || !!pending} onClick={() => enter(switchTo)}>放弃并切换</button><button disabled={busy} onClick={() => setSwitchTo(undefined)}>留在当前配置</button></div>}
    {uncertain && <button disabled={busy} onClick={() => void loadCurrent()}>核查当前配置（加载将放弃草稿）</button>}
    <form onSubmit={(e: FormEvent) => { e.preventDefault(); void save(); }}>
      <label>配置名称<input required maxLength={200} value={draft.name} disabled={busy || uncertain} onChange={e => change({ name: e.target.value })} /></label>
      <label>Provider<select aria-label="Provider" value={draft.provider} disabled={busy || uncertain} onChange={e => { const provider = e.target.value; change({ provider, protocol: provider === 'anthropic' ? 'anthropic_messages' : provider === 'gemini' ? 'gemini_content' : 'openai_chat', api_version: provider === 'anthropic' ? '2023-06-01' : '' }); }} >{['openai', 'anthropic', 'gemini', 'deepseek', 'custom'].map(v => <option key={v}>{v}</option>)}</select></label>
      <label>适配协议<select aria-label="适配协议" value={draft.protocol} disabled={busy || uncertain} onChange={e => change({ protocol: e.target.value })}>{protocols.map(v => <option key={v}>{v}</option>)}</select></label>
      <label>Base URL<input required type="url" value={draft.base_url} disabled={busy || uncertain} onChange={e => change({ base_url: e.target.value })} /></label>
      {draft.provider === 'anthropic' && <label>API版本<input value={draft.api_version} disabled={busy || uncertain} onChange={e => change({ api_version: e.target.value })} /></label>}
      <label>API密钥（留空保持已存值）<input type="password" autoComplete="new-password" value={draft.secret} disabled={busy || uncertain || draft.clearSecret} onChange={e => change({ secret: e.target.value })} /></label><p>{selected?.secret.configured ? '已保存凭据，无法读取明文。' : '尚无已保存凭据。'}</p>
      <label><input type="checkbox" checked={draft.clearSecret} disabled={busy || uncertain} onChange={e => change({ clearSecret: e.target.checked, secret: '' })} />清除已存凭据</label>
      <fieldset disabled={busy || uncertain}><legend>常用参数（留空使用Provider默认）</legend>{(['temperature', 'top_p', 'max_output_tokens'] as const).map(key => <label key={key}>{key}<input type="number" step={key === 'max_output_tokens' ? '1' : 'any'} value={draft[key]} onChange={e => change({ [key]: e.target.value })} /></label>)}</fieldset>
      <fieldset disabled={busy || uncertain}><legend>扩展参数键值编辑</legend><label>扩展参数名<select aria-label="扩展参数名" value={extensionNames.includes(customKey) ? customKey : ''} onChange={e => setCustomKey(e.target.value)}><option value="">请选择字段</option>{extensionNames.map(name => <option key={name}>{name}</option>)}</select></label><label>扩展参数值（JSON类型）<textarea aria-label="扩展参数值（JSON类型）" value={customValue} onChange={e => setCustomValue(e.target.value)} /></label><p>字符串如 "high"；数字如 1024；对象如 {"{\"effort\":\"high\"}"}。未登记字段不可透传。</p><button type="button" onClick={() => editExtension()}>添加或更新扩展参数</button><button type="button" onClick={() => editExtension(true)}>移除扩展参数</button></fieldset>
      <label>高级参数 JSON<textarea aria-label="高级参数 JSON" rows={5} spellCheck={false} value={draft.extra} disabled={busy || uncertain} onChange={e => change({ extra: e.target.value })} /></label><p>可填写stop、seed等适用字段；扩展项放在custom_params对象中。类型、范围及能力由后端校验，不支持的参数会明确拒绝。</p>
      <label>调用超时（秒，不发送给模型）<input type="number" min={1} max={120} value={draft.timeout} disabled={busy || uncertain} onChange={e => change({ timeout: e.target.value })} /></label>
      <button type="submit" disabled={busy || uncertain || !!pending}>保存LLM配置</button><button type="button" disabled={busy} onClick={() => { if (uncertain || pending) void loadCurrent(); else enter(selected); }}>取消配置编辑</button>
    </form>
    {selected && <div><h3>模型发现与测试</h3><button disabled={busy || dirty || uncertain || !!pending} onClick={() => void start('refresh')}>刷新可发现模型</button>
      <label>模型ID（可手工填写）<input value={model} disabled={busy || !!pending} onChange={e => { setModel(e.target.value); setConsent(false); }} /></label>
      {selected.models.map(o => <button key={o.model_id} disabled={busy || !!pending} onClick={() => { setModel(o.model_id); setConsent(false); }}>{o.model_id}：{o.available ? '测试通过' : '待测试或失败'}</button>)}
      <label><input type="checkbox" checked={consent} disabled={busy} onChange={e => setConsent(e.target.checked)} />我了解测试会调用已保存配置的模型，可能产生费用；仅发送固定测试文本。</label>
      <button disabled={busy || dirty || uncertain || !!pending || !consent || !model.trim()} onClick={() => void start('test')}>测试所选模型</button>
      {pending && <button disabled={busy} onClick={() => void start(pending.path.endsWith('/test') ? 'test' : 'refresh')}>核查同一测试请求</button>}
      {task && <div role="status">任务状态：{task.execution_status}<button disabled={busy} onClick={() => void poll()}>刷新测试状态</button></div>}
      {testDetails && <div aria-label="测试详情"><p>诊断：{testDetails.reason_code ?? '成功'}</p><p>实际生成参数</p><pre>{JSON.stringify(testDetails.tested_parameters, null, 2)}</pre><p>仅测试时覆盖</p><pre>{JSON.stringify(testDetails.test_overrides, null, 2)}</pre></div>}
      <button disabled={busy || dirty || uncertain || !!pending} onClick={() => { if (window.confirm('删除此LLM配置？已保存的模型选择将失效。')) void run(async () => { await write(configPath + '/' + selected.id + '?expected_revision=' + selected.revision, undefined, undefined, actor, 'DELETE'); enter(null); await listing(); onChange(); }, true); }}>删除LLM配置</button>
    </div>}
  </section>;
}
