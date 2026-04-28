import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { HealthPage } from "./HealthPage";
import { renderWithRouter } from "../test/render";

const mocks = vi.hoisted(() => ({
  getHealth: vi.fn(),
  getDbHealth: vi.fn(),
  getDeepHealth: vi.fn(),
}));

vi.mock("../../api/inspect", () => ({
  getHealth: mocks.getHealth,
  getDbHealth: mocks.getDbHealth,
  getDeepHealth: mocks.getDeepHealth,
}));

describe("HealthPage", () => {
  it("renders shallow, db and deep health states", async () => {
    mocks.getHealth.mockResolvedValue({ status: "ok", timestamp: "2026-04-28T00:00:00Z" });
    mocks.getDbHealth.mockResolvedValue({ status: "ok" });
    mocks.getDeepHealth.mockResolvedValue({
      status: "degraded",
      summary: "degraded",
      checks: {
        llm_primary: { status: "ok", message: null, suggestion: null },
        llm_fallback: { status: "ok", message: null, suggestion: null },
        arxiv: { status: "ok", message: null, suggestion: null },
        openalex: { status: "ok", message: null, suggestion: null },
        semantic_scholar: { status: "degraded", message: "延迟较高", suggestion: null },
        ads: { status: "error", message: "超时", suggestion: null },
        smtp: { status: "not_configured", message: null, suggestion: "未配置" },
      },
    });

    renderWithRouter(<HealthPage />);

    expect(await screen.findByText("系统健康检查")).toBeInTheDocument();
    expect(screen.getByText(/时间：2026-04-28T00:00:00Z/)).toBeInTheDocument();
    expect(screen.getByText("semantic_scholar")).toBeInTheDocument();
    expect(screen.getByText("延迟较高")).toBeInTheDocument();
  });

  it("shows fallback message when deep or db health is unavailable", async () => {
    mocks.getHealth.mockResolvedValue({ status: "ok", timestamp: "2026-04-28T00:00:00Z" });
    mocks.getDbHealth.mockRejectedValue(new Error("db down"));
    mocks.getDeepHealth.mockRejectedValue(new Error("deep down"));

    renderWithRouter(<HealthPage />);

    expect(await screen.findByText("数据库探针当前不可用或返回失败。")).toBeInTheDocument();
    expect(screen.getByText("还没有拿到深度探针结果。")).toBeInTheDocument();
  });
});
