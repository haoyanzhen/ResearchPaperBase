import {
  FileText,
  FolderKanban,
  LayoutPanelLeft,
  Microscope,
  Settings,
} from "lucide-react";
import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";

import type { ProjectDetail, ProjectSummary } from "../../api/projects";
import type { MeResponse } from "../../api/auth";
import { useAuth } from "../contexts/AuthContext";
import { classNames } from "../utils/format";

type NavItem = {
  key: string;
  label: string;
  icon: ReactNode;
};

type AppShellProps = {
  project?: ProjectDetail | null;
  projects?: ProjectSummary[];
  mode: "construction" | "deep_research" | "review";
  selectedNav: string;
  onNavChange?: (key: string) => void;
  onModeChange?: (mode: "construction" | "deep_research" | "review") => void;
  getProjectHref?: (projectId: string) => string;
  children: ReactNode;
  sidebarItems: NavItem[];
  aside?: ReactNode;
};

function UserBadge({ user }: { user: MeResponse }) {
  return (
    <div className="user-badge">
      <div className="user-badge__avatar">{user.username.slice(0, 1).toUpperCase()}</div>
      <div>
        <div className="user-badge__name">{user.username}</div>
        <div className="user-badge__meta">{user.is_admin ? "管理员" : "普通用户"}</div>
      </div>
    </div>
  );
}

export function AppShell({
  project,
  projects = [],
  mode,
  selectedNav,
  onNavChange,
  onModeChange,
  getProjectHref,
  children,
  sidebarItems,
  aside,
}: AppShellProps) {
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  const currentProjectId = project?.project_id ?? "";

  return (
    <div className="app-shell">
      <header className="topbar">
        <Link to="/projects" className="brand">
          <LayoutPanelLeft size={18} />
          <span>Research Paper Base</span>
        </Link>

        <div className="topbar__center">
          <select
            className="project-select"
            value={currentProjectId}
            onChange={(event) => {
              const nextId = event.target.value;
              if (nextId) navigate(getProjectHref?.(nextId) ?? `/projects/${nextId}`);
            }}
          >
            <option value="">选择项目</option>
            {projects.map((item) => (
              <option key={item.project_id} value={item.project_id}>
                {item.name}
              </option>
            ))}
          </select>

          <div className="mode-tabs">
            {[
              { value: "construction", label: "构建", icon: <FolderKanban size={14} /> },
              { value: "deep_research", label: "深度研究", icon: <Microscope size={14} /> },
              { value: "review", label: "综述", icon: <FileText size={14} /> },
            ].map((tab) => (
              <button
                key={tab.value}
                className={classNames("mode-tab", mode === tab.value && "mode-tab--active")}
                onClick={() => onModeChange?.(tab.value as AppShellProps["mode"])}
                type="button"
              >
                {tab.icon}
                <span>{tab.label}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="topbar__actions">
          <button className="icon-button" onClick={() => navigate("/settings")} aria-label="设置">
            <Settings size={16} />
          </button>
          {user && <UserBadge user={user} />}
          <button className="button button--ghost" onClick={() => void logout()}>
            退出
          </button>
        </div>
      </header>

      <div className="workspace">
        <aside className="sidebar">
          <div className="sidebar__group">
            {sidebarItems.map((item) => (
              <button
                key={item.key}
                className={classNames("sidebar__item", selectedNav === item.key && "sidebar__item--active")}
                onClick={() => onNavChange?.(item.key)}
                type="button"
              >
                {item.icon}
                <span>{item.label}</span>
              </button>
            ))}
          </div>
          {aside && <div className="sidebar__aside">{aside}</div>}
        </aside>
        <main className="content">{children}</main>
      </div>
    </div>
  );
}
