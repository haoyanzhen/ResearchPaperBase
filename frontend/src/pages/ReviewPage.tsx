import { CheckCircle2, FileText, PlayCircle, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { projectsApi, type ProjectDetail, type ProjectSummary } from "../../api/projects";
import {
  reviewApi,
  type ChapterDetail,
  type ChapterSummaryItem,
  type OutlineDetail,
  type OutlineSummaryItem,
} from "../../api/review";
import { Alert } from "../components/Alert";
import { AppShell } from "../components/AppShell";

export function ReviewPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [outlines, setOutlines] = useState<OutlineSummaryItem[]>([]);
  const [outline, setOutline] = useState<OutlineDetail | null>(null);
  const [chapters, setChapters] = useState<ChapterSummaryItem[]>([]);
  const [chapterDetail, setChapterDetail] = useState<ChapterDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const loadData = async () => {
    if (!projectId) return;
    try {
      const [projectList, detail, outlineList, status] = await Promise.all([
        projectsApi.list(),
        projectsApi.get(projectId),
        reviewApi.getOutlines(projectId).catch(() => []),
        reviewApi.getStatus(projectId).catch(() => null),
      ]);
      setProjects(projectList.items);
      setProject(detail);
      setOutlines(outlineList);

      const latest = outlineList[0];
      if (latest) {
        const detailOutline = await reviewApi.getOutline(projectId, latest.outline_id);
        setOutline(detailOutline);
        const chapterList = await reviewApi.getChapters(projectId, latest.outline_id).catch(() => []);
        setChapters(chapterList);
        if (chapterList[0]) {
          const chapter = await reviewApi.getChapter(projectId, latest.outline_id, chapterList[0].chapter_id);
          setChapterDetail(chapter);
        }
      }

      if (!detail.valid_papers && !status) {
        setMessage("当前项目还没有有效论文，综述模式暂时只能先展示入口与状态。");
      }
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载综述页面失败");
    }
  };

  useEffect(() => {
    void loadData();
  }, [projectId]);

  const handleModeChange = async (mode: "construction" | "deep_research" | "review") => {
    if (!projectId) return;
    if (mode === "review") return;
    try {
      await projectsApi.switchMode(projectId, { target_mode: mode });
      navigate(mode === "construction" ? `/projects/${projectId}` : `/projects/${projectId}/dialogue`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "切换模式失败");
    }
  };

  const handleStartReview = async () => {
    if (!projectId) return;
    try {
      const result = await reviewApi.start(projectId, {});
      setMessage(`综述流程已启动，阶段 ${result.stage}`);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "启动综述失败");
    }
  };

  const outlineSections = useMemo(() => outline?.outline?.sections ?? [], [outline]);

  return (
    <AppShell
      project={project}
      projects={projects}
      mode="review"
      selectedNav="outline"
      getProjectHref={(nextProjectId) => `/projects/${nextProjectId}/review`}
      onModeChange={(mode) => void handleModeChange(mode)}
      sidebarItems={[
        { key: "outline", label: "综述架构", icon: <FileText size={16} /> },
        { key: "chapters", label: "章节列表", icon: <Sparkles size={16} /> },
      ]}
    >
      <header className="page-header">
        <div>
          <h1>{project?.name ?? "综述工作台"}</h1>
          <p>这里接的是 review 服务层：状态、架构、章节和导出接口都可以独立访问。</p>
        </div>
        <button
          className="button"
          data-testid="start-review"
          disabled={(project?.valid_papers ?? 0) === 0}
          onClick={() => void handleStartReview()}
        >
          <PlayCircle size={16} />
          启动综述
        </button>
      </header>

      {message && <Alert tone="info" message={message} />}
      {error && <Alert tone="error" message={error} />}

      <div className="data-grid data-grid--two">
        <section className="section-card">
          <div className="section-header">
            <div>
              <h3>架构预览</h3>
              <p>阶段 2 的草稿与人工确认区。</p>
            </div>
          </div>
          {outline ? (
            <div className="stack review-outline" data-testid="outline-preview">
              <div>
                <h3>{outline.outline?.title || "未生成标题"}</h3>
                <p className="muted">{outline.topic_expansion || "等待课题扩写结果。"}</p>
              </div>
              {outlineSections.length ? (
                <table className="table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>章节标题</th>
                      <th>类型</th>
                    </tr>
                  </thead>
                  <tbody>
                    {outlineSections.map((section) => (
                      <tr key={section.index}>
                        <td>{section.index}</td>
                        <td>{section.title}</td>
                        <td>{section.type}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="empty-state">还没有架构草稿，可以先启动综述。</div>
              )}
            </div>
          ) : (
            <div className="empty-state">当前还没有综述架构草稿。</div>
          )}
        </section>

        <section className="section-card">
          <div className="section-header">
            <div>
              <h3>章节状态</h3>
              <p>阶段 3 和阶段 4 的主要落点。</p>
            </div>
          </div>
          {chapters.length ? (
            <div className="stack">
              {chapters.map((chapter) => (
                <button
                  key={chapter.chapter_id}
                  className="dialogue-list__item"
                  onClick={async () => {
                    if (!projectId || !outline) return;
                    const detail = await reviewApi.getChapter(projectId, outline.outline_id, chapter.chapter_id);
                    setChapterDetail(detail);
                  }}
                >
                  <div>{chapter.chapter_index}. {chapter.title}</div>
                  <div className="inline-meta">
                    {chapter.status} · 审查次数 {chapter.iteration_count}
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <div className="empty-state">章节列表还没有生成。</div>
          )}
        </section>
      </div>

      <section className="section-card">
        <div className="section-header">
          <div>
            <h3>章节内容</h3>
            <p>当前选中章节的正文与引用摘要。</p>
          </div>
          {chapterDetail && (
            <span className="pill pill--completed">
              <CheckCircle2 size={14} />
              {chapterDetail.status}
            </span>
          )}
        </div>
        {chapterDetail ? (
          <div className="stack">
            <h3>{chapterDetail.chapter_index}. {chapterDetail.title}</h3>
            <textarea rows={14} value={chapterDetail.content || ""} readOnly />
            <div className="muted">
              引用数：{chapterDetail.citations?.length ?? 0} · 迭代次数：{chapterDetail.iteration_count}
            </div>
          </div>
        ) : (
          <div className="empty-state">选择一个章节后，这里会展示正文和引用信息。</div>
        )}
      </section>
    </AppShell>
  );
}
