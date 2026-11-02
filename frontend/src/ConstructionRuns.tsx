import { useEffect, useRef, useState } from 'react';
import { PaperAnalysis, type Analysis } from './PaperAnalysis';

type Term = { id: string; revision: string; confirmed_revision: string | null; query: string };
type Model = { source: string; config_id: string; model_id: string };
type SourceResult = { term_id: string; config_id: string; status: string; count: number; error: string | null; limited?: boolean };
type Processing = { cleanup?: { output_tokens: number; output_defaulted: boolean; raw_text_preview: string }; source_attempts: { source_id: string; state: string }[]; status: string; text_source_kind: string | null; failure_reason: string | null; selected_source_id: string | null; source_ids: string[]; text_preview: string | null; text_length_chars?: number; diagnostics: { source_id: string | null; reason: string }[]; basis: { confirmed_revision: string | null; document_asset_id: string | null }; material_classification?: Classification };
type Run = { published_knowledge_version_id?: string; rerun_of?: string; base_knowledge_version_id?: string | null; analysis_tasks?: { task_id: string; execution_status: string; error: { code: string } | null }[]; candidate_revision: string; scoring_tasks: { task_id: string; execution_status: string; error: { code: string } | null }[]; phase: string; waiting_items: { allowed_actions?: string[]; id: string; revision: string; confirmation: { blocked_reasons?:string[]; subject_revision: string; candidate_revision: string; confirmation_token: string } | null }[]; id: string; revision: string; status: string; created_at: string; input_snapshot: { selected_terms: { term_id: string; content: { query: string } }[]; retrieval_range: { published_from: string | null; published_until: string | null }; result_limit_per_source: number; frozen_at: string } | null; config_snapshot: { pdf_cleanup?: { context_window_tokens: number; output_tokens: number; output_defaulted: boolean }; model_selection: Model; parameters: Record<string, unknown> } | null; task: { attempt_id: string }; steps: { result_summary: { analysis?: { completed: number; failed: number; pending: number; manual: number; confirmed: boolean; busy: boolean }; candidate_count: number; processing?: { available: number; degraded: number; failed: number; pending: number; excluded: number; confirmed: boolean } | null; screening: { valid_count: number; invalid_count: number; pending_count: number; failed_count: number } | null; deduplication: { unique_count: number; duplicate_count: number; unresolved_count: number } | null; sources: SourceResult[]; resolution: { executable: { term_id: string; rejected: { config_id?: string; reason_code: string }[] }[]; failed: { term_id: string; resolution: { rejected: { reason_code: string }[] } }[] } | null }; error: { code: string } | null }[] };
type Classification = { revision: string; source: { source_id: string; content_revision: string }; confirmation_status: string; classification: string };
type ScorePreview = { confirmation_token: string; risks: { id: string; message: string }[]; affected_items: { object: { id: string }; reason: string }[] };
type IngestionPreview = { base_knowledge_version_id: string | null; valid_papers: string[]; skipped: { candidate_id?: string; term_id?: string; config_id?: string | null; reason: string }[]; failed: { candidate_id?: string; term_id?: string; config_id?: string | null; reason: string }[]; degraded: { candidate_id?: string; reason: string }[]; risks: { id: string; message: string }[] };
type Candidate = { analysis?: Analysis; retained_analysis?: Analysis; analysis_current?: boolean; analysis_state?: string; analysis_error?: string | null; analysis_modified_by?: string; analysis_modified_at?: string; cleanup_pending?: { document_asset_id: string; source_id: string; material_classification: Classification }; processing_stale?: boolean; processing_history?: Processing[]; processing?: Processing; document_refs?: string[]; material_classification?: Classification; screening: { score: number | null; valid: boolean | null; reason: string | null; threshold_source: string | null }; screening_modified_by?: string; screening_modified_at?: string; screening_history?: { screening: { score: number | null; valid: boolean | null; reason: string | null }; state: string; actor_id: string; at: string }[]; screening_state?: string; screening_stale?: boolean; screening_error?: string | null; screening_basis?: { threshold: number; reasons: { theoretical: string; technical: string; relevance: string }; model_selection: Model }; revision: string; deduplication?: { state: string; group_id: string | null; origin: string; matched_candidate_id: string | null; matched_project_asset_id?: string | null; baseline_matches?: { project_paper_id: string; paper_revision_id: string; normalized_title: string }[]; history: { decision: string; reason: string; at: string }[] }; id: string; metadata: { title: string; authors: string[]; year: number | null; abstract: string | null }; source: { search_term_id: string; provider_config_ref: { config_id: string } } };
type Props = {
  project: { id: string; status: string }; actor: string;
  envelope: <T>(path: string, init?: RequestInit) => Promise<{ data: T; meta: { next_cursor: string | null; has_more: boolean } }>;
  api: <T>(path: string, init?: RequestInit) => Promise<T>;
  write: <T>(path: string, body: unknown, key?: string, actor?: string, method?: string) => Promise<T>;
  onAuthFailure: (e: unknown) => void;
};
const labels: Record<string, string> = { queued: '排队中', running: '检索中', waiting_user: '检索结果待确认', failed: '失败', cancelled: '已取消', succeeded: '已发布' };
export function ConstructionRuns({ project, actor, api, envelope, write, onAuthFailure }: Props) {
  const base = `/api/v1/projects/${project.id}`;
  const [extractionEngine, setExtractionEngine] = useState('pypdf');
  const [comparison, setComparison] = useState<Record<string, { raw_text: string; text: string }>>({});
  const [terms, setTerms] = useState<Term[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [model, setModel] = useState<Model | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [current, setCurrent] = useState<Run | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [published, setPublished] = useState<{version: string; papers: {title: string; analysis?: {one_sentence_summary?: string}}[]} | null>(null);
  const [ingestionPreview, setIngestionPreview] = useState<IngestionPreview | null>(null);
  const [from, setFrom] = useState(''); const [until, setUntil] = useState(''); const [limit, setLimit] = useState(100);
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const [scorePreview, setScorePreview] = useState<{ proof: ScorePreview; path: string; body: Record<string, unknown> } | null>(null);
  const [pending, setPending] = useState<{ path: string; key: string; body: unknown; method?: string } | null>(null);
  const epoch = useRef(0); const mounted = useRef(true);
  const headers = { 'X-Expected-Actor': actor };
  async function all<T>(path: string): Promise<{ items: T[] }> {
    let cursor: string | null = null; const items: T[] = [];
    do {
      const query: string = (path.includes('?') ? '&' : '?') + 'page_size=100' + (cursor ? '&cursor=' + encodeURIComponent(cursor) : '');
      const result: { data: { items: T[] }; meta: { next_cursor: string | null } } = await envelope<{ items: T[] }>(path + query, { headers });
      items.push(...result.data.items); cursor = result.meta.next_cursor;
    } while (cursor && mounted.current);
    return { items };
  }

  function failed(e: unknown) {
    const value = e as { status?: number; code?: string };
    if ([401, 403, 404].includes(value.status ?? 0)) { setTerms([]); setRuns([]); setCurrent(null); setCandidates([]); setIngestionPreview(null); setPending(null); onAuthFailure(e); }
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
      setRuns(list.items); setCandidates([]); setIngestionPreview(null); setTerms(ts.items); setModel(choice.valid ? choice.selection : null);
      setCurrent(old => list.items.find(r => r.id === old?.id) ?? null);
    } catch (e) { if (mounted.current && epoch.current === version) failed(e); }
  }
  useEffect(() => { mounted.current = true; void refresh(); return () => { mounted.current = false; epoch.current++; }; }, [project.id, actor]); // eslint-disable-line react-hooks/exhaustive-deps
  async function inspect(run: Run) {
    const version = ++epoch.current; setComparison({}); setError(''); setScorePreview(null); setCandidates([]); setIngestionPreview(null); setCurrent(run);
    try {
      const [detail, list] = await Promise.all([api<Run>(base + '/construction-runs/' + run.id, { headers }), all<Candidate>(base + '/construction-runs/' + run.id + '/candidates')]);
      const preview = detail.status === 'waiting_user' && detail.phase === 'ingestion_preview' ? await api<IngestionPreview>(base + '/construction-runs/' + run.id + '/ingestion-preview', { headers }) : null;
      if (mounted.current && epoch.current === version) { setCurrent(detail); setCandidates(list.items); setIngestionPreview(preview); }
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
  async function prepareAnalysis(candidate: Candidate) {
    if (!current) return;
    const path = base + '/construction-runs/' + current.id + '/candidates/' + candidate.id + '/analysis';
    const body = { expected_revision: candidate.revision };
    setBusy(true); setError('');
    try { const proof = await write<ScorePreview>(path + '/action-preview', { ...body, action: 'generate' }, crypto.randomUUID(), actor); if (mounted.current) setScorePreview({ proof, path: path + '/generate', body }); }
    catch (e) { if (mounted.current) failed(e); }
    finally { if (mounted.current) setBusy(false); }
  }
  const analyzing = current?.analysis_tasks?.some(t => ['queued', 'running'].includes(t.execution_status)) ?? false;
  const active = project.status === 'active';
  const scoring = analyzing || current?.scoring_tasks.some(t => ['queued', 'running'].includes(t.execution_status)) || false;
  return <section aria-label="构建运行" className="maintenance" aria-busy={busy}>
    <h2>构建运行</h2>
    <p>选择已确认检索词和模型，检索论文并查看来源结果。确认检索后按标题去标点、转小写去重，可人工拆分或合并。可评分、查看理由并人工调整。确认筛选后获取全文；无全文时使用真实摘要并标明来源，处理确认后可生成、编辑和确认AI分析。知识入库尚未开放。</p>
    {error && <p role="alert" className="error">{error}</p>}
    <button disabled={busy} onClick={() => { void refresh(); }}>刷新运行与配置</button>
    {pending && <button disabled={busy || !active} onClick={() => { void submit(pending); }}>用原请求核查重试</button>}
    <form onSubmit={event => { event.preventDefault(); if (!model) return; const body = { pdf_extraction_engine: extractionEngine, selected_terms: terms.filter(t => selected.includes(t.id)).map(t => ({ term_id: t.id, confirmed_revision: t.confirmed_revision })), model_selection: model, retrieval_range: { published_from: from ? from + 'T00:00:00Z' : null, published_until: until ? until + 'T00:00:00Z' : null }, result_limit_per_source: limit }; void submit({ path: base + '/construction-runs', key: crypto.randomUUID(), body }); }}>
      <fieldset disabled={busy || !active || !!pending}>
        <legend>启动论文检索</legend>
        <p>{model ? `模型：${model.source} / ${model.model_id}` : '请先在模型设置中显式选择已验证模型，然后刷新。'}</p>
        <p>未确认的词不能用于启动；每次最多选择100条。</p>
        <label>PDF提取引擎<select aria-label="PDF提取引擎" value={extractionEngine} onChange={e => setExtractionEngine(e.target.value)}><option value="pypdf">pypdf 静态文字提取</option><option value="llm_text_cleanup">LLM 文本整理</option></select></label>
        {extractionEngine === 'llm_text_cleanup' && <p>使用本轮所选模型，先静态提取，再仅调整换行。仅整理已有文字层，图片中的文字未识别。输出上限未填写时，本引擎默认4096 tokens；显式设置保持不变。保存实际PDF分类后自动继续原作业。更换引擎需新建运行。</p>}
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
      <h3>{['cancelled', 'failed', 'succeeded'].includes(current.status) ? labels[current.status] : current.status === 'waiting_user' && current.phase === 'screening' ? '去重结果待核对' : current.phase === 'processing' ? current.status === 'running' ? '正在下载解析' : '下载解析结果待确认' : current.phase === 'analysis' ? '论文AI分析' : current.phase === 'knowledge_build' ? '正在构建知识版本' : current.phase === 'ingestion_preview' ? '分析已确认，等待入库确认' : labels[current.status] ?? current.status}</h3>
      {current.status === 'waiting_user' && <p>{current.phase === 'screening' ? '可检查来源、评分并调整有效性。评分使用本轮冻结模型；先在检索词面板确认主题资料分类，再确认本页各来源分类。' : current.phase === 'processing' ? '按固定来源顺序选取首个可用全文；无全文时使用真实摘要。请逐项核对最终来源与失败项。' : current.phase === 'analysis' ? '分析使用本轮冻结模型及已确认文本；失败可重试或人工补全。修改筛选结果会使处理确认失效。' : current.phase === 'ingestion_preview' ? '请核对本次入库范围和已列出的风险。' : '检索已完成，确认后进行标题去重。'}该运行仍占用构建槽，可查看结果或取消。</p>}
      {current.status === 'running' && current.steps.some(step => step.error?.code === 'PROVIDER_RESULT_UNKNOWN') && <p role="alert">来源请求结果未知，系统没有自动重发。此运行仍占用构建槽；可取消后按需要新建运行。</p>}
      {ingestionPreview && current.status === 'waiting_user' && current.phase === 'ingestion_preview' && <section aria-label="入库预览"><h4>入库预览</h4>{ingestionPreview.base_knowledge_version_id && <p>保留基线版本 {ingestionPreview.base_knowledge_version_id} 的全部论文。</p>}<p>{ingestionPreview.base_knowledge_version_id ? "本轮拟新增论文" : "拟纳入论文"}：{ingestionPreview.valid_papers.length}；跳过：{ingestionPreview.skipped.length}；失败：{ingestionPreview.failed.length}；摘要降级：{ingestionPreview.degraded.length}。</p><ul>{ingestionPreview.valid_papers.map(id => <li key={id}>{candidates.find(c => c.id === id)?.metadata.title ?? id}</li>)}</ul>{ingestionPreview.risks.map(r => <p key={r.id}>{r.message}</p>)}{[...ingestionPreview.skipped, ...ingestionPreview.failed].map((item, i) => <p key={i}>{candidates.find(c => c.id === item.candidate_id)?.metadata.title ?? item.term_id ?? item.candidate_id}{item.config_id && ` / 来源 ${item.config_id}`}：{item.reason}</p>)}</section>}
      {current.phase === 'ingestion_preview' && current.waiting_items.flatMap(w => w.confirmation?.blocked_reasons ?? []).map(reason => <p key={reason}>{reason}</p>)}
      {ingestionPreview && current.phase === 'ingestion_preview' && current.waiting_items.map(w => w.allowed_actions?.includes('confirm_ingestion_preview') && w.confirmation && <button key={w.id} disabled={busy || !active || !!pending} onClick={() => void submit({ path: base + '/construction-runs/' + current.id + '/waiting-items/' + w.id + '/confirm', key: crypto.randomUUID(), body: { expected_revision: w.revision, subject_revision: w.confirmation!.subject_revision, candidate_revision: w.confirmation!.candidate_revision, confirmation_token: w.confirmation!.confirmation_token, acknowledged_risk_ids: ingestionPreview.risks.map(r => r.id) } })}>{ingestionPreview.risks.length ? '接受上述风险并确认入库' : '确认入库'}</button>)}
      {current.published_knowledge_version_id && <button onClick={async () => { const version=current.published_knowledge_version_id!; try { const result=await all<{title:string;analysis?:{one_sentence_summary?:string}}>(base + '/papers?knowledge_version_id=' + version); setPublished({version, papers:result.items}); } catch(e) { failed(e); } }}>查看已发布版本</button>}
      {published && published.version === current.published_knowledge_version_id && <section aria-label="已发布版本"><h4>知识版本 {published.version}</h4>{published.papers.map((p,i)=><p key={i}>{p.title} {p.analysis?.one_sentence_summary}</p>)}</section>}
      {current.status === 'waiting_user' && current.phase !== 'ingestion_preview' && current.waiting_items.map(wait => wait.confirmation && <button key={wait.id} disabled={busy || !active || !!pending} onClick={() => { void submit({ path: base + '/construction-runs/' + current.id + '/waiting-items/' + wait.id + '/confirm', key: crypto.randomUUID(), body: { expected_revision: wait.revision, subject_revision: wait.confirmation!.subject_revision, candidate_revision: wait.confirmation!.candidate_revision, confirmation_token: wait.confirmation!.confirmation_token, acknowledged_risk_ids: [] } }); }}>{current.phase === 'screening' ? '确认筛选并下载解析' : current.phase === 'processing' ? '确认处理结果' : current.phase === 'analysis' ? '确认有效分析（失败项不纳入）' : '确认检索并去重'}</button>)}
      <button disabled={busy} onClick={() => { void inspect(current); }}>刷新本次结果</button>
      {current.status === 'failed' && <button disabled={busy || !active || !!pending} onClick={() => { void submit({ path: base + '/construction-runs', key: crypto.randomUUID(), body: { rerun_of: current.id, expected_revision: current.revision } }); }}>重新运行</button>}
      {current.rerun_of && <p>来源构建：{current.rerun_of} · 本次基线：{current.input_snapshot ? current.base_knowledge_version_id ?? '首次构建' : '取得构建槽后确定'}</p>}
      {['queued', 'running', 'waiting_user'].includes(current.status) && <button disabled={busy || !active || !!pending} onClick={() => { void submit({ path: base + '/construction-runs/' + current.id + '/cancel', key: crypto.randomUUID(), body: { expected_revision: current.revision, attempt_id: current.task.attempt_id } }); }}>取消本次构建</button>}
      {current.steps.map(step => <div key="retrieval"><p>候选论文：{step.result_summary.candidate_count}</p>{step.result_summary.deduplication && <p>不同论文：{step.result_summary.deduplication.unique_count} · 重复来源：{step.result_summary.deduplication.duplicate_count} · 身份待补充：{step.result_summary.deduplication.unresolved_count}</p>}{step.error && <p role="alert">{step.error.code}</p>}<ul>{step.result_summary.resolution?.executable.flatMap(term => term.rejected.map((reason, i) => <li key={term.term_id + i}>检索词 {term.term_id} 的部分来源不可用：{reason.config_id} · {reason.reason_code}</li>))}</ul><ul>{step.result_summary.resolution?.failed.map(term => <li key={term.term_id}>检索词 {term.term_id} 未执行：{term.resolution.rejected.map(reason => reason.reason_code).join("、")}</li>)}</ul><ul>{step.result_summary.sources.map((source, i) => <li key={i}>来源 {source.config_id} · 检索词 {source.term_id}：{source.count} 条 · {source.status}{source.error && ` · ${source.error}`}{source.limited && ' · 已达到返回范围限制'}</li>)}</ul></div>)}
      {current.phase === 'screening' && <p>仅处理本轮有效且依据未失效的论文；重复、无效、未判定或失败项保留在列表中，不会作为有效论文下载。</p>}
      {current.status === 'running' && current.phase === 'processing' && <p role="status">正在获取并解析论文。处理期间不能修改候选；可刷新结果或取消。</p>}
      {current.steps[0]?.result_summary.processing && <p aria-label="处理统计">全文 {current.steps[0].result_summary.processing.available} · 摘要降级 {current.steps[0].result_summary.processing.degraded} · 失败 {current.steps[0].result_summary.processing.failed} · 待处理 {current.steps[0].result_summary.processing.pending} · 未纳入处理 {current.steps[0].result_summary.processing.excluded}</p>}
      {current.steps[0]?.result_summary.screening && <p aria-label="筛选统计">有效 {current.steps[0].result_summary.screening.valid_count} · 无效 {current.steps[0].result_summary.screening.invalid_count} · 待判定 {current.steps[0].result_summary.screening.pending_count} · 评分失败 {current.steps[0].result_summary.screening.failed_count}</p>}
      {current.steps[0]?.result_summary.analysis && <p aria-label="分析统计">有效分析 {current.steps[0].result_summary.analysis.completed} · 失败 {current.steps[0].result_summary.analysis.failed} · 待完成 {current.steps[0].result_summary.analysis.pending} · 人工修改 {current.steps[0].result_summary.analysis.manual}</p>}
      {current.analysis_tasks?.map(t => <p key={t.task_id}>分析任务：{t.execution_status}{t.error && ` · ${t.error.code}`}</p>)}
      {scoring && <p role="status">{analyzing ? '分析任务处理中，可刷新查看进度；此时不能修改候选。' : '评分任务处理中，可刷新查看进度；此时不能修改候选。'}</p>}
      {current.scoring_tasks.map(t => <p key={t.task_id}>评分任务：{t.execution_status}{t.error && ` · ${t.error.code}`}</p>)}
      {scorePreview && <section aria-label="评分确认"><h4>{scorePreview.path.endsWith('/generate') ? '分析生成范围确认' : '评分范围确认'}</h4><p>{scorePreview.path.endsWith('/generate') ? '使用本轮模型及已确认最终文本生成五字段分析；失败保留原稿。' : '使用本轮模型和各来源原始内容评分，默认有效阈值为7/10。失败保留原判断。'}</p>{scorePreview.proof.risks.map(r => <p key={r.id}>{r.message}</p>)}<ul>{scorePreview.proof.affected_items.map(i => <li key={i.object.id}>{i.object.id}：{i.reason}</li>)}</ul><button disabled={busy || !active || scoring} onClick={() => void submit({ path: scorePreview.path, key: crypto.randomUUID(), body: { ...scorePreview.body, confirmation_token: scorePreview.proof.confirmation_token, acknowledged_risk_ids: scorePreview.proof.risks.map(r => r.id) } })}>{scorePreview.path.endsWith('/generate') ? '确认生成分析' : '确认评分'}</button><button disabled={busy} onClick={() => setScorePreview(null)}>{scorePreview.path.endsWith('/generate') ? '取消分析确认' : '取消评分确认'}</button></section>}
      <details><summary>本轮输入与模型</summary>
        {current.config_snapshot?.pdf_cleanup && <p>引擎：LLM文本整理 · 冻结上下文容量 {current.config_snapshot.pdf_cleanup.context_window_tokens} tokens · 输出上限 {current.config_snapshot.pdf_cleanup.output_tokens} tokens（{current.config_snapshot.pdf_cleanup.output_defaulted ? '整理引擎默认' : '用户显式设置'}）</p>}
        {current.input_snapshot ? <><p>冻结于 {current.input_snapshot.frozen_at}；每源上限 {current.input_snapshot.result_limit_per_source}</p><p>时间范围：{current.input_snapshot.retrieval_range.published_from ?? '不限'} 至 {current.input_snapshot.retrieval_range.published_until ?? '不限'}（不含结束时刻）</p><ul>{current.input_snapshot.selected_terms.map(t => <li key={t.term_id}>{t.content.query}</li>)}</ul></> : <p>尚未取得构建资格，输入未冻结。</p>}
        {current.config_snapshot && <><p>本轮模型：{current.config_snapshot.model_selection.source} / {current.config_snapshot.model_selection.model_id}</p><dl>{Object.entries(current.config_snapshot.parameters).map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{JSON.stringify(value)}</dd></div>)}</dl></>}
      </details>
      <ul>{candidates.map(candidate => <li key={candidate.id}><strong>{candidate.metadata.title}</strong><p>{candidate.metadata.authors.join('、')} · {candidate.metadata.year ?? '年份未知'}</p><p>{candidate.metadata.abstract}</p><p>候选 {candidate.id} · 来源配置 {candidate.source.provider_config_ref.config_id}</p>
        {candidate.cleanup_pending && <section aria-label={'全文分类等待 ' + candidate.id}><p>待整理全文来源：{candidate.cleanup_pending.source_id}。摘要公开不代表此文件公开；保存分类后自动继续原作业。</p><a href={base + '/construction-runs/' + current.id + '/candidates/' + candidate.id + '/files/' + candidate.cleanup_pending.document_asset_id + '/download'}>核对待整理的PDF</a>
          {candidate.cleanup_pending.material_classification.confirmation_status === 'confirmed' ? <p>全文分类已保存，原作业将自动重验权限和预算后继续。</p> : <form aria-label={'全文分类 ' + candidate.id} onSubmit={event => { event.preventDefault(); const form = new FormData(event.currentTarget); const v = candidate.cleanup_pending!.material_classification; void submit({ path: base + '/material-sources/' + v.source.source_id + '/classification/confirm', key: crypto.randomUUID(), body: { expected_revision: v.revision, content_revision: v.source.content_revision, classification: String(form.get('classification')), basis: String(form.get('basis')), explicit_confirmation: true } }); }}><fieldset disabled={busy || !active || !!pending || current.status !== 'waiting_user'}><legend>实际PDF文件分类</legend><label>全文分类<select aria-label="全文分类" name="classification" defaultValue="private"><option value="private">私人</option><option value="public">公开</option></select></label><label>全文分类依据<input name="basis" required maxLength={2000} /></label><button>保存全文分类并继续</button></fieldset></form>}
        </section>}
        {candidate.processing && <section aria-label={'论文处理 ' + candidate.id}>
          <p>{candidate.processing_stale ? '此前处理结果，当前依据已变化，需重新处理确认' : '当前处理结果'}</p><h4>{candidate.processing.status === 'available' ? '全文解析' : candidate.processing.status === 'degraded' ? '摘要降级（不是全文）' : '处理失败'}</h4>
          {candidate.processing.cleanup && <><p>仅整理已有文字层，图片中的文字未识别。模型仅建议换行，原始文件和提取文本均保留。</p><button disabled={busy} onClick={async () => { const version = epoch.current; try { const result = await api<{raw_text: string; text: string}>(base + '/construction-runs/' + current.id + '/candidates/' + candidate.id + '/processing-text', { headers }); if (mounted.current && epoch.current === version) setComparison(old => ({ ...old, [candidate.id]: result })); } catch (e) { if (mounted.current && epoch.current === version) failed(e); } }}>核对原始与整理全文</button>{comparison[candidate.id] && <div><h5>原始提取全文</h5><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{comparison[candidate.id].raw_text}</pre><h5>整理后全文</h5><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{comparison[candidate.id].text}</pre></div>}</>}
          <p>{candidate.processing.failure_reason} · {candidate.processing.basis.confirmed_revision ? '已确认处理结果' : '处理结果未确认'}</p>
          <p>本轮所用来源：{candidate.processing.selected_source_id ?? '无可用来源'}。选择顺序：{candidate.processing.source_ids.join(' → ')}。不表示所选版本最新或其他来源无效。</p>
          {candidate.processing.text_preview && <details><summary>查看所用文本节选（前2000字符，共{candidate.processing.text_length_chars}字符）</summary><p style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{candidate.processing.text_preview}</p></details>}
          <ul>{candidate.processing.source_attempts.map(a => <li key={a.source_id}>{a.source_id}：{{ selected_full_text: '已选择全文', selected_abstract: '已选择摘要降级', failed: '未取得可用全文', not_attempted: '未尝试（请结合最终来源和预算状态核对）' }[a.state]}</li>)}</ul><ul>{candidate.processing.diagnostics.map((d, i) => <li key={i}>来源 {d.source_id ?? '未知'}：{{ source_unavailable: '文件不可获取', corrupt_content: '文件不可解析', encrypted_content: '文件已加密', no_usable_text: '没有可提取文字', safety_limit: '超过安全解析限制', parser_unavailable: '解析能力不可用', cleanup_failed: '模型整理未产生完整可用结果', capacity_exceeded: '文本超出当前容量或调用次数限制', budget_exhausted: '整理预算耗尽' }[d.reason] ?? '处理失败'}</li>)}</ul>
          {candidate.document_refs?.map(id => <a key={id} href={base + '/construction-runs/' + current.id + '/candidates/' + candidate.id + '/files/' + id + '/download'}>下载本轮保存的PDF（实际使用文本以上方来源为准）</a>)}
          {candidate.processing.material_classification && <form aria-label={'解析全文分类 ' + candidate.id} onSubmit={event => { event.preventDefault(); const form = new FormData(event.currentTarget); const v = candidate.processing!.material_classification!; void submit({ path: base + '/material-sources/' + v.source.source_id + '/classification/' + (v.confirmation_status === 'confirmed' ? 'correct' : 'confirm'), key: crypto.randomUUID(), body: { expected_revision: v.revision, content_revision: v.source.content_revision, classification: String(form.get('classification')), basis: String(form.get('basis')), explicit_confirmation: true } }); }}><fieldset disabled={busy || !active || !!pending}><legend>实际解析全文分类</legend><label>文件分类<select name="classification" defaultValue="private"><option value="private">私人</option><option value="public">公开</option></select></label><label>文件分类依据<input name="basis" required maxLength={2000} /></label><button>保存解析全文分类</button></fieldset></form>}
          {candidate.processing.material_classification && <p>全文分类：{candidate.processing.material_classification.confirmation_status === 'confirmed' ? candidate.processing.material_classification.classification : '尚未确认；摘要公开不代表全文公开'}。后续AI使用前仍须确认全文分类及当前权限。</p>}
        </section>}
        {(candidate.analysis || candidate.retained_analysis || (candidate.deduplication?.state === 'distinct' && candidate.processing?.basis.confirmed_revision)) && <PaperAnalysis key={candidate.id + candidate.revision} candidate={candidate} disabled={busy || !active || !!pending || scoring || current.status !== 'waiting_user' || !['analysis', 'ingestion_preview'].includes(current.phase) || !candidate.processing?.basis.confirmed_revision || !!candidate.processing_stale} generate={() => void prepareAnalysis(candidate)} save={analysis => void submit({ path: base + '/construction-runs/' + current.id + '/candidates/' + candidate.id, method: 'PATCH', key: crypto.randomUUID(), body: { expected_revision: candidate.revision, analysis } })} />}
        {!!candidate.processing_history?.length && <details><summary>保留的处理记录</summary><ul>{candidate.processing_history.map((entry, index) => <li key={index}>来源 {entry.selected_source_id ?? '无'} · {entry.text_source_kind === 'abstract_fallback' ? '摘要降级' : entry.text_source_kind === 'full_text' ? '全文' : '无可用文本'} · {entry.basis.confirmed_revision ? '曾确认' : '未确认'}<p style={{ whiteSpace: 'pre-wrap' }}>{entry.text_preview}</p></li>)}</ul></details>}
        {candidate.material_classification && <form aria-label={'来源分类 ' + candidate.id} onSubmit={event => { event.preventDefault(); const form = new FormData(event.currentTarget); const v = candidate.material_classification!; void submit({ path: base + '/material-sources/' + v.source.source_id + '/classification/' + (v.confirmation_status === 'confirmed' ? 'correct' : 'confirm'), key: crypto.randomUUID(), body: { expected_revision: v.revision, content_revision: v.source.content_revision, classification: String(form.get('classification')), basis: String(form.get('basis')), explicit_confirmation: true } }); }}><fieldset disabled={busy || !active || !!pending}><legend>本来源标题与摘要分类</legend><p>{candidate.material_classification.confirmation_status === 'confirmed' ? '已确认：' + candidate.material_classification.classification : '建议公开，尚未确认'}</p><label>分类<select name="classification" defaultValue={candidate.material_classification.classification}><option value="public">公开</option><option value="private">私人</option></select></label><label>实际内容依据<input name="basis" required maxLength={2000} /></label><button>确认来源分类</button></fieldset></form>}
        {candidate.deduplication && <section aria-label={'论文评分 ' + candidate.id}><p>评分：{candidate.screening.score ?? '未判定'} / 10 · {candidate.screening_stale ? '依据已变化，待复核' : candidate.screening.valid === null ? '待判定' : candidate.screening.valid ? '有效' : '无效'} · {candidate.screening_state === 'manual_edit' ? '人工修改' : candidate.screening_state === 'manual_confirm' ? '人工确认' : candidate.screening.score === null && candidate.screening.valid === null ? '尚无判断' : '模型草稿'}</p>{candidate.screening.reason && <p>{candidate.screening.reason}</p>}<p>默认评分阈值：7 / 10（系统默认）</p>{candidate.screening_modified_at && <p>最后人工修改：{candidate.screening_modified_by} · {candidate.screening_modified_at}</p>}{!!candidate.screening_history?.length && <details><summary>保留的判断记录</summary><ul>{candidate.screening_history.map((entry, index) => <li key={index}>{entry.at} · {entry.actor_id} · {entry.state === 'manual_edit' ? '人工修改' : entry.state === 'manual_confirm' ? '人工确认' : '模型草稿'} · 评分 {entry.screening.score ?? '未判定'} · {entry.screening.valid === null ? '待判定' : entry.screening.valid ? '有效' : '无效'} · {entry.screening.reason}</li>)}</ul></details>}{candidate.screening_error && <p role="alert">评分失败：{candidate.screening_error}；已有判断保留。</p>}{candidate.screening_basis && <details><summary>{candidate.screening_state === 'manual_edit' ? '原机器评分依据（当前以人工判断为准）' : '评分依据'}</summary><p>阈值：{candidate.screening_basis.threshold}（系统默认）；模型：{candidate.screening_basis.model_selection.model_id}</p><p>理论价值：{candidate.screening_basis.reasons.theoretical}</p><p>技术价值：{candidate.screening_basis.reasons.technical}</p><p>Project相关性：{candidate.screening_basis.reasons.relevance}</p></details>}
          {candidate.deduplication.state === 'distinct' && <><button disabled={busy || !active || !!pending || scoring || current.status !== 'waiting_user'} onClick={() => void prepareScore(candidate)}>评分或重新评分</button>
          <form aria-label={'调整评分 ' + candidate.id} onSubmit={event => { event.preventDefault(); const form = new FormData(event.currentTarget); const score = String(form.get('score') ?? '').trim(); const valid = String(form.get('valid') ?? ''); if (!score && !valid) { setError('请填写评分或选择有效性。'); return; } void submit({ path: base + '/construction-runs/' + current.id + '/candidates/' + candidate.id, method: 'PATCH', key: crypto.randomUUID(), body: { expected_revision: candidate.revision, screening: { ...(score ? { score: Number(score) } : {}), ...(valid ? { valid: valid === 'true' } : {}), reason: String(form.get('reason')) } } }); }}><fieldset disabled={busy || !active || !!pending || scoring || current.status !== 'waiting_user'}><legend>人工调整评分和有效性</legend><label>评分<input name="score" type="number" min={0} max={10} step="any" placeholder="留空则不修改评分" /></label><label>有效性<select name="valid" aria-label="有效性" defaultValue=""><option value="">随新评分判断；无新评分则保持</option><option value="true">有效</option><option value="false">无效</option></select></label><label>判断理由<input name="reason" required maxLength={10000} /></label><button>保存人工评分</button></fieldset></form></>}
        </section>}
        {candidate.deduplication && <><p>{candidate.deduplication.state === 'match' ? `重复来源，归入候选 ${candidate.deduplication.matched_candidate_id}` : candidate.deduplication.state === 'match_existing' ? `已存在于当前知识版本：${candidate.deduplication.matched_project_asset_id}` : candidate.deduplication.state === 'needs_existing_resolution' ? '同标题对应多个已有身份，请人工核对' : candidate.deduplication.state === 'needs_title' ? '标题无有效身份，请人工核对' : '独立论文'} · {candidate.deduplication.origin === 'human' ? '人工决定' : '标题自动判断'}</p>
        <ul>{candidate.deduplication.history.map((entry, index) => <li key={index}>{entry.at} · {entry.decision} · {entry.reason}</li>)}</ul>
        {current.status === 'waiting_user' && <form aria-label={'纠正去重 ' + candidate.id} onSubmit={event => { event.preventDefault(); const form = new FormData(event.currentTarget); const selectedTarget = String(form.get('target') ?? ''); const existingId = String(form.get('existing_asset') ?? '').trim(); if (existingId && selectedTarget) { setError('请选择一个合并目标。'); return; } const target = existingId ? 'asset:' + existingId : selectedTarget; void submit({ path: base + '/construction-runs/' + current.id + '/candidates/' + candidate.id + '/deduplication-decision', key: crypto.randomUUID(), body: { expected_revision: candidate.revision, decision: target ? 'match' : 'distinct', ...(target.startsWith('asset:') ? { matched_project_asset_id: target.slice(6) } : target ? { matched_candidate_id: target, matched_candidate_revision: candidates.find(item => item.id === target)!.revision } : {}), reason: String(form.get('reason')) } }); }}>
          <fieldset disabled={busy || !active || !!pending || scoring}><legend>纠正合并结果</legend><label>处理方式<select name="target"><option value="">独立保留（撤销误合并）</option>{(candidate.deduplication?.baseline_matches ?? []).map(item => <option key={item.project_paper_id} value={'asset:' + item.project_paper_id}>合并到已有论文：{item.project_paper_id.slice(0, 8)}</option>)}{candidates.filter(other => other.id !== candidate.id && other.deduplication?.group_id).map(other => <option key={other.id} value={other.id}>合并到：{other.metadata.title} · {other.id.slice(0, 8)}</option>)}</select></label><label>其他已有论文 ID（可选）<input name="existing_asset" /></label><label>纠正理由<input name="reason" required maxLength={10000} /></label><button>保存去重决定</button></fieldset>
        </form>}</>}
      </li>)}</ul>
    </div>}
  </section>;
}
