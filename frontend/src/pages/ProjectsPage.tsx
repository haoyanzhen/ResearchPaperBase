import { FolderPlus, Settings } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  projectsApi,
  type ProjectSummary,
} from "../../api/projects";
import { Alert } from "../components/Alert";
import { ProjectModal } from "../components/ProjectModal";
import { useAuth } from "../contexts/AuthContext";
import { formatDate } from "../utils/format";

export function ProjectsPage() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const loadProjects = async () => {
    setLoading(true);
    try {
      const response = await projectsApi.list();
      setProjects(response.items);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载项目失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadProjects();
  }, []);

  const handleCreate = async (payload: { name: string; description?: string }) => {
    const project = await projectsApi.create(payload);
    await loadProjects();
    navigate(`/projects/${project.project_id}`);
  };

  const handleDelete = async (projectId: string) => {
    if (!window.confirm("确定删除这个项目吗？相关构建、对话和综述数据都会一并移除。")) {
      return;
    }
    try {
      await projectsApi.delete(projectId);
      await loadProjects();
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    }
  };

  return (
    <div className="content">
      <header className="page-header">
        <div>
          <h1>我的研究项目</h1>
          <p>从一个问题出发，把论文库、对话研究和综述写作串成同一条工作流。</p>
        </div>
        <div className="toolbar">
          <button className="icon-button" onClick={() => navigate("/settings")} aria-label="设置">
            <Settings size={16} />
          </button>
          <button className="button" onClick={() => setCreating(true)}>
            <FolderPlus size={16} />
            <span>新建项目</span>
          </button>
          <button className="button button--ghost" onClick={() => void logout()}>
            退出
          </button>
        </div>
      </header>

      {error && <Alert tone="error" message={error} />}

      {loading ? (
        <div className="empty-state">正在加载项目列表...</div>
      ) : (
        <div className="projects-grid">
          {projects.map((project) => (
            <article key={project.project_id} className="project-card">
              <div>
                <h3>{project.name}</h3>
                <div className="inline-meta">
                  模式：{project.mode} · 状态：{project.status}
                </div>
              </div>
              <div className="grid grid--stats">
                <div className="stat-card">
                  <span className="stat-card__label">有效论文</span>
                  <span className="stat-card__value">{project.valid_papers}</span>
                </div>
                <div className="stat-card">
                  <span className="stat-card__label">总论文</span>
                  <span className="stat-card__value">{project.total_papers}</span>
                </div>
              </div>
              <div className="project-card__meta">更新于 {formatDate(project.updated_at)}</div>
              <div className="project-card__actions">
                <button className="button" onClick={() => navigate(`/projects/${project.project_id}`)}>
                  打开
                </button>
                <button className="button button--ghost" onClick={() => navigate(`/projects/${project.project_id}`)}>
                  设置
                </button>
                <button className="button button--danger" onClick={() => void handleDelete(project.project_id)}>
                  删除
                </button>
              </div>
            </article>
          ))}
          {!projects.length && (
            <div className="empty-state">
              还没有研究项目。先建一个，我们就能开始把前端和服务层一起跑通。
            </div>
          )}
        </div>
      )}

      {user && (
        <ProjectModal
          open={creating}
          onClose={() => setCreating(false)}
          onSubmit={handleCreate}
        />
      )}
    </div>
  );
}
