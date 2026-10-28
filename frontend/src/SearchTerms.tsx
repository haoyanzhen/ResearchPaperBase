import { useEffect, useRef, useState } from 'react';

type API = <T>(url: string, init?: RequestInit) => Promise<T>;
type Envelope = <T>(url: string, init?: RequestInit) => Promise<{ data: T; meta: { next_cursor: string | null; has_more: boolean } }>;
type Write = <T>(url: string, body: unknown, key?: string, actor?: string, method?: string) => Promise<T>;
type Ref = { source: 'user' | 'system'; config_id: string };
type Content = { query: string; keywords: string[]; synonyms: string[]; exclusions: string[]; rationale: string; coverage: string; auto_update_enabled: boolean; source_policy: { mode: 'all_resolvable' | 'selected'; source_refs?: Ref[] } };
type Term = Content & { id: string; revision: string; status: string; content_state: string; confirmed_revision: string | null; confirmations: { confirmation_token: string }[] };
type Task = { task_id: string; execution_status: string; error: { message: string } | null };
type Workspace = { revision: string; auto_update_enabled: boolean; topic_source: { source_id: string }; generation_tasks: Task[] };
type Policy = { revision: string; mode: 'public_only' | 'allow_private' };
type Classification = { revision: string; source: { content_revision: string }; classification: 'public' | 'private'; confirmation_status: string };
type Source = Ref & { provider: string; reason_code?: string };
const blank: Content = { query: '', keywords: [], synonyms: [], exclusions: [], rationale: '', coverage: '', auto_update_enabled: true, source_policy: { mode: 'all_resolvable' } };
const sourceKey = (v: Ref) => v.source + ':' + v.config_id;

