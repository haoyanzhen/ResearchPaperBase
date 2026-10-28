import { useEffect, useRef, useState } from 'react';

type Term = { id: string; revision: string; confirmed_revision: string | null; query: string };
type Model = { source: string; config_id: string; model_id: string };
type SourceResult = { term_id: string; config_id: string; status: string; count: number; error: string | null; limited?: boolean };
type Run = { id: string; revision: string; status: string; created_at: string; input_snapshot: { selected_terms: { term_id: string; content: { query: string } }[]; retrieval_range: { published_from: string | null; published_until: string | null }; result_limit_per_source: number; frozen_at: string } | null; config_snapshot: { model_selection: Model; parameters: Record<string, unknown> } | null; task: { attempt_id: string }; steps: { result_summary: { candidate_count: number; sources: SourceResult[]; resolution: { executable: { term_id: string; rejected: { config_id?: string; reason_code: string }[] }[]; failed: { term_id: string; resolution: { rejected: { reason_code: string }[] } }[] } | null }; error: { code: string } | null }[] };
type Candidate = { id: string; metadata: { title: string; authors: string[]; year: number | null; abstract: string | null }; source: { search_term_id: string; provider_config_ref: { config_id: string } } };
type Props = {
  project: { id: string; status: string }; actor: string;
  envelope: <T>(path: string, init?: RequestInit) => Promise<{ data: T; meta: { next_cursor: string | null; has_more: boolean } }>;
  api: <T>(path: string, init?: RequestInit) => Promise<T>;
  write: <T>(path: string, body: unknown, key?: string, actor?: string, method?: string) => Promise<T>;
  onAuthFailure: (e: unknown) => void;
};
const labels: Record<string, string> = { queued: '排队中', running: '检索中', waiting_user: '检索结果待确认', failed: '失败', cancelled: '已取消' };
export function ConstructionRuns({ project, actor, api, envelope, write, onAuthFailure }: Props) {
  const base = `/api/v1/projects/${project.id}`;
  const [terms, setTerms] = useState<Term[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [model, setModel] = useState<Model | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [current, setCurrent] = useState<Run | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [from, setFrom] = useState(''); const [until, setUntil] = useState(''); const [limit, setLimit] = useState(100);
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<{ path: string; key: string; body: unknown } | null>(null);
  const epoch = useRef(0); const mounted = useRef(true);
  const headers = { 'X-Expected-Actor': actor };
  async function all<T>(path: string): Promise<{ items: T[] }> {
    let cursor: string | null = null; const items: T[] = [];
    do {
      const query: string = '?page_size=100' + (cursor ? '&cursor=' + encodeURIComponent(cursor) : '');
      const result: { data: { items: T[] }; meta: { next_cursor: string | null } } = await envelope<{ items: T[] }>(path + query, { headers });
      items.push(...result.data.items); cursor = result.meta.next_cursor;
    } while (cursor && mounted.current);
    return { items };
  }

  function failed(e: unknown) {
    const value = e as { status?: number; code?: string };
    if ([401, 403, 404].includes(value.status ?? 0)) { setTerms([]); setRuns([]); setCurrent(null); setCandidates([]); setPending(null); onAuthFailure(e); }
    else setError(value.code === 'LOCK_CONSTRUCTION_OCCUPIED' ? '当前构建占用项目，请查看或取消该运行。' : value.status === 412 ? '运行或检索词已变化，请刷新并核对后提交。' : '操作未完成，请检查输入、模型和数据源。若提交结果未知，可用原请求核查重试。');
  }
  async function refresh() {
    const version = ++epoch.current;
    try {
      const [list, ts, choice] = await Promise.all([
        all<Run>(base + '/construction-runs'),
        all<Term>(base + '/construction-workspace/search-terms'),
        api<{ selection: Model | null; valid: boolean }>('/api/v1/me/model-selection', { headers }),
      ]);
      if (!mounted.current || epoch.current !== version) return;
      setRuns(list.items); setCandidates([]); setTerms(ts.items); setModel(choice.valid ? choice.selection : null);
      setCurrent(old => list.items.find(r => r.id === old?.id) ?? null);
    } catch (e) { if (mounted.current && epoch.current === version) failed(e); }
  }
  useEffect(() => { mounted.current = true; void refresh(); return () => { mounted.current = false; epoch.current++; }; }, [project.id, actor]); // eslint-disable-line react-hooks/exhaustive-deps
  async function inspect(run: Run) {
    const version = ++epoch.current; setError(''); setCandidates([]); setCurrent(run);
    try {
      const [detail, list] = await Promise.all([api<Run>(base + '/construction-runs/' + run.id, { headers }), all<Candidate>(base + '/construction-runs/' + run.id + '/candidates')]);
      if (mounted.current && epoch.current === version) { setCurrent(detail); setCandidates(list.items); }
    } catch (e) { if (mounted.current && epoch.current === version) failed(e); }
  }
  async function submit(command: { path: string; key: string; body: unknown }) {
    setBusy(true); setError(''); setPending(command);
    try {
      const result = await write<{ run: Run }>(command.path, command.body, command.key, actor);
      if (!mounted.current) return;
      setPending(null); setCurrent(result.run); setCandidates([]); await refresh();
    } catch (e) {
      if (mounted.current) { const status = (e as { status?: number }).status; if (status && status >= 400 && status < 500 && status !== 408) setPending(null); failed(e); }
    } finally { if (mounted.current) setBusy(false); }
  }
  const active = project.status === 'active';
  return <section aria-label="构建运行" className="maintenance" aria-busy={busy}>
    <h2>构建运行</h2>
    <p>选择已确认检索词和模型，检索论文并查看来源结果。检索完成后保持待确认；去重评分和入库将在后续阶段开放。</p>
    {error && <p role="alert" className="error">{error}</p>}
    <button disabled={busy} onClick={() => { void refresh(); }}>刷新运行与配置</button>
    {pending && <button disabled={busy || !active} onClick={() => { void submit(pending); }}>用原请求核查重试</button>}
    <form onSubmit={event => { event.preventDefault(); if (!model) return; const body = { selected_terms: terms.filter(t => selected.includes(t.id)).map(t => ({ term_id: t.id, confirmed_revision: t.confirmed_revision })), model_selection: model, retrieval_range: { published_from: from ? from + 'T00:00:00Z' : null, published_until: until ? until + 'T00:00:00Z' : null }, result_limit_per_source: limit }; void submit({ path: base + '/construction-runs', key: crypto.randomUUID(), body }); }}>
      <fieldset disabled={busy || !active || !!pending}>
        <legend>启动论文检索</legend>
        <p>{model ? `模型：${model.source} / ${model.model_id}` : '请先在模型设置中显式选择已验证模型，然后刷新。'}</p>
        <p>未确认的词不能用于启动；每次最多选择100条。</p>
        {terms.map(term => <label key={term.id}><input type="checkbox" checked={selected.includes(term.id)} disabled={!term.confirmed_revision} onChange={e => setSelected(ids => e.target.checked ? [...ids, term.id] : ids.filter(id => id !== term.id))} />{term.query}{!term.confirmed_revision && '（未确认）'}</label>)}
        <label>开始日期（UTC，含当日）<input type="date" value={from} onChange={e => setFrom(e.target.value)} /></label>
        <label>结束日期（UTC，不含当日）<input type="date" value={until} onChange={e => setUntil(e.target.value)} /></label>
        <label>每个来源返回上限<input type="number" min={1} max={1000} required value={limit} onChange={e => setLimit(Number(e.target.value))} /></label>
        <button disabled={!model || !selected.length || selected.length > 100 || selected.some(id => !terms.some(t => t.id === id && t.confirmed_revision))}>启动检索</button>
      </fieldset>
    </form>
    <h3>历史运行</h3>
    <ul>{runs.map(run => <li key={run.id}><button disabled={busy} onClick={() => { void inspect(run); }}>{run.created_at} · {labels[run.status] ?? run.status}</button></li>)}</ul>
    {current && <div aria-label="运行详情">
      <h3>{labels[current.status] ?? current.status}</h3>
      {current.status === 'waiting_user' && <p>检索已完成；去重评分尚未交付。该运行仍占用构建槽，可查看结果或取消。</p>}
      <button disabled={busy} onClick={() => { void inspect(current); }}>刷新本次结果</button>
      {['queued', 'running', 'waiting_user'].includes(current.status) && <button disabled={busy || !active || !!pending} onClick={() => { void submit({ path: base + '/construction-runs/' + current.id + '/cancel', key: crypto.randomUUID(), body: { expected_revision: current.revision, attempt_id: current.task.attempt_id } }); }}>取消本次构建</button>}
      {current.steps.map(step => <div key="retrieval"><p>候选论文：{step.result_summary.candidate_count}</p>{step.error && <p role="alert">{step.error.code}</p>}<ul>{step.result_summary.resolution?.executable.flatMap(term => term.rejected.map((reason, i) => <li key={term.term_id + i}>检索词 {term.term_id} 的部分来源不可用：{reason.config_id} · {reason.reason_code}</li>))}</ul><ul>{step.result_summary.resolution?.failed.map(term => <li key={term.term_id}>检索词 {term.term_id} 未执行：{term.resolution.rejected.map(reason => reason.reason_code).join("、")}</li>)}</ul><ul>{step.result_summary.sources.map((source, i) => <li key={i}>来源 {source.config_id} · 检索词 {source.term_id}：{source.count} 条 · {source.status}{source.error && ` · ${source.error}`}{source.limited && ' · 已达到返回范围限制'}</li>)}</ul></div>)}
      <details><summary>本轮输入与模型</summary>
        {current.input_snapshot ? <><p>冻结于 {current.input_snapshot.frozen_at}；每源上限 {current.input_snapshot.result_limit_per_source}</p><p>时间范围：{current.input_snapshot.retrieval_range.published_from ?? '不限'} 至 {current.input_snapshot.retrieval_range.published_until ?? '不限'}（不含结束时刻）</p><ul>{current.input_snapshot.selected_terms.map(t => <li key={t.term_id}>{t.content.query}</li>)}</ul></> : <p>尚未取得构建资格，输入未冻结。</p>}
        {current.config_snapshot && <><p>本轮模型：{current.config_snapshot.model_selection.source} / {current.config_snapshot.model_selection.model_id}</p><dl>{Object.entries(current.config_snapshot.parameters).map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{JSON.stringify(value)}</dd></div>)}</dl></>}
      </details>
      <ul>{candidates.map(candidate => <li key={candidate.id}><strong>{candidate.metadata.title}</strong><p>{candidate.metadata.authors.join('、')} · {candidate.metadata.year ?? '年份未知'}</p><p>{candidate.metadata.abstract}</p></li>)}</ul>
    </div>}
  </section>;
}
