import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ReviewPage } from "./ReviewPage";
import { renderWithRouter } from "../test/render";

const mocks = vi.hoisted(() => ({
  projectList: vi.fn(),
  getProject: vi.fn(),
  switchMode: vi.fn(),
  getOutlines: vi.fn(),
  getOutline: vi.fn(),
  getChapters: vi.fn(),
  getChapter: vi.fn(),
  getStatus: vi.fn(),
  start: vi.fn(),
}));

vi.mock("../../api/projects", () => ({
  projectsApi: {
    list: mocks.projectList,
    get: mocks.getProject,
    switchMode: mocks.switchMode,
  },
}));

vi.mock("../../api/review", () => ({
  reviewApi: {
    getOutlines: mocks.getOutlines,
    getOutline: mocks.getOutline,
    getChapters: mocks.getChapters,
    getChapter: mocks.getChapter,
    getStatus: mocks.getStatus,
    start: mocks.start,
  },
}));

vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: {
      user_id: "u1",
      username: "tester",
      email: "tester@example.com",
      is_admin: false,
      is_active: true,
      created_at: "2026-04-28T00:00:00Z",
    },
    logout: vi.fn(),
  }),
}));

describe("ReviewPage", () => {
  beforeEach(() => {
    mocks.projectList.mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 20,
      items: [
        {
          project_id: "p1",
          name: "项目一",
          mode: "review",
          status: "idle",
          total_papers: 10,
          valid_papers: 6,
          created_at: "2026-04-28T00:00:00Z",
          updated_at: "2026-04-28T00:00:00Z",
        },
      ],
    });
    mocks.getProject.mockResolvedValue({
      project_id: "p1",
      name: "项目一",
      description: "描述",
      mode: "review",
      status: "idle",
      total_papers: 10,
      valid_papers: 6,
      auto_push: false,
      push_interval: null,
      last_push_at: null,
      next_push_at: null,
      created_at: "2026-04-28T00:00:00Z",
      updated_at: "2026-04-28T00:00:00Z",
    });
    mocks.getOutlines.mockResolvedValue([{ outline_id: "o1", version: 1, status: "draft", confirmed_at: null, created_at: "2026-04-28T00:00:00Z" }]);
    mocks.getOutline.mockResolvedValue({
      outline_id: "o1",
      version: 1,
      status: "draft",
      confirmed_at: null,
      created_at: "2026-04-28T00:00:00Z",
      topic_expansion: "扩写说明",
      outline: {
        title: "综述标题",
        abstract_hint: "",
        sections: [{ index: 1, title: "背景", type: "background" }],
      },
    });
    mocks.getChapters.mockResolvedValue([{ chapter_id: "c1", chapter_index: 1, title: "背景", status: "draft", iteration_count: 0, completed_at: null }]);
    mocks.getChapter.mockResolvedValue({
      chapter_id: "c1",
      chapter_index: 1,
      title: "背景",
      status: "draft",
      iteration_count: 0,
      completed_at: null,
      content: "章节正文",
      citations: [],
      review_history: [],
      created_at: "2026-04-28T00:00:00Z",
      updated_at: "2026-04-28T00:00:00Z",
    });
    mocks.getStatus.mockResolvedValue(null);
    mocks.start.mockResolvedValue({ stage: 1 });
  });

  it("loads outline and chapter content", async () => {
    renderWithRouter(<ReviewPage />, {
      route: "/projects/p1/review",
      path: "/projects/:projectId/review",
    });

    expect(await screen.findByText("综述标题")).toBeInTheDocument();
    expect(screen.getByText("背景")).toBeInTheDocument();
    expect(screen.getByDisplayValue("章节正文")).toBeInTheDocument();
  });

  it("starts review flow from action button", async () => {
    const user = userEvent.setup();

    renderWithRouter(<ReviewPage />, {
      route: "/projects/p1/review",
      path: "/projects/:projectId/review",
    });

    await screen.findByText("综述标题");
    await user.click(screen.getByRole("button", { name: /启动综述/i }));

    await waitFor(() => {
      expect(mocks.start).toHaveBeenCalledWith("p1", {});
    });
  });
});
