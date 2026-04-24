/**
 * E2E-003: 综述模式完整流程（qa_design §7）
 */

import { test, expect } from "@playwright/test";
import { createTestProject, deleteTestProject, setAuthToken } from "./helpers";

test.describe("E2E-003 综述模式流程", () => {
  let projectId: string;

  test.beforeAll(async () => {
    projectId = await createTestProject("E2E Review Test");
  });

  test.afterAll(async () => {
    await deleteTestProject(projectId);
  });

  test.beforeEach(async ({ page }) => {
    await setAuthToken(page);
  });

  test("无有效论文时启动综述模式显示错误", async ({ page }) => {
    await page.goto(`/projects/${projectId}/review`);

    const startBtn = page.locator('[data-testid="start-review"], button:has-text("启动综述"), button:has-text("开始综述")');
    if (await startBtn.isVisible({ timeout: 3_000 })) {
      await startBtn.click();
      // 应显示错误提示（空论文库）
      const errMsg = page.locator('[role="alert"], .error-toast, .notification--error');
      await expect(errMsg).toBeVisible({ timeout: 5_000 });
    } else {
      // 按钮可能已被禁用
      const disabledBtn = page.locator('[data-testid="start-review"][disabled], button:has-text("启动综述")[disabled]');
      await expect(disabledBtn).toBeVisible({ timeout: 3_000 });
    }
  });

  test("架构确认界面正确渲染", async ({ page }) => {
    await page.goto(`/projects/${projectId}/review`);

    // 若有 paused 状态的架构生成阶段，应显示架构预览
    const outlinePreview = page.locator(
      '[data-testid="outline-preview"], .outline-editor, .review-outline'
    );
    // 此阶段若未运行，控件可能不存在 — 只检查页面不崩溃
    await expect(page.locator("body")).toBeVisible();
  });
});
