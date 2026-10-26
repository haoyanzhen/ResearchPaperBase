import { useState } from 'react';
const pages = ['Projects', '设置'] as const;
export function App() {
  const [page, setPage] = useState<typeof pages[number]>('Projects');
  return <div className="app">
    <a className="skip" href="#content">跳到内容</a>
    <header><a className="brand" href="/">Research Paper Base</a><span className="badge">工程预览</span></header>
    <nav aria-label="主导航">{pages.map(item => <button key={item} aria-current={page === item ? 'page' : undefined} onClick={() => setPage(item)}>{item}</button>)}</nav>
    <main id="content" tabIndex={-1}>
      <p className="eyebrow">研究工作空间</p><h1>{page}</h1>
      <p className="intro">从文献发现，到有据可循的研究。</p>
      <section aria-label="功能状态" className="empty"><div className="symbol" aria-hidden="true">▤</div>
        <h2>{page === 'Projects' ? '项目功能尚未接入' : '账号与配置功能尚未接入'}</h2>
        <p>当前为工程骨架预览，未连接业务数据。</p>
        <button disabled>{page === 'Projects' ? '创建 Project（尚未实现）' : '保存设置（尚未实现）'}</button>
      </section>
      <footer>文献构建 · 研究对话 · 文献综述</footer>
    </main>
  </div>;
}
