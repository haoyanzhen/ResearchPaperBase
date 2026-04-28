import { Route } from "react-router-dom";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AppShell } from "./AppShell";
import { renderWithRouter } from "../test/render";

const mocks = vi.hoisted(() => ({
  logout: vi.fn(),
}));

vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: {
      user_id: "u1",
      username: "tester",
      email: "tester@example.com",
      is_admin: true,
      is_active: true,
      created_at: "2026-04-28T00:00:00Z",
    },
    logout: mocks.logout,
  }),
}));

describe("AppShell", () => {
  it("preserves mode-specific navigation when switching project", async () => {
    const user = userEvent.setup();

    renderWithRouter(
      <AppShell
        mode="deep_research"
        selectedNav="dialogues"
        projects={[
          {
            project_id: "p1",
            name: "项目一",
            mode: "construction",
            status: "idle",
            total_papers: 0,
            valid_papers: 0,
            created_at: "2026-04-28T00:00:00Z",
            updated_at: "2026-04-28T00:00:00Z",
          },
          {
            project_id: "p2",
            name: "项目二",
            mode: "deep_research",
            status: "running",
            total_papers: 3,
            valid_papers: 2,
            created_at: "2026-04-28T00:00:00Z",
            updated_at: "2026-04-28T00:00:00Z",
          },
        ]}
        project={{
          project_id: "p1",
          name: "项目一",
          description: null,
          mode: "deep_research",
          status: "idle",
          total_papers: 0,
          valid_papers: 0,
          auto_push: false,
          push_interval: null,
          last_push_at: null,
          next_push_at: null,
          created_at: "2026-04-28T00:00:00Z",
          updated_at: "2026-04-28T00:00:00Z",
        }}
        getProjectHref={(projectId) => `/projects/${projectId}/dialogue`}
        sidebarItems={[{ key: "dialogues", label: "对话列表", icon: <span>D</span> }]}
      >
        <div>当前内容</div>
      </AppShell>,
      {
        route: "/shell",
        path: "/shell",
        extraRoutes: <Route path="/projects/:projectId/dialogue" element={<div>对话页目标</div>} />,
      },
    );

    await user.selectOptions(screen.getByRole("combobox"), "p2");

    expect(screen.getByText("对话页目标")).toBeInTheDocument();
  });

  it("emits mode switch and logout interactions", async () => {
    const user = userEvent.setup();
    const onModeChange = vi.fn();

    renderWithRouter(
      <AppShell
        mode="construction"
        selectedNav="overview"
        projects={[]}
        onModeChange={onModeChange}
        sidebarItems={[{ key: "overview", label: "构建流程", icon: <span>O</span> }]}
      >
        <div>当前内容</div>
      </AppShell>,
    );

    await user.click(screen.getByRole("button", { name: /深度研究/i }));
    await user.click(screen.getByRole("button", { name: "退出" }));

    expect(onModeChange).toHaveBeenCalledWith("deep_research");
    expect(mocks.logout).toHaveBeenCalledTimes(1);
  });
});
