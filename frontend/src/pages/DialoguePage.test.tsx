import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DialoguePage } from "./DialoguePage";
import { renderWithRouter } from "../test/render";

const mocks = vi.hoisted(() => ({
  projectList: vi.fn(),
  getProject: vi.fn(),
  switchMode: vi.fn(),
  dialogueList: vi.fn(),
  createDialogue: vi.fn(),
  getTurns: vi.fn(),
  sendMessage: vi.fn(),
  readSseStream: vi.fn(),
}));

vi.mock("../../api/projects", () => ({
  projectsApi: {
    list: mocks.projectList,
    get: mocks.getProject,
    switchMode: mocks.switchMode,
  },
}));

vi.mock("../../api/dialogues", () => ({
  dialoguesApi: {
    list: mocks.dialogueList,
    create: mocks.createDialogue,
    getTurns: mocks.getTurns,
    sendMessage: mocks.sendMessage,
  },
}));

vi.mock("../utils/format", () => ({
  readSseStream: mocks.readSseStream,
  classNames: (...values: Array<string | false | null | undefined>) => values.filter(Boolean).join(" "),
  formatDate: () => "04-28 08:00",
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

describe("DialoguePage", () => {
  beforeEach(() => {
    mocks.projectList.mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 20,
      items: [
        {
          project_id: "p1",
          name: "项目一",
          mode: "deep_research",
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
      mode: "deep_research",
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
    mocks.dialogueList.mockResolvedValue([]);
    mocks.createDialogue.mockResolvedValue({
      dialogue_id: "d1",
      title: "新研究对话",
      sub_mode: "technical",
      status: "idle",
      turn_count: 0,
      summary: null,
      tags: null,
      created_at: "2026-04-28T00:00:00Z",
      last_active_at: "2026-04-28T00:00:00Z",
    });
    mocks.getTurns.mockResolvedValue([]);
    mocks.sendMessage.mockResolvedValue(new Response("ok", { status: 200 }));
    mocks.readSseStream.mockImplementation(async (_response, handlers) => {
      handlers.onText?.("第一段");
      handlers.onText?.("第二段");
      handlers.onComplete?.();
    });
  });

  it("creates initial dialogue and streams assistant response", async () => {
    const user = userEvent.setup();
    mocks.getTurns
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        {
          turn_id: "t1",
          turn_index: 1,
          user_content: "请总结一下",
          assistant_content: "第一段第二段",
          sub_mode_before: "technical",
          sub_mode_after: "technical",
          referenced_papers: [],
          input_tokens: 10,
          output_tokens: 20,
          created_at: "2026-04-28T00:00:00Z",
        },
      ]);

    renderWithRouter(<DialoguePage />, {
      route: "/projects/p1/dialogue",
      path: "/projects/:projectId/dialogue",
    });

    expect(await screen.findByRole("heading", { name: "新研究对话" })).toBeInTheDocument();

    await user.type(screen.getByTestId("chat-input"), "请总结一下");
    await user.click(screen.getByRole("button", { name: "发送" }));

    await waitFor(() => {
      expect(mocks.sendMessage).toHaveBeenCalledWith("p1", "d1", {
        user_content: "请总结一下",
        sub_mode: "technical",
      });
    });
    expect(await screen.findByText("第一段第二段")).toBeInTheDocument();
  });

  it("keeps streamed assistant text when turn refetch is temporarily stale", async () => {
    const user = userEvent.setup();
    mocks.getTurns.mockResolvedValue([]);

    renderWithRouter(<DialoguePage />, {
      route: "/projects/p1/dialogue",
      path: "/projects/:projectId/dialogue",
    });

    await screen.findByRole("heading", { name: "新研究对话" });
    await user.type(screen.getByTestId("chat-input"), "继续分析");
    await user.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByText("第一段第二段")).toBeInTheDocument();
  });

  it("creates a new dialogue from sidebar action", async () => {
    const user = userEvent.setup();
    mocks.createDialogue
      .mockResolvedValueOnce({
        dialogue_id: "d1",
        title: "新研究对话",
        sub_mode: "technical",
        status: "idle",
        turn_count: 0,
        summary: null,
        tags: null,
        created_at: "2026-04-28T00:00:00Z",
        last_active_at: "2026-04-28T00:00:00Z",
      })
      .mockResolvedValueOnce({
        dialogue_id: "d2",
        title: "新研究对话",
        sub_mode: "technical",
        status: "idle",
        turn_count: 0,
        summary: null,
        tags: null,
        created_at: "2026-04-28T00:00:00Z",
        last_active_at: "2026-04-28T00:00:00Z",
      });

    renderWithRouter(<DialoguePage />, {
      route: "/projects/p1/dialogue",
      path: "/projects/:projectId/dialogue",
    });

    await screen.findByRole("heading", { name: "新研究对话" });
    await user.click(screen.getByRole("button", { name: /新建对话/i }));

    await waitFor(() => {
      expect(mocks.createDialogue).toHaveBeenCalledTimes(2);
    });
  });
});
