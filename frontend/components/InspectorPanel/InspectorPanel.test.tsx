import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { InspectorPanel } from "./InspectorPanel";
import { renderWithRouter } from "../../src/test/render";

const mocks = vi.hoisted(() => ({
  getProjectInspect: vi.fn(),
  getPipelineHealth: vi.fn(),
  getDeepHealth: vi.fn(),
  parseRecommendationSeverity: vi.fn((value: string) => {
    if (value.startsWith("[FATAL]")) return "fatal";
    return "info";
  }),
}));

vi.mock("../../api/inspect", () => ({
  getProjectInspect: mocks.getProjectInspect,
  getPipelineHealth: mocks.getPipelineHealth,
  getDeepHealth: mocks.getDeepHealth,
  parseRecommendationSeverity: mocks.parseRecommendationSeverity,
}));

describe("InspectorPanel", () => {
  it("renders summary, recommendations and active stages", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();

    mocks.getProjectInspect.mockResolvedValue({
      snapshot_at: "2026-04-28T00:00:00Z",
      project: { id: "p1", name: "项目", status: "running", mode: "construction" },
      stage_history: [
        {
          stage_record_id: "r1",
          stage: 3,
          mode: "construction",
          status: "failed",
          started_at: "2026-04-28T00:00:00Z",
          completed_at: null,
          elapsed_seconds: 25,
          error: { code: "ERR-1", message: "评分失败", retryable: true, suggestion: "", occurred_at: "", detail: null },
        },
      ],
      keyword_summary: { total: 2, search_done: 1, pending: 1 },
      paper_summary: { total: 10, valid: 6, invalid: 4, downloaded: 5, analyzed: 3 },
      config_status: {
        llm_configured: true,
        llm_active_provider: "openai",
        paper_db_sources: ["arxiv", "openalex"],
        smtp_configured: false,
      },
      recommendations: ["[FATAL] LLM 未配置完整"],
    });
    mocks.getPipelineHealth.mockResolvedValue({
      project_id: "p1",
      project_status: "running",
      mode: "construction",
      last_error: null,
      active_stages: [
        {
          stage_record_id: "a1",
          stage: 2,
          mode: "construction",
          status: "running",
          started_at: "2026-04-28T00:00:00Z",
          elapsed_seconds: 45,
          result_preview: null,
          error_preview: null,
          pending_user_action: null,
        },
      ],
    });
    mocks.getDeepHealth.mockResolvedValue({
      status: "degraded",
      summary: "degraded",
      checks: {
        llm_primary: { status: "ok", latency_ms: 11, message: null, code: null, suggestion: null, last_success_at: null },
        llm_fallback: { status: "ok", latency_ms: 12, message: null, code: null, suggestion: null, last_success_at: null },
        arxiv: { status: "ok", latency_ms: 13, message: null, code: null, suggestion: null, last_success_at: null },
        openalex: { status: "ok", latency_ms: 14, message: null, code: null, suggestion: null, last_success_at: null },
        semantic_scholar: { status: "degraded", latency_ms: 15, message: "慢", code: null, suggestion: null, last_success_at: null },
        ads: { status: "error", latency_ms: null, message: "超时", code: null, suggestion: null, last_success_at: null },
        smtp: { status: "not_configured", latency_ms: null, message: null, code: null, suggestion: "缺少配置", last_success_at: null },
      },
    });

    renderWithRouter(<InspectorPanel projectId="p1" onClose={onClose} />);

    expect(await screen.findByText("诊断建议")).toBeInTheDocument();
    expect(screen.getByText("LLM 未配置完整")).toBeInTheDocument();
    expect(screen.getByTestId("paper-total")).toHaveTextContent("10");
    expect(screen.getByText("openai")).toBeInTheDocument();
    expect(screen.getByText("活跃阶段")).toBeInTheDocument();
    expect(screen.getByText("外部依赖")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "关闭" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("supports manual refresh and error rendering", async () => {
    const user = userEvent.setup();

    mocks.getProjectInspect.mockRejectedValue(new Error("诊断失败"));
    mocks.getPipelineHealth.mockResolvedValue({ active_stages: [] });
    mocks.getDeepHealth.mockResolvedValue(null);

    renderWithRouter(<InspectorPanel projectId="p1" />);

    expect(await screen.findByRole("alert")).toHaveTextContent("加载失败：诊断失败");

    mocks.getProjectInspect.mockResolvedValueOnce({
      snapshot_at: "2026-04-28T00:00:00Z",
      project: { id: "p1", name: "项目", status: "idle" },
      stage_history: [],
      keyword_summary: { total: 0, search_done: 0, pending: 0 },
      paper_summary: { total: 0, valid: 0, invalid: 0, downloaded: 0, analyzed: 0 },
      config_status: { llm_configured: false, llm_active_provider: null, paper_db_sources: [], smtp_configured: false },
      recommendations: [],
    });

    await user.click(screen.getByRole("button", { name: "刷新" }));

    await waitFor(() => {
      expect(mocks.getProjectInspect).toHaveBeenCalledTimes(2);
    });
  });
});
