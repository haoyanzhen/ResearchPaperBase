/**
 * E2E-005: Inspector Panel 诊断面板展示（qa_design §7）
 */

import { test, expect } from "@playwright/test";
import { createTestProject, deleteTestProject, setAuthToken } from "./helpers";

test.describe("E2E-005 Inspector Panel", () => {
  let projectId: string;

  test.beforeAll(async () => {
    projectId = await createTestProject("E2E Inspector Test");
  });

  test.afterAll(async () => {
    await deleteTestProject(projectId);
  });

  test.beforeEach(async ({ page }) => {
    await setAuthToken(page);
  });

  test("LLM 未配置时 Inspector 显示 FATAL 建议", async ({ page }) => {
    // 拦截 /inspect 端点，注入未配置 LLM 的响应
    await page.route(`**/projects/${projectId}/inspect`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          code: 0,
          data: {
            snapshot_at: new Date().toISOString(),
            project: { id: projectId, name: "Test", status: "idle" },
            stage_history: [],
            keyword_summary: { total: 0, search_done: 0, pending: 0 },
            paper_summary: { total: 0, valid: 0, invalid: 0, downloaded: 0, analyzed: 0 },
            config_status: {
              llm_configured: false,
              llm_active_provider: null,
              paper_db_sources: [],
              smtp_configured: false,
            },
            recommendations: [
              "[FATAL] LLM 未配置，所有 Agent 任务将立即失败，请在「设置 → LLM 配置」添加模型",
            ],
          },
          message: "ok",
        }),
      });
    });

    await page.goto(`/projects/${projectId}`);

    // 打开 Inspector Panel
    const inspectorBtn = page.locator(
      '[data-testid="open-inspector"], button:has-text("Inspector"), .inspector-toggle'
    );
    if (await inspectorBtn.isVisible({ timeout: 5_000 })) {
      await inspectorBtn.click();
    }

    // Inspector Panel 或内联诊断区域应显示 FATAL 建议
    const fatalRec = page.locator(".inspector-rec--fatal, [data-severity='fatal'], :text('LLM 未配置')");
    await expect(fatalRec).toBeVisible({ timeout: 10_000 });
  });

  test("Inspector Panel 包含论文库统计", async ({ page }) => {
    await page.route(`**/projects/${projectId}/inspect`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          code: 0,
          data: {
            snapshot_at: new Date().toISOString(),
            project: { id: projectId, name: "Test", status: "idle" },
            stage_history: [],
            keyword_summary: { total: 5, search_done: 3, pending: 2 },
            paper_summary: { total: 42, valid: 38, invalid: 4, downloaded: 30, analyzed: 25 },
            config_status: {
              llm_configured: true,
              llm_active_provider: "gpt-4o-mini",
              paper_db_sources: ["arxiv", "openalex"],
              smtp_configured: false,
            },
            recommendations: [],
          },
          message: "ok",
        }),
      });
    });

    await page.goto(`/projects/${projectId}`);

    const inspectorBtn = page.locator(
      '[data-testid="open-inspector"], button:has-text("Inspector"), .inspector-toggle'
    );
    if (await inspectorBtn.isVisible({ timeout: 5_000 })) {
      await inspectorBtn.click();
    }

    // 应显示论文总数
    const paperStats = page.locator(":text('42'), [data-testid='paper-total']");
    await expect(paperStats).toBeVisible({ timeout: 10_000 });
  });
});
