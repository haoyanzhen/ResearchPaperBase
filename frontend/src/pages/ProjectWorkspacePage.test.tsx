import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectWorkspacePage } from "./ProjectWorkspacePage";
import { renderWithRouter } from "../test/render";

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  get: vi.fn(),
  listPapers: vi.fn(),
  getStageRecords: vi.fn(),
  getStatus: vi.fn(),
  updateSchedule: vi.fn(),
  switchMode: vi.fn(),
  start: vi.fn(),
  useProjectEventStream: vi.fn(),
}));

vi.mock("../../api/projects", () => ({
  projectsApi: {
    list: mocks.list,
    get: mocks.get,
    listPapers: mocks.listPapers,
    getStageRecords: mocks.getStageRecords,
    getStatus: mocks.getStatus,
    updateSchedule: mocks.updateSchedule,
    switchMode: mocks.switchMode,
  },
}));

vi.mock("../../api/construction", () => ({
  constructionApi: {
    start: mocks.start,
  },
}));

vi.mock("../hooks/useProjectEventStream", () => ({
  useProjectEventStream: mocks.useProjectEventStream,
}));

vi.mock("../../components/InspectorPanel", () => ({
  InspectorPanel: ({ onClose }: { onClose?: () => void }) => (
    <div>
      <span>Inspector Mock</span>
      <button onClick={onClose}>Close Inspector</button>
    </div>
  ),
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

describe("ProjectWorkspacePage", () => {
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
          total_papers: 10,
          valid_papers: 6,
          created_at: "2026-04-28T00:00:00Z",
          updated_at: "2026-04-28T00:00:00Z",
        },
      ],
    });
    mocks.get.mockResolvedValue({
      project_id: "p1",
      name: "项目一",
      description: "描述",
      mode: "construction",
      status: "idle",
      total_papers: 10,
      valid_papers: 6,
      auto_push: false,
      push_interval: 7,
      last_push_at: null,
      next_push_at: null,
      created_at: "2026-04-28T00:00:00Z",
      updated_at: "2026-04-28T00:00:00Z",
    });
    mocks.listPapers.mockResolvedValue({
      total: 1,
      items: [
        {
          paper_id: "paper-1",
          title: "Paper 1",
          authors: ["A", "B"],
          venue: "Nature",
          total_score: 9,
          is_valid: true,
        },
      ],
    });
    mocks.getStageRecords.mockResolvedValue([
      {
        record_id: "r1",
        mode: "construction",
        stage: 2,
        status: "completed",
        started_at: "2026-04-28T00:00:00Z",
        completed_at: null,
        error: null,
      },
    ]);
    mocks.getStatus.mockResolvedValue({ current_stage: 2, stage_status: "running", status: "running" });
    mocks.updateSchedule.mockResolvedValue(undefined);
    mocks.start.mockResolvedValue({ message: "已启动" });
    mocks.switchMode.mockResolvedValue(undefined);
    mocks.useProjectEventStream.mockReturnValue(null);
  });

  it("loads project data and handles core interactions", async () => {
    const user = userEvent.setup();

    renderWithRouter(<ProjectWorkspacePage />, {
      route: "/projects/p1",
      path: "/projects/:projectId",
    });

    expect(await screen.findByRole("heading", { name: "项目一" })).toBeInTheDocument();
    expect(screen.getByText("Paper 1")).toBeInTheDocument();
    expect(screen.getByText("Inspector Mock")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "开始构建" }));
    await waitFor(() => {
      expect(mocks.start).toHaveBeenCalledWith("p1", {});
    });

    await user.selectOptions(screen.getByDisplayValue("关闭"), "on");
    await waitFor(() => {
      expect(mocks.updateSchedule).toHaveBeenCalledWith("p1", {
        auto_push: true,
        push_interval: 7,
      });
    });

    await user.click(screen.getByTestId("open-inspector"));
    expect(screen.queryByText("Inspector Mock")).not.toBeInTheDocument();
  });

  it("renders stage error from event stream", async () => {
    mocks.useProjectEventStream.mockReturnValue({
      event: "stage_error",
      payload: { message: "阶段执行失败" },
    });

    renderWithRouter(<ProjectWorkspacePage />, {
      route: "/projects/p1",
      path: "/projects/:projectId",
    });

    expect(await screen.findByTestId("stage-error")).toHaveTextContent("阶段执行失败");
  });
});
