import { Route } from "react-router-dom";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectsPage } from "./ProjectsPage";
import { renderWithRouter } from "../test/render";

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  create: vi.fn(),
  remove: vi.fn(),
  logout: vi.fn(),
}));

vi.mock("../../api/projects", () => ({
  projectsApi: {
    list: mocks.list,
    create: mocks.create,
    delete: mocks.remove,
  },
}));

vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { user_id: "u1", username: "tester" },
    logout: mocks.logout,
  }),
}));

describe("ProjectsPage", () => {
  beforeEach(() => {
    mocks.list.mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 20,
      items: [
        {
          project_id: "p1",
          name: "项目一",
          mode: "construction",
          status: "idle",
          total_papers: 2,
          valid_papers: 1,
          created_at: "2026-04-28T00:00:00Z",
          updated_at: "2026-04-28T00:00:00Z",
        },
      ],
    });
  });

  it("loads project list and creates a project via modal", async () => {
    const user = userEvent.setup();
    mocks.create.mockResolvedValue({ project_id: "p2" });

    renderWithRouter(<ProjectsPage />, {
      route: "/projects",
      path: "/projects",
      extraRoutes: <Route path="/projects/:projectId" element={<div>项目工作台</div>} />,
    });

    expect(await screen.findByText("项目一")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /新建项目/i }));
    await user.type(screen.getByLabelText("项目名称"), "新项目");
    await user.type(screen.getByLabelText("项目描述"), "说明");
    await user.click(screen.getByRole("button", { name: "创建项目" }));

    await waitFor(() => {
      expect(mocks.create).toHaveBeenCalledWith({ name: "新项目", description: "说明" });
    });
    expect(await screen.findByText("项目工作台")).toBeInTheDocument();
  });

  it("deletes project after confirmation", async () => {
    const user = userEvent.setup();
    mocks.remove.mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderWithRouter(<ProjectsPage />, { route: "/projects", path: "/projects" });

    await screen.findByText("项目一");
    await user.click(screen.getByRole("button", { name: "删除" }));

    await waitFor(() => {
      expect(mocks.remove).toHaveBeenCalledWith("p1");
    });
  });
});
