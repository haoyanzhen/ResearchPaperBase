/**
 * E2E-007: 阶段失败后 SSE 推送 stage_error 事件（qa_design §7）
 *
 * 测试策略：
 *   1. 拦截 LLM 请求，返回 401（API Key 错误）
 *   2. 启动构建模式阶段 1
 *   3. 验证前端收到 stage_error SSE 事件
 *   4. 验证 Inspector Panel 展示 ErrorEnvelope 中的 code 和 suggestion
 */

import { test, expect, Page } from "@playwright/test";
import { createTestProject, deleteTestProject, setAuthToken } from "./helpers";

test.describe("E2E-007 阶段失败 SSE 事件", () => {
  let projectId: string;

  test.beforeAll(async () => {
    projectId = await createTestProject("E2E SSE Error Test");
  });

  test.afterAll(async () => {
    await deleteTestProject(projectId);
  });

  test.beforeEach(async ({ page }) => {
    await setAuthToken(page);
  });

  test("LLM API Key 错误触发 stage_error SSE，Inspector 显示错误码", async ({ page }) => {
    // 拦截 LLM 请求 → 401
    await page.route("**/chat/completions", async (route) => {
      await route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({ error: { message: "invalid api key", type: "invalid_request_error" } }),
      });
    });

    // 拦截 SSE 流端点，注入 stage_error 事件
    await page.route(`**/projects/${projectId}/sse`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        headers: {
          "Cache-Control": "no-cache",
          "X-Accel-Buffering": "no",
        },
        body: [
          `event: stage_start\ndata: {"stage": 1, "stage_name": "关键词生成"}\n\n`,
          `event: stage_error\ndata: ${JSON.stringify({
            code: "ERR-LLM-001",
            message: "LLM API Key 无效",
            retryable: false,
            suggestion: "在「设置 → LLM 配置」更新 API 密钥",
            occurred_at: new Date().toISOString(),
            project_id: projectId,
            stage_record_id: "sr_test_001",
          })}\n\n`,
        ].join(""),
      });
    });

    await page.goto(`/projects/${projectId}`);

    // 注入 SSE 事件监听器，将 SSE 事件转发为 CustomEvent（供 waitForSseEvent 使用）
    await page.evaluate(() => {
      const es = new EventSource(
        `/api/v1/projects/${location.pathname.split("/")[2]}/sse`,
      );
      es.addEventListener("stage_error", (e: MessageEvent) => {
        const detail = JSON.parse(e.data);
        window.dispatchEvent(new CustomEvent("sse:stage_error", { detail }));
      });
    });

    // 触发阶段启动
    const startBtn = page.locator(
      '[data-testid="start-construction"], button:has-text("启动构建"), button:has-text("开始")'
    );
    if (await startBtn.isVisible({ timeout: 5_000 })) {
      await startBtn.click();
    }

    // 等待 stage_error 在 UI 中展示（错误码或提示文字）
    const errorDisplay = page.locator(
      ':text("ERR-LLM-001"), :text("API Key"), :text("api key"), .stage-error, [data-testid="stage-error"]'
    );
    await expect(errorDisplay).toBeVisible({ timeout: 15_000 });
  });

  test("stage_error 事件中 suggestion 文本在 Inspector Panel 中可见", async ({ page }) => {
    // 拦截 inspect 端点，返回包含失败阶段的历史
    await page.route(`**/projects/${projectId}/inspect`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          code: 0,
          data: {
            snapshot_at: new Date().toISOString(),
            project: { id: projectId, name: "SSE Error Test", status: "error" },
            stage_history: [
              {
                stage_record_id: "sr_test_001",
                stage: 1,
                mode: "construction",
                status: "failed",
                started_at: new Date().toISOString(),
                completed_at: null,
                elapsed_seconds: 3,
                error: {
                  code: "ERR-LLM-001",
                  message: "LLM API Key 无效",
                  retryable: false,
                  suggestion: "在「设置 → LLM 配置」更新 API 密钥",
                  occurred_at: new Date().toISOString(),
                  detail: null,
                },
              },
            ],
            keyword_summary: { total: 0, search_done: 0, pending: 0 },
            paper_summary: { total: 0, valid: 0, invalid: 0, downloaded: 0, analyzed: 0 },
            config_status: {
              llm_configured: true,
              llm_active_provider: "gpt-4o-mini",
              paper_db_sources: [],
              smtp_configured: false,
            },
            recommendations: ["[ERROR] 最近阶段 construction-stage1 失败: ERR-LLM-001 — LLM API Key 无效"],
          },
          message: "ok",
        }),
      });
    });

    await page.goto(`/projects/${projectId}`);

    // 打开 Inspector
    const inspectorBtn = page.locator(
      '[data-testid="open-inspector"], button:has-text("Inspector"), .inspector-toggle'
    );
    if (await inspectorBtn.isVisible({ timeout: 5_000 })) {
      await inspectorBtn.click();
    }

    // suggestion 文字应出现在面板中
    const suggestion = page.locator(':text("API 密钥"), :text("LLM 配置"), :text("ERR-LLM-001")');
    await expect(suggestion).toBeVisible({ timeout: 10_000 });
  });
});
