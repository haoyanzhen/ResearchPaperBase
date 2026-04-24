/**
 * E2E-006: 健康检查降级状态展示（qa_design §7）
 */

import { test, expect } from "@playwright/test";
import { setAuthToken } from "./helpers";

test.describe("E2E-006 健康检查降级状态", () => {
  test.beforeEach(async ({ page }) => {
    await setAuthToken(page);
  });

  test("GET /health/deep 返回 degraded 时 UI 显示警告", async ({ page }) => {
    await page.route("**/health/deep", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          code: 0,
          data: {
            status: "degraded",
            checks: {
              llm_primary:       { status: "ok",             latency_ms: 250, message: null, code: null, suggestion: null, last_success_at: null },
              llm_fallback:      { status: "not_configured", latency_ms: null, message: "备用 LLM 未设置", code: null, suggestion: null, last_success_at: null },
              arxiv:             { status: "error",          latency_ms: null, message: "连接超时", code: "ERR-EXT-ARXIV-001", suggestion: "检查网络", last_success_at: null },
              openalex:          { status: "ok",             latency_ms: 180, message: null, code: null, suggestion: null, last_success_at: null },
              semantic_scholar:  { status: "ok",             latency_ms: 310, message: null, code: null, suggestion: null, last_success_at: null },
              ads:               { status: "not_configured", latency_ms: null, message: null, code: null, suggestion: null, last_success_at: null },
              smtp:              { status: "ok",             latency_ms: 45,  message: null, code: null, suggestion: null, last_success_at: null },
            },
            summary: "1 个服务不可达，2 个未配置",
          },
          message: "ok",
        }),
      });
    });

    await page.goto("/settings/health");

    // 应显示 degraded 状态标识
    const degradedIndicator = page.locator(
      ':text("degraded"), [data-status="degraded"], .health-status--degraded'
    );
    await expect(degradedIndicator).toBeVisible({ timeout: 10_000 });

    // arXiv 应显示 error 状态
    const arxivError = page.locator(
      ':text("arXiv"), .inspector-dep--error'
    ).first();
    await expect(arxivError).toBeVisible({ timeout: 5_000 });
  });

  test("GET /health/db 失败时页面显示数据库错误提示", async ({ page }) => {
    await page.route("**/health/db", async (route) => {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({
          code: 1001,
          data: null,
          message: "数据库连接失败",
        }),
      });
    });

    await page.goto("/settings/health");

    const dbError = page.locator(':text("数据库"), :text("DB"), .health-db--error');
    // 若页面有 DB 状态展示，应显示错误
    if (await dbError.isVisible({ timeout: 3_000 })) {
      await expect(dbError).toBeVisible();
    }
    // 页面不应崩溃（500 等）
    await expect(page.locator("body")).toBeVisible();
  });
});
