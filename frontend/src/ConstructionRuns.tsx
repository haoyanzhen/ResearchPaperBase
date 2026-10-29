import { useEffect, useRef, useState } from 'react';

type Term = { id: string; revision: string; confirmed_revision: string | null; query: string };
type Model = { source: string; config_id: string; model_id: string };
type SourceResult = { term_id: string; config_id: string; status: string; count: number; error: string | null; limited?: boolean };
type Run = { candidate_revision: string; scoring_tasks: { task_id: string; execution_status: string; error: { code: string } | null }[]; phase: string; waiting_items: { id: string; revision: string; confirmation: { subject_revision: string; candidate_revision: string; confirmation_token: string } | null }[]; id: string; revision: string; status: string; created_at: string; input_snapshot: { selected_terms: { term_id: string; content: { query: string } }[]; retrieval_range: { published_from: string | null; published_until: string | null }; result_limit_per_source: number; frozen_at: string } | null; config_snapshot: { model_selection: Model; parameters: Record<string, unknown> } | null; task: { attempt_id: string }; steps: { result_summary: { candidate_count: number; screening: { valid_count: number; invalid_count: number; pending_count: number; failed_count: number } | null; deduplication: { unique_count: number; duplicate_count: number; unresolved_count: number } | null; sources: SourceResult[]; resolution: { executable: { term_id: string; rejected: { config_id?: string; reason_code: string }[] }[]; failed: { term_id: string; resolution: { rejected: { reason_code: string }[] } }[] } | null }; error: { code: string } | null }[] };
type Classification = { revision: string; source: { source_id: string; content_revision: string }; confirmation_status: string; classification: string };
type ScorePreview = { confirmation_token: string; risks: { id: string; message: string }[]; affected_items: { object: { id: string }; reason: string }[] };
type Candidate = { material_classification?: Classification; screening: { score: number | null; valid: boolean | null; reason: string | null; threshold_source: string | null }; screening_modified_by?: string; screening_modified_at?: string; screening_history?: { screening: { score: number | null; valid: boolean | null; reason: string | null }; state: string; actor_id: string; at: string }[]; screening_state?: string; screening_stale?: boolean; screening_error?: string | null; screening_basis?: { threshold: number; reasons: { theoretical: string; technical: string; relevance: string }; model_selection: Model }; revision: string; deduplication?: { state: string; group_id: string | null; origin: string; matched_candidate_id: string | null; history: { decision: string; reason: string; at: string }[] }; id: string; metadata: { title: string; authors: string[]; year: number | null; abstract: string | null }; source: { search_term_id: string; provider_config_ref: { config_id: string } } };
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
  const [scorePreview, setScorePreview] = useState<{ proof: ScorePreview; path: string; body: Record<string, unknown> } | null>(null);
  const [pending, setPending] = useState<{ path: string; key: string; body: unknown; method?: string } | null>(null);
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
    const version = ++epoch.current; setError(''); setScorePreview(null); setCandidates([]); setCurrent(run);
    try {
      const [detail, list] = await Promise.all([api<Run>(base + '/construction-runs/' + run.id, { headers }), all<Candidate>(base + '/construction-runs/' + run.id + '/candidates')]);
      if (mounted.current && epoch.current === version) { setCurrent(detail); setCandidates(list.items); }
    } catch (e) { if (mounted.current && epoch.current === version) failed(e); }
  }
  async function submit(command: { path: string; key: string; body: unknown; method?: string }) {
    setBusy(true); setError(''); setPending(command);
    try {
      const result = await write<{ run?: Run }>(command.path, command.body, command.key, actor, command.method);
      if (!mounted.current) return;
      setPending(null); setScorePreview(null); setCandidates([]); await refresh(); if (result.run ?? current) await inspect((result.run ?? current)!);
    } catch (e) {
      if (mounted.current) { const status = (e as { status?: number }).status; if (status && status >= 400 && status < 500 && status !== 408) setPending(null); failed(e); }
    } finally { if (mounted.current) setBusy(false); }
  }
  async function prepareScore(candidate: Candidate) {
    if (!current) return;
    const path = base + '/construction-runs/' + current.id + '/screening';
    const body = { expected_revision: current.candidate_revision, candidate_ids: [candidate.id] };
    setBusy(true); setError('');
    try {
      const proof = await write<ScorePreview>(path + '/action-preview', { ...body, action: 'score' }, crypto.randomUUID(), actor);
      if (mounted.current) setScorePreview({ proof, path: path + '/score', body });
    } catch (e) { if (mounted.current) failed(e); }
    finally { if (mounted.current) setBusy(false); }
  }
  const active = project.status === 'active';
  const scoring = current?.scoring_tasks.some(t => ['queued', 'running'].includes(t.execution_status)) ?? false;
  return <section aria-label="构建运行" className="maintenance" aria-busy={busy}>
    <h2>构建运行</h2>
    <p>选择已确认检索词和模型，检索论文并查看来源结果。确认检索后按标题去标点、转小写去重，可人工拆分或合并。可评分、查看理由并人工调整；下载解析和入库尚未开放。</p>
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
      <h3>{current.status === 'waiting_user' && current.phase === 'screening' ? '去重结果待核对' : labels[current.status] ?? current.status}</h3>
      {current.status === 'waiting_user' && <p>{current.phase === 'screening' ? '可检查来源、评分并调整有效性。评分使用本轮冻结模型；先在检索词面板确认主题资料分类，再确认本页各来源分类。' : '检索已完成，确认后进行标题去重。'}该运行仍占用构建槽，可查看结果或取消。</p>}
      {current.status === 'waiting_user' && current.phase === 'retrieval' && current.waiting_items.map(wait => wait.confirmation && <button key={wait.id} disabled={busy || !active || !!pending} onClick={() => { void submit({ path: base + '/construction-runs/' + current.id + '/waiting-items/' + wait.id + '/confirm', key: crypto.randomUUID(), body: { expected_revision: wait.revision, subject_revision: wait.confirmation!.subject_revision, candidate_revision: wait.confirmation!.candidate_revision, confirmation_token: wait.confirmation!.confirmation_token, acknowledged_risk_ids: [] } }); }}>确认检索并去重</button>)}
      <button disabled={busy} onClick={() => { void inspect(current); }}>刷新本次结果</button>
      {['queued', 'running', 'waiting_user'].includes(current.status) && <button disabled={busy || !active || !!pending} onClick={() => { void submit({ path: base + '/construction-runs/' + current.id + '/cancel', key: crypto.randomUUID(), body: { expected_revision: current.revision, attempt_id: current.task.attempt_id } }); }}>取消本次构建</button>}
      {current.steps.map(step => <div key="retrieval"><p>候选论文：{step.result_summary.candidate_count}</p>{step.result_summary.deduplication && <p>不同论文：{step.result_summary.deduplication.unique_count} · 重复来源：{step.result_summary.deduplication.duplicate_count} · 身份待补充：{step.result_summary.deduplication.unresolved_count}</p>}{step.error && <p role="alert">{step.error.code}</p>}<ul>{step.result_summary.resolution?.executable.flatMap(term => term.rejected.map((reason, i) => <li key={term.term_id + i}>检索词 {term.term_id} 的部分来源不可用：{reason.config_id} · {reason.reason_code}</li>))}</ul><ul>{step.result_summary.resolution?.failed.map(term => <li key={term.term_id}>检索词 {term.term_id} 未执行：{term.resolution.rejected.map(reason => reason.reason_code).join("、")}</li>)}</ul><ul>{step.result_summary.sources.map((source, i) => <li key={i}>来源 {source.config_id} · 检索词 {source.term_id}：{source.count} 条 · {source.status}{source.error && ` · ${source.error}`}{source.limited && ' · 已达到返回范围限制'}</li>)}</ul></div>)}
      {current.steps[0]?.result_summary.screening && <p aria-label="筛选统计">有效 {current.steps[0].result_summary.screening.valid_count} · 无效 {current.steps[0].result_summary.screening.invalid_count} · 待判定 {current.steps[0].result_summary.screening.pending_count} · 评分失败 {current.steps[0].result_summary.screening.failed_count}</p>}
      {scoring && <p role="status">评分任务处理中，可刷新查看进度；此时不能修改候选。</p>}
      {current.scoring_tasks.map(t => <p key={t.task_id}>评分任务：{t.execution_status}{t.error && ` · ${t.error.code}`}</p>)}
      {scorePreview && <section aria-label="评分确认"><h4>评分范围确认</h4><p>使用本轮模型和各来源原始内容评分，默认有效阈值为7/10。失败保留原判断。</p>{scorePreview.proof.risks.map(r => <p key={r.id}>{r.message}</p>)}<ul>{scorePreview.proof.affected_items.map(i => <li key={i.object.id}>{i.object.id}：{i.reason}</li>)}</ul><button disabled={busy || !active || scoring} onClick={() => void submit({ path: scorePreview.path, key: crypto.randomUUID(), body: { ...scorePreview.body, confirmation_token: scorePreview.proof.confirmation_token, acknowledged_risk_ids: scorePreview.proof.risks.map(r => r.id) } })}>确认评分</button><button disabled={busy} onClick={() => setScorePreview(null)}>取消评分确认</button></section>}
      <details><summary>本轮输入与模型</summary>
        {current.input_snapshot ? <><p>冻结于 {current.input_snapshot.frozen_at}；每源上限 {current.input_snapshot.result_limit_per_source}</p><p>时间范围：{current.input_snapshot.retrieval_range.published_from ?? '不限'} 至 {current.input_snapshot.retrieval_range.published_until ?? '不限'}（不含结束时刻）</p><ul>{current.input_snapshot.selected_terms.map(t => <li key={t.term_id}>{t.content.query}</li>)}</ul></> : <p>尚未取得构建资格，输入未冻结。</p>}
        {current.config_snapshot && <><p>本轮模型：{current.config_snapshot.model_selection.source} / {current.config_snapshot.model_selection.model_id}</p><dl>{Object.entries(current.config_snapshot.parameters).map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{JSON.stringify(value)}</dd></div>)}</dl></>}
      </details>
      <ul>{candidates.map(candidate => <li key={candidate.id}><strong>{candidate.metadata.title}</strong><p>{candidate.metadata.authors.join('、')} · {candidate.metadata.year ?? '年份未知'}</p><p>{candidate.metadata.abstract}</p><p>候选 {candidate.id} · 来源配置 {candidate.source.provider_config_ref.config_id}</p>
        {candidate.material_classification && <form aria-label={'来源分类 ' + candidate.id} onSubmit={event => { event.preventDefault(); const form = new FormData(event.currentTarget); const v = candidate.material_classification!; void submit({ path: base + '/material-sources/' + v.source.source_id + '/classification/' + (v.confirmation_status === 'confirmed' ? 'correct' : 'confirm'), key: crypto.randomUUID(), body: { expected_revision: v.revision, content_revision: v.source.content_revision, classification: String(form.get('classification')), basis: String(form.get('basis')), explicit_confirmation: true } }); }}><fieldset disabled={busy || !active || !!pending}><legend>本来源标题与摘要分类</legend><p>{candidate.material_classification.confirmation_status === 'confirmed' ? '已确认：' + candidate.material_classification.classification : '建议公开，尚未确认'}</p><label>分类<select name="classification" defaultValue={candidate.material_classification.classification}><option value="public">公开</option><option value="private">私人</option></select></label><label>实际内容依据<input name="basis" required maxLength={2000} /></label><button>确认来源分类</button></fieldset></form>}
        {candidate.deduplication && <section aria-label={'论文评分 ' + candidate.id}><p>评分：{candidate.screening.score ?? '未判定'} / 10 · {candidate.screening_stale ? '依据已变化，待复核' : candidate.screening.valid === null ? '待判定' : candidate.screening.valid ? '有效' : '无效'} · {candidate.screening_state === 'manual_edit' ? '人工修改' : candidate.screening_state === 'manual_confirm' ? '人工确认' : candidate.screening.score === null && candidate.screening.valid === null ? '尚无判断' : '模型草稿'}</p>{candidate.screening.reason && <p>{candidate.screening.reason}</p>}<p>默认评分阈值：7 / 10（系统默认）</p>{candidate.screening_modified_at && <p>最后人工修改：{candidate.screening_modified_by} · {candidate.screening_modified_at}</p>}{!!candidate.screening_history?.length && <details><summary>保留的判断记录</summary><ul>{candidate.screening_history.map((entry, index) => <li key={index}>{entry.at} · {entry.actor_id} · {entry.state === 'manual_edit' ? '人工修改' : entry.state === 'manual_confirm' ? '人工确认' : '模型草稿'} · 评分 {entry.screening.score ?? '未判定'} · {entry.screening.valid === null ? '待判定' : entry.screening.valid ? '有效' : '无效'} · {entry.screening.reason}</li>)}</ul></details>}{candidate.screening_error && <p role="alert">评分失败：{candidate.screening_error}；已有判断保留。</p>}{candidate.screening_basis && <details><summary>{candidate.screening_state === 'manual_edit' ? '原机器评分依据（当前以人工判断为准）' : '评分依据'}</summary><p>阈值：{candidate.screening_basis.threshold}（系统默认）；模型：{candidate.screening_basis.model_selection.model_id}</p><p>理论价值：{candidate.screening_basis.reasons.theoretical}</p><p>技术价值：{candidate.screening_basis.reasons.technical}</p><p>Project相关性：{candidate.screening_basis.reasons.relevance}</p></details>}
          {candidate.deduplication.state === 'distinct' && <><button disabled={busy || !active || !!pending || scoring || current.status !== 'waiting_user'} onClick={() => void prepareScore(candidate)}>评分或重新评分</button>
          <form aria-label={'调整评分 ' + candidate.id} onSubmit={event => { event.preventDefault(); const form = new FormData(event.currentTarget); const score = String(form.get('score') ?? '').trim(); const valid = String(form.get('valid') ?? ''); if (!score && !valid) { setError('请填写评分或选择有效性。'); return; } void submit({ path: base + '/construction-runs/' + current.id + '/candidates/' + candidate.id, method: 'PATCH', key: crypto.randomUUID(), body: { expected_revision: candidate.revision, screening: { ...(score ? { score: Number(score) } : {}), ...(valid ? { valid: valid === 'true' } : {}), reason: String(form.get('reason')) } } }); }}><fieldset disabled={busy || !active || !!pending || scoring || current.status !== 'waiting_user'}><legend>人工调整评分和有效性</legend><label>评分<input name="score" type="number" min={0} max={10} step="any" placeholder="留空则不修改评分" /></label><label>有效性<select name="valid" aria-label="有效性" defaultValue=""><option value="">随新评分判断；无新评分则保持</option><option value="true">有效</option><option value="false">无效</option></select></label><label>判断理由<input name="reason" required maxLength={10000} /></label><button>保存人工评分</button></fieldset></form></>}
        </section>}
        {candidate.deduplication && <><p>{candidate.deduplication.state === 'match' ? `重复来源，归入候选 ${candidate.deduplication.matched_candidate_id}` : candidate.deduplication.state === 'needs_title' ? '标题无有效身份，请人工核对' : '独立论文'} · {candidate.deduplication.origin === 'human' ? '人工决定' : '标题自动判断'}</p>
        <ul>{candidate.deduplication.history.map((entry, index) => <li key={index}>{entry.at} · {entry.decision} · {entry.reason}</li>)}</ul>
        {current.status === 'waiting_user' && <form aria-label={'纠正去重 ' + candidate.id} onSubmit={event => { event.preventDefault(); const form = new FormData(event.currentTarget); const target = String(form.get('target') ?? ''); void submit({ path: base + '/construction-runs/' + current.id + '/candidates/' + candidate.id + '/deduplication-decision', key: crypto.randomUUID(), body: { expected_revision: candidate.revision, decision: target ? 'match' : 'distinct', ...(target ? { matched_candidate_id: target, matched_candidate_revision: candidates.find(item => item.id === target)!.revision } : {}), reason: String(form.get('reason')) } }); }}>
          <fieldset disabled={busy || !active || !!pending || scoring}><legend>纠正合并结果</legend><label>处理方式<select name="target"><option value="">独立保留（撤销误合并）</option>{candidates.filter(other => other.id !== candidate.id && other.deduplication?.group_id).map(other => <option key={other.id} value={other.id}>合并到：{other.metadata.title} · {other.id.slice(0, 8)}</option>)}</select></label><label>纠正理由<input name="reason" required maxLength={10000} /></label><button>保存去重决定</button></fieldset>
        </form>}</>}
      </li>)}</ul>
    </div>}
  </section>;
}
