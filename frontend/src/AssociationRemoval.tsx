import { useState } from 'react';

type Paper = { id: string; title: string };
type Preview = {
  subject_revision: string;
  base_knowledge_version_id: string;
  confirmation_token: string;
  targets: { id: string; asset_revision: string }[];
  conflicting_runs: { run_id: string; revision: string; reason: string }[];
  risks: { id: string; message: string }[];
};
type Props = {
  disabled: boolean;
  load: () => Promise<Paper[]>;
  preview: (selection: unknown) => Promise<Preview>;
  confirm: (preview: Preview) => void;
  onError: (error: unknown) => void;
};
export function AssociationRemoval({ disabled, load, preview, confirm, onError }: Props) {
  const [papers, setPapers] = useState<Paper[] | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [proof, setProof] = useState<Preview | null>(null);
  const [working, setWorking] = useState(false);
  async function prepare(all: boolean) {
    setWorking(true);
    setProof(null);
    try {
      setProof(await preview(all ? { scope: 'all', kind: 'paper' } : {
        scope: 'selected', targets: selected.map(id => ({ kind: 'paper', id })),
      }));
    } catch (error) { onError(error); }
    finally { setWorking(false); }
  }
  return <fieldset disabled={disabled || working}>
    <legend>移除知识成员</legend>
    <button onClick={async () => {
      setWorking(true); setProof(null); setSelected([]); setPapers(null);
      try { setPapers(await load()); } catch (error) { onError(error); }
      finally { setWorking(false); }
    }}>加载当前版本论文</button>
    {papers?.length === 0 && <p>当前版本没有论文成员。</p>}
    {!!papers?.length && <>
      {papers.map(paper => <label key={paper.id}><input type="checkbox"
        checked={selected.includes(paper.id)} onChange={event => {
          setProof(null);
          setSelected(event.target.checked ? [...selected, paper.id] : selected.filter(id => id !== paper.id));
        }} />{paper.title}</label>)}
      <button disabled={!selected.length} onClick={() => void prepare(false)}>预览移除所选论文</button>
      <button onClick={() => void prepare(true)}>预览移除全部论文</button>
    </>}
    {proof && <section aria-label="移除影响预览"><h4>核对移除范围</h4>
      <p>基线版本 {proof.base_knowledge_version_id}</p>
      <ul>{proof.targets.map(target => <li key={target.id}>
        {papers?.find(p => p.id === target.id)?.title ?? target.id} · 修订 {target.asset_revision}
      </li>)}</ul>
      {proof.conflicting_runs.map(run => <p key={run.run_id}>将终止构建 {run.run_id} · 修订 {run.revision} · {run.reason}</p>)}
      {proof.risks.map(risk => <p key={risk.id}>{risk.message}</p>)}
      <button onClick={() => { confirm(proof); setProof(null); setPapers(null); setSelected([]); }}>确认以上范围并启动移除构建</button>
      <button onClick={() => setProof(null)}>取消移除预览</button>
    </section>}
  </fieldset>;
}
