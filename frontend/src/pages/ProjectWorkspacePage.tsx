import {
  Activity,
  CalendarClock,
  Eye,
  FileStack,
  FolderKanban,
  History,
  Search,
  ShieldAlert,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { constructionApi } from "../../api/construction";
import { InspectorPanel } from "../../components/InspectorPanel";
import {
  projectsApi,
  type PaperItem,
  type ProjectDetail,
  type ProjectSummary,
} from "../../api/projects";
import { Alert } from "../components/Alert";
import { AppShell } from "../components/AppShell";
import { useProjectEventStream } from "../hooks/useProjectEventStream";
import { formatDate } from "../utils/format";

type StageRecordItem = {
  record_id: string;
  mode: string;
  stage: number;
  status: string;
  started_at: string;
  completed_at: string | null;
  error: string | null;
};

const CONSTRUCTION_NAV = [
  { key: "overview", label: "构建流程", icon: <FolderKanban size={16} /> },
  { key: "papers", label: "论文库", icon: <FileStack size={16} /> },
  { key: "history", label: "检索历史", icon: <History size={16} /> },
  { key: "schedule", label: "定时设置", icon: <CalendarClock size={16} /> },
];

export function ProjectWorkspacePage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [papers, setPapers] = useState<PaperItem[]>([]);
  const [history, setHistory] = useState<StageRecordItem[]>([]);
  const [activeNav, setActiveNav] = useState("overview");
  const [loading, setLoading] = useState(true);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [currentStage, setCurrentStage] = useState<{
    current_stage: number | null;
    stage_status?: string | null;
    status?: string;
  } | null>(null);
  const streamEvent = useProjectEventStream(projectId);

  const loadProject = async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const [listResponse, detail, papersResponse, stageRecords, statusResponse] = await Promise.all([
        projectsApi.list(),
        projectsApi.get(projectId),
        projectsApi.listPapers(projectId, { page_size: 10 }),
        projectsApi.getStageRecords(projectId) as Promise<StageRecordItem[]>,
        projectsApi.getStatus(projectId) as Promise<{ current_stage: number | null; stage_status?: string | null; status?: string }>,
      ]);
      setProjects(listResponse.items);
      setProject(detail);
      setPapers(papersResponse.items);
      setHistory(stageRecords);
      setCurrentStage(statusResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载项目失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadProject();
  }, [projectId]);

  useEffect(() => {
    if (!streamEvent) return;
    if (streamEvent.event === "stage_error") {
      setError(
        String(streamEvent.payload.message ?? streamEvent.payload.error ?? streamEvent.payload.code ?? "阶段执行失败"),
      );
    }
    if (streamEvent.event === "stage_start") {
      setMessage(`已收到阶段事件：${String(streamEvent.payload.stage_name ?? "任务启动")}`);
    }
  }, [streamEvent]);

  const handleModeChange = async (mode: "construction" | "deep_research" | "review") => {
    if (!projectId || !project) return;
    try {
      await projectsApi.switchMode(projectId, { target_mode: mode });
      if (mode === "deep_research") {
        navigate(`/projects/${projectId}/dialogue`);
        return;
      }
      if (mode === "review") {
        navigate(`/projects/${projectId}/review`);
        return;
      }
      await loadProject();
    } catch (err) {
      setError(err instanceof Error ? err.message : "切换模式失败");
    }
  };

  const handleStartConstruction = async () => {
    if (!projectId) return;
    try {
      const result = await constructionApi.start(projectId, {});
      setMessage(result.message);
      await loadProject();
    } catch (err) {
      setError(err instanceof Error ? err.message : "启动构建失败");
    }
  };

  const handleScheduleUpdate = async (autoPush: boolean, pushInterval?: number) => {
    if (!projectId) return;
    try {
      await projectsApi.updateSchedule(projectId, {
        auto_push: autoPush,
        push_interval: autoPush ? pushInterval : undefined,
      });
      setMessage("定时推送设置已更新");
      await loadProject();
    } catch (err) {
      setError(err instanceof Error ? err.message : "更新定时设置失败");
    }
  };

  const stageBadge = useMemo(() => {
    const status = currentStage?.stage_status ?? project?.status ?? "idle";
    return <span className={`pill pill--${status}`}>{status}</span>;
  }, [currentStage?.stage_status, project?.status]);

  if (loading) {
    return <div className="content"><div className="empty-state">正在加载项目工作台...</div></div>;
  }

  if (!project) {
    return <div className="content"><Alert tone="error" message="项目不存在或当前账号无权限访问" /></div>;
  }

  return (
    <AppShell
      project={project}
      projects={projects}
      mode={project.mode}
      selectedNav={activeNav}
      getProjectHref={(nextProjectId) => `/projects/${nextProjectId}`}
      onNavChange={setActiveNav}
      onModeChange={handleModeChange}
      sidebarItems={CONSTRUCTION_NAV}
      aside={
        <button
          className="button button--ghost"
          data-testid="open-inspector"
          onClick={() => setInspectorOpen((open) => !open)}
        >
          <ShieldAlert size={16} />
          <span>Inspector</span>
        </button>
      }
    >
      <header className="page-header">
        <div>
          <h1>{project.name}</h1>
          <p>{project.description || "当前项目尚未填写描述，可以在设置页补充研究目标与背景。"}</p>
        </div>
        <div className="toolbar">
          {stageBadge}
          <button className="button" data-testid="start-construction" onClick={() => void handleStartConstruction()}>
            开始构建
          </button>
        </div>
      </header>

      {message && <Alert tone="success" message={message} />}
      {error && (
        <div data-testid="stage-error">
          <Alert tone="error" message={error} />
        </div>
      )}

      <div className="grid grid--stats">
        <div className="stat-card">
          <span className="stat-card__label">有效论文</span>
          <span className="stat-card__value">{project.valid_papers}</span>
        </div>
        <div className="stat-card">
          <span className="stat-card__label">总论文</span>
          <span className="stat-card__value">{project.total_papers}</span>
        </div>
        <div className="stat-card" data-testid="current-stage">
          <span className="stat-card__label">当前阶段</span>
          <span className="stat-card__value">{currentStage?.current_stage ?? "—"}</span>
        </div>
        <div className="stat-card">
          <span className="stat-card__label">下次推送</span>
          <span className="stat-card__value">{project.next_push_at ? formatDate(project.next_push_at) : "未设置"}</span>
        </div>
      </div>

      <div className="split">
        <section className="section-card" data-testid="stage-progress">
          <div className="section-header">
            <div>
              <h3>构建流程</h3>
              <p>普通用户的核心服务链路已经接入：项目、论文、任务状态和定时设置都走真实 API。</p>
            </div>
            {stageBadge}
          </div>
          <div className="stack">
            <div className="inline-meta">当前阶段：{currentStage?.current_stage ?? "尚未启动"}</div>
            <div className="inline-meta">项目模式：{project.mode}</div>
            <div className="inline-meta">项目状态：{project.status}</div>
            <div className="toolbar">
              <button className="button button--ghost" onClick={() => navigate(`/projects/${project.project_id}/dialogue`)}>
                深度研究
              </button>
              <button className="button button--ghost" onClick={() => navigate(`/projects/${project.project_id}/review`)}>
                综述工作台
              </button>
            </div>
          </div>
        </section>

        <section className="section-card">
          <div className="section-header">
            <div>
              <h3>定时推送</h3>
              <p>按项目维度控制自动推送节奏。</p>
            </div>
          </div>
          <div className="form">
            <label className="field">
              <span>是否启用</span>
              <select
                value={project.auto_push ? "on" : "off"}
                onChange={(event) => void handleScheduleUpdate(event.target.value === "on", project.push_interval ?? 7)}
              >
                <option value="off">关闭</option>
                <option value="on">开启</option>
              </select>
            </label>
            <label className="field">
              <span>推送间隔（天）</span>
              <select
                defaultValue={String(project.push_interval ?? 7)}
                onChange={(event) => void handleScheduleUpdate(project.auto_push, Number(event.target.value))}
              >
                {[1, 3, 7, 14, 30].map((value) => (
                  <option key={value} value={value}>{value} 天</option>
                ))}
              </select>
            </label>
          </div>
        </section>
      </div>

      <div className="data-grid data-grid--two">
        <section className="section-card">
          <div className="section-header">
            <div>
              <h3>论文库</h3>
              <p>最近 10 篇论文，支持从真实服务层读取评分与推送状态。</p>
            </div>
            <button className="button button--ghost" onClick={() => setActiveNav("papers")}>
              <Search size={16} />
              查看更多
            </button>
          </div>
          {papers.length ? (
            <table className="table">
              <thead>
                <tr>
                  <th>标题</th>
                  <th>总分</th>
                  <th>状态</th>
                  <th>期刊</th>
                </tr>
              </thead>
              <tbody>
                {papers.map((paper) => (
                  <tr key={paper.paper_id}>
                    <td>
                      <div>{paper.title}</div>
                      <div className="muted">{paper.authors?.join("、") || "未知作者"}</div>
                    </td>
                    <td>{paper.total_score ?? "—"}</td>
                    <td><span className={`pill pill--${paper.is_valid ? "completed" : "paused"}`}>{paper.is_valid ? "有效" : "待筛选"}</span></td>
                    <td>{paper.venue || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="empty-state">论文库还没有内容。启动构建后，这里会逐步填充。</div>
          )}
        </section>

        <section className="section-card">
          <div className="section-header">
            <div>
              <h3>阶段历史</h3>
              <p>最近的任务记录，方便确认普通用户服务层是否完整落地。</p>
            </div>
          </div>
          {history.length ? (
            <div className="stack">
              {history.slice(0, 6).map((item) => (
                <div key={item.record_id} className="inspector-stage">
                  <div className="inspector-stage__header">
                    <span>{item.mode}</span>
                    <span>阶段 {item.stage}</span>
                    <span className={`pill pill--${item.status}`}>{item.status}</span>
                    <span className="muted">{formatDate(item.started_at)}</span>
                  </div>
                  {item.error && <div className="muted">{item.error}</div>}
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state">还没有阶段记录。</div>
          )}
        </section>
      </div>

      {inspectorOpen && (
        <InspectorPanel projectId={project.project_id} refreshInterval={0} onClose={() => setInspectorOpen(false)} />
      )}
    </AppShell>
  );
}
