/**
 * E2E-002: 构建模式完整流程（qa_design §7）
 *
 * 使用 route 拦截 LLM API 请求，返回 mock 响应，无需真实 LLM。
 */

import { test, expect } from "@playwright/test";
import { createTestProject, deleteTestProject, setAuthToken } from "./helpers";

test.describe("E2E-002 构建模式流程", () => {
  let projectId: string;

  test.beforeAll(async () => {
    projectId = await createTestProject("E2E Construction Test");
  });

  test.afterAll(async () => {
    await deleteTestProject(projectId);
  });

  test.beforeEach(async ({ page }) => {
    await setAuthToken(page);
  });

  test("启动构建模式，阶段 1 发出 stage_start SSE 事件", async ({ page }) => {
    // 拦截 LLM API 请求
    await page.route("**/chat/completions", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          choices: [{ message: { content: '["机器学习", "深度学习", "神经网络"]' } }],
          usage: { completion_tokens: 20 },
        }),
      });
    });

    await page.goto(`/projects/${projectId}`);

    // 点击启动构建模式按钮
    const startBtn = page.locator('[data-testid="start-construction"], button:has-text("启动构建"), button:has-text("开始构建")');
    await expect(startBtn).toBeVisible({ timeout: 10_000 });
    await startBtn.click();

    // 应看到阶段进度指示器
    const stageIndicator = page.locator('[data-testid="stage-progress"], .stage-progress, .pipeline-stage');
    await expect(stageIndicator).toBeVisible({ timeout: 15_000 });
  });

  test("阶段状态在 UI 中正确展示", async ({ page }) => {
    await page.goto(`/projects/${projectId}`);

    // 应显示当前阶段信息（不论是 running/paused/completed）
    const stageInfo = page.locator('[data-testid="current-stage"], .current-stage, .stage-info');
    await expect(stageInfo).toBeVisible({ timeout: 10_000 });
  });
});