export function SearchTerms({ project, actor, api: baseApi, envelope, write, onAuthFailure }: { project: { id: string; status: string; revision: string }; actor: string; api: API; envelope: Envelope; write: Write; onAuthFailure: (e: unknown) => void }) {
  const root = `/api/v1/projects/${project.id}`;
  const path = root + '/construction-workspace';
  const api: API = (url, init) => baseApi(url, { ...init, headers: { ...init?.headers, 'X-Expected-Actor': actor } });
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [terms, setTerms] = useState<Term[]>([]);
  const loadedCount = useRef(20);
  const [conflict, setConflict] = useState(false);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [classification, setClassification] = useState<Classification | null>(null);
  const [draft, setDraft] = useState<Content>(blank);
  const [editing, setEditing] = useState<Term | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [requirements, setRequirements] = useState('');
  const [basis, setBasis] = useState('');
  const [kind, setKind] = useState<'private' | 'public'>('private');
  const [risk, setRisk] = useState(false);
  const [pending, setPending] = useState<{ url: string; body: unknown; key: string; method?: string } | null>(null);
  const [uncertain, setUncertain] = useState(false);
  const readonly = project.status !== 'active';
  async function load() {
    const [w, t, p, s] = await Promise.all([api<Workspace>(path), envelope<{ items: Term[] }>(path + '/search-terms', { headers: { 'X-Expected-Actor': actor } }), api<Policy>(root + '/material-policy'), api<{ sources: Source[]; rejected: Source[] }>(path + '/source-options')]);
    const loaded = [...t.data.items];
    let cursor = t.meta.next_cursor;
    while (cursor && loaded.length < loadedCount.current) {
      const page = await envelope<{ items: Term[] }>(path + '/search-terms?cursor=' + encodeURIComponent(cursor), { headers: { 'X-Expected-Actor': actor } });
      loaded.push(...page.data.items); cursor = page.meta.next_cursor;
    }
    const c = await api<Classification>(root + `/material-sources/${w.topic_source.source_id}/classification`);
    setWorkspace(w); setTerms(loaded); setNextCursor(cursor); setSelected(ids => ids.filter(id => loaded.some(t => t.id === id && t.status === 'candidate'))); setPolicy(p); setClassification(c); setSources([...s.sources, ...s.rejected]);
  }
  async function run(action: () => Promise<void>, writing = false) {
    setBusy(true); setMessage('');
    try { await action(); }
    catch (e) {
      const err = e as { status?: number; code?: string };
      if (err.status === 401 || err.code === 'PERMISSION_CSRF_REJECTED') { onAuthFailure(e); setTerms([]); setDraft(blank); setEditing(null); }
      else {
        if (err.status === 404) {
          try {
            await api(root);
            await load(); setEditing(null); setPending(null); setUncertain(false); setConflict(false);
            setMessage('此检索词已被移除，草稿保留；核对后可另存为新词。');
            return;
          } catch (lookup) {
            const status = (lookup as { status?: number }).status;
            if (status !== 401 && status !== 404) { setUncertain(true); setMessage('尚不能核实Project访问资格，草稿保留，请重试核查。'); return; }
            setTerms([]); setWorkspace(null); setClassification(null); setPolicy(null); setDraft(blank); setEditing(null); setSelected([]);
            if ((lookup as { status?: number }).status === 401) onAuthFailure(lookup);
          }
        }
        setMessage(err.status === 412 ? '内容已变化，草稿保留。请核查最新内容后重新编辑。' : err.status === 404 ? '资源不可用。' : err.status === 409 ? '操作未完成，请检查确认、资料分类、模型及当前任务状态。' : err.status === 422 ? '输入未通过校验，请检查字段。' : '结果尚未确认，请核查当前内容。');
        if (writing && err.status === 412) { setConflict(true); setPending(null); }
        else if (writing && (!err.status || err.status >= 500)) setUncertain(true);
        else if (writing) setPending(null);
      }
    } finally { setBusy(false); }
  }
  async function submit(url: string, body: unknown, method = 'POST') {
    const command = { url, body, key: crypto.randomUUID(), method };
    setPending(command);
    await write(url, body, command.key, actor, method);
    setPending(null); setUncertain(false); await load();
  }
  useEffect(() => { void run(load); }, [project.id, project.revision, actor]);
  useEffect(() => {
    if (!workspace?.generation_tasks.some(t => ['queued', 'running'].includes(t.execution_status))) return;
    const timer = setInterval(() => { if (!busy) void run(load); }, 1500);
    return () => clearInterval(timer);
  }, [workspace, busy]);
  function edit(term: Term) { setEditing(term); setDraft({ query: term.query, keywords: term.keywords, synonyms: term.synonyms, exclusions: term.exclusions, rationale: term.rationale, coverage: term.coverage, auto_update_enabled: term.auto_update_enabled, source_policy: term.source_policy }); }
  async function confirm(term: Term) {
    const current = await api<Term>(path + '/search-terms/' + term.id);
    if (!current.confirmations.length) return;
    await submit(path + `/search-terms/${term.id}/confirm`, { expected_revision: term.revision, confirmation_token: current.confirmations[0].confirmation_token, acknowledged_risk_ids: [] });
  }
  async function batch(action: 'confirm' | 'discard') {
    const chosen = terms.filter(t => selected.includes(t.id) && t.status === 'candidate');
    for (const term of chosen) {
      if (action === 'confirm') await confirm(term);
      else await submit(path + `/search-terms/${term.id}/discard`, { expected_revision: term.revision });
      setSelected(ids => ids.filter(id => id !== term.id));
    }
    setMessage('所选候选已处理。');
  }
  const disabled = busy || readonly || uncertain || conflict;
  return <section className="term-workspace" aria-label="构建检索词" aria-busy={busy}>
    <h2>构建检索词</h2><p>调度未启用 · 配置修改用于下一轮。生成建议不会覆盖已有检索词。</p>
    {message && <p role="alert">{message}</p>}
    <button disabled={busy} onClick={() => void run(load)}>刷新检索词</button>
    {conflict && <button disabled={busy} onClick={() => void run(async () => { await load(); if (editing) { const latest = await api<Term>(path + '/search-terms/' + editing.id); setEditing(latest); } setConflict(false); setMessage('已加载最新确认依据，原草稿保留；请对照下方最新内容后再保存。'); })}>加载最新内容并保留草稿</button>}
    {uncertain && <div><button disabled={busy} onClick={() => void run(async () => { await load(); setUncertain(false); setPending(null); setEditing(null); setDraft(blank); })}>核查当前内容并放弃草稿</button>{pending?.method === 'POST' && <button disabled={busy} onClick={() => void run(async () => { await write(pending.url, pending.body, pending.key, actor, pending.method); setPending(null); setUncertain(false); await load(); }, true)}>用原请求核查结果</button>}</div>}
    {workspace && <aside className="term-summary" aria-label="检索词配置摘要"><h3>当前检索词配置</h3><p>版本：{workspace.revision}</p><p>已加载 {terms.length} 词，待确认 {terms.filter(t => t.confirmed_revision !== t.revision).length} 词；{nextCursor ? '还有更多检索词可加载' : '已加载全部检索词'}。</p><p>Project自动更新：{workspace.auto_update_enabled ? '开启' : '关闭'}；调度未启用，无自动运行记录。逐词来源和更新策略见审核列表。</p></aside>}
    {workspace && <label className="checkbox"><input type="checkbox" disabled={disabled} checked={workspace.auto_update_enabled} onChange={e => void run(() => submit(path, { expected_revision: workspace.revision, auto_update_enabled: e.target.checked }, 'PATCH'), true)} />保存Project自动更新策略（调度未启用）</label>}
    <form onSubmit={e => { e.preventDefault(); void run(async () => { await submit(path + '/search-terms' + (editing ? '/' + editing.id : ''), editing ? { ...draft, expected_revision: editing.revision } : draft, editing ? 'PATCH' : 'POST'); setEditing(null); setDraft(blank); setMessage('检索词已保存，需确认当前版本。'); }, true); }}>
      <h3>{editing ? '编辑检索词' : '手动添加检索词'}</h3>
      <label>查询表达式<textarea aria-label="查询表达式" required maxLength={10000} disabled={disabled} value={draft.query} onChange={e => setDraft({ ...draft, query: e.target.value })} /></label>
      {(['keywords', 'synonyms', 'exclusions'] as const).map((field, i) => <label key={field}>{['自然语言关键词', '同义词与缩写', '排除词'][i]}（每行一项）<textarea aria-label={['自然语言关键词', '同义词与缩写', '排除词'][i] + '（每行一项）'} disabled={disabled} value={draft[field].join('\n')} onChange={e => setDraft({ ...draft, [field]: e.target.value ? e.target.value.split('\n') : [] })} /></label>)}
      <label>生成或修改理由<textarea aria-label="生成或修改理由" disabled={disabled} value={draft.rationale} onChange={e => setDraft({ ...draft, rationale: e.target.value })} /></label>
      <label>预期覆盖方向<textarea aria-label="预期覆盖方向" disabled={disabled} value={draft.coverage} onChange={e => setDraft({ ...draft, coverage: e.target.value })} /></label>
      <label className="checkbox"><input type="checkbox" disabled={disabled} checked={draft.auto_update_enabled} onChange={e => setDraft({ ...draft, auto_update_enabled: e.target.checked })} />参与自动更新（不影响手动选择）</label>
      <label>适用数据源<select aria-label="适用数据源" disabled={disabled} value={draft.source_policy.mode} onChange={e => setDraft({ ...draft, source_policy: e.target.value === 'selected' ? { mode: 'selected', source_refs: [] } : { mode: 'all_resolvable' } })}><option value="all_resolvable">全部可解析数据源</option><option value="selected">显式选择数据源</option></select></label>
      {draft.source_policy.mode === 'selected' && <div>{sources.map(s => <label className="checkbox" key={sourceKey(s)}><input type="checkbox" disabled={disabled} checked={draft.source_policy.source_refs?.some(v => sourceKey(v) === sourceKey(s)) ?? false} onChange={e => setDraft({ ...draft, source_policy: { mode: 'selected', source_refs: e.target.checked ? [...(draft.source_policy.source_refs ?? []), { source: s.source, config_id: s.config_id }] : draft.source_policy.source_refs?.filter(v => sourceKey(v) !== sourceKey(s)) } })} />{s.provider} · {s.source === 'user' ? '个人' : '系统'} · {s.config_id.slice(0, 8)} {s.reason_code ? '（当前不可用）' : ''}</label>)}{draft.source_policy.source_refs?.filter(r => !sources.some(s => sourceKey(s) === sourceKey(r))).map(r => <p key={sourceKey(r)}>已保存来源当前不可用：{r.config_id} <button type="button" disabled={disabled} onClick={() => setDraft({ ...draft, source_policy: { mode: 'selected', source_refs: draft.source_policy.source_refs?.filter(x => sourceKey(x) !== sourceKey(r)) } })}>移除此选择</button></p>)}</div>}
      <button disabled={disabled || (draft.source_policy.mode === 'selected' && !draft.source_policy.source_refs?.length)} type="submit">{editing ? '保存词修改' : '添加检索词'}</button>{editing && <button type="button" disabled={busy} onClick={() => { setEditing(null); setDraft(blank); }}>取消词编辑</button>}
    </form>
    <h3>长期检索词与待审核候选</h3>
    <p>批量操作逐词校验；发生冲突时保留已完成项，剩余项可重新核查。</p>
    <button disabled={disabled || !selected.length} onClick={() => void run(() => batch('confirm'), true)}>接受并确认所选候选</button>
    <button disabled={disabled || !selected.length} onClick={() => void run(() => batch('discard'), true)}>弃用所选候选</button>
    {!terms.length && <p>还没有检索词，可以手动添加或生成建议。</p>}
    {terms.map(term => <article className="term-card" key={term.id} aria-label={'检索词 ' + term.query}>
      {term.status === 'candidate' && <label className="checkbox"><input type="checkbox" disabled={disabled} checked={selected.includes(term.id)} onChange={e => setSelected(ids => e.target.checked ? [...ids, term.id] : ids.filter(id => id !== term.id))} />选择候选 {term.query}</label>}
      <h4>{term.query}</h4><p>{term.status === 'candidate' ? '待审核候选' : '长期检索词'} · {term.confirmed_revision === term.revision ? '已确认' : '待确认'} · {term.content_state === 'agent_draft' ? 'Agent草稿' : term.content_state === 'manual_edit' ? '人工修改' : '人工确认'}</p>
      <p>关键词：{term.keywords.join('、')}；同义词：{term.synonyms.join('、')}；排除词：{term.exclusions.join('、')}</p><p>理由：{term.rationale || '未填写'}；覆盖：{term.coverage || '未填写'}</p>
      <p>{term.auto_update_enabled ? '参与自动更新' : '不参与自动更新'} · {term.source_policy.mode === 'all_resolvable' ? '全部可解析数据源' : `显式来源 ${term.source_policy.source_refs?.length} 项`}</p>
      {term.source_policy.mode === 'selected' && <ul>{term.source_policy.source_refs?.map(ref => { const source = sources.find(s => sourceKey(s) === sourceKey(ref)); return <li key={sourceKey(ref)}>{source?.provider ?? '未知来源'} · {ref.source === 'user' ? '个人' : '系统'} · {ref.config_id} {(!source || source.reason_code) ? '（当前不可用）' : ''}</li>; })}</ul>}
      <div className="list-pages"><button disabled={disabled} onClick={() => edit(term)}>编辑此词</button>{term.confirmed_revision !== term.revision && <button disabled={disabled} onClick={() => void run(() => confirm(term), true)}>{term.status === 'candidate' ? '接受并确认此词' : '确认此词'}</button>}
      {term.status === 'candidate' ? <button disabled={disabled} onClick={() => void run(() => submit(path + `/search-terms/${term.id}/discard`, { expected_revision: term.revision }), true)}>弃用此候选</button> : <button disabled={disabled} onClick={() => void run(() => submit(path + `/search-terms/${term.id}?expected_revision=${encodeURIComponent(term.revision)}`, undefined, 'DELETE'), true)}>删除此词</button>}</div>
    </article>)}
    {nextCursor && <button disabled={busy} onClick={() => void run(async () => { const page = await envelope<{ items: Term[] }>(path + '/search-terms?cursor=' + encodeURIComponent(nextCursor), { headers: { 'X-Expected-Actor': actor } }); loadedCount.current += page.data.items.length; setTerms(items => [...items, ...page.data.items.filter(t => !items.some(v => v.id === t.id))]); setNextCursor(page.meta.next_cursor); })}>加载更多检索词</button>}
    <details><summary>主题资料分类与Agent使用范围</summary><p>已保存的项目名称、描述和研究范围需要明确分类。允许私人资料后，所选模型服务可能收到本Project私人内容；可随时关闭，已发送内容不能撤回。</p>
      <p>主题分类：{classification?.confirmation_status === 'confirmed' ? classification.classification === 'private' ? '已确认私人' : '已确认公开' : '未确认'}；Agent范围：{policy?.mode === 'allow_private' ? '允许私人资料' : '仅公开资料'}</p>
      <label>主题分类<select aria-label="主题分类" disabled={disabled} value={kind} onChange={e => setKind(e.target.value as 'private' | 'public')}><option value="private">私人</option><option value="public">公开</option></select></label>
      <label>分类依据<input maxLength={2000} disabled={disabled} value={basis} onChange={e => setBasis(e.target.value)} /></label>
      <button disabled={disabled || !basis.trim() || !classification || !workspace} onClick={() => void run(() => submit(root + `/material-sources/${workspace!.topic_source.source_id}/classification/${classification!.confirmation_status === 'confirmed' ? 'correct' : 'confirm'}`, { expected_revision: classification!.revision, content_revision: classification!.source.content_revision, classification: kind, basis, explicit_confirmation: true }), true)}>确认主题资料分类</button>
      <label className="checkbox"><input type="checkbox" disabled={disabled} checked={risk} onChange={e => setRisk(e.target.checked)} />我理解所选模型服务可能收到本Project私人内容</label>
      <button disabled={disabled || !policy || (!risk && policy.mode !== 'allow_private')} onClick={() => void run(async () => { const mode = policy!.mode === 'allow_private' ? 'public_only' : 'allow_private'; await submit(root + '/material-policy', { expected_revision: policy!.revision, mode, risk_acknowledged: mode === 'allow_private' }, 'PUT'); setRisk(false); }, true)}>{policy?.mode === 'allow_private' ? '关闭私人资料使用' : '允许本Project私人资料'}</button>
    </details>
    <h3>生成检索词建议</h3><label>本次补充要求<textarea aria-label="本次补充要求" disabled={disabled} maxLength={10000} value={requirements} onChange={e => setRequirements(e.target.value)} /></label>
    <button disabled={disabled || !workspace || workspace.generation_tasks.some(t => ['queued', 'running'].includes(t.execution_status))} onClick={() => void run(async () => { const model = await api<{ selection: unknown; valid: boolean }>('/api/v1/me/model-selection'); if (!model.valid) { setMessage('请先显式选择已测试可用的模型。'); return; } await submit(path + '/search-terms/generate', { expected_revision: workspace!.revision, model_selection: model.selection, additional_requirements: requirements, acknowledged_risk_ids: [] }); }, true)}>生成检索词建议</button>
    {workspace?.generation_tasks.map(t => <p key={t.task_id} role="status">生成任务：{({ queued: '排队中', running: '生成中', succeeded: '已完成，请审核候选', failed: '失败，原词保留', cancelled: '已安全终止' } as Record<string, string>)[t.execution_status]} {t.error?.message}</p>)}
  </section>;
}
