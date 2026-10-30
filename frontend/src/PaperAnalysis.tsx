import { useState } from 'react';

export type Analysis = { one_sentence_summary: string; highlights: string[]; relevance_points: string[]; methods: string; innovations: string[] };
type Candidate = { id: string; revision: string; analysis?: Analysis; retained_analysis?: Analysis; analysis_state?: string; analysis_error?: string | null; analysis_modified_at?: string; analysis_modified_by?: string; analysis_current?: boolean };
type Props = { candidate: Candidate; disabled: boolean; save: (analysis: Analysis) => void; generate: () => void };
const arrays = { highlights: '亮点解析', relevance_points: 'Project相关性要点', innovations: '创新点' };
export function PaperAnalysis({ candidate, disabled, save, generate }: Props) {
  const [draft, setDraft] = useState<Analysis>(() => structuredClone(candidate.analysis ?? candidate.retained_analysis ?? { one_sentence_summary: '', methods: '', highlights: [], relevance_points: [], innovations: [] }));
  return <section aria-label={'论文分析 ' + candidate.id}>
    <h4>论文 AI 分析</h4>
    <p>{candidate.analysis_current === false && candidate.retained_analysis ? '处理依据已变，保留旧稿供核对；不可作为当前分析确认。' : candidate.analysis_state === 'manual_edit' ? '人工修改' : candidate.analysis_state === 'confirmed' ? '人工确认' : candidate.analysis ? '模型草稿，待确认' : '尚无有效分析，可生成或人工补全。'}</p>
    {candidate.analysis_modified_at && <p>最后修改：{candidate.analysis_modified_by} · {candidate.analysis_modified_at}</p>}
    {candidate.analysis_error && <p role="alert">分析失败：{candidate.analysis_error}。已有稿件保留，可重新生成或人工补全。</p>}
    <button disabled={disabled} onClick={generate}>生成或重新生成分析</button>
    <form onSubmit={e => { e.preventDefault(); save(draft); }}>
      <fieldset disabled={disabled}><legend>编辑论文分析</legend><p>没有依据的要点可留空；方法缺失请明确说明。</p>
        <label>一句话总结<textarea aria-label="一句话总结" required maxLength={10000} value={draft.one_sentence_summary} onChange={e => setDraft(old => ({ ...old, one_sentence_summary: e.target.value }))} /></label>
        <label>技术方法<textarea aria-label="技术方法" required maxLength={10000} value={draft.methods} onChange={e => setDraft(old => ({ ...old, methods: e.target.value }))} /></label>
        {Object.entries(arrays).map(([key, label]) => { const field = key as keyof typeof arrays; return <div key={key}><h5>{label}</h5>{draft[field].map((value, index) => <div key={index}><label>{label} {index + 1}<textarea aria-label={label + " " + (index + 1)} required maxLength={2000} value={value} onChange={e => setDraft(old => ({ ...old, [field]: old[field].map((v, i) => i === index ? e.target.value : v) }))} /></label><button type="button" onClick={() => setDraft(old => ({ ...old, [field]: old[field].filter((_, i) => i !== index) }))}>移除{label} {index + 1}</button></div>)}<button type="button" disabled={draft[field].length >= 100} onClick={() => setDraft(old => ({ ...old, [field]: [...old[field], ''] }))}>添加{label}</button></div>; })}
        <button>保存人工分析</button>
      </fieldset>
    </form>
  </section>;
}
