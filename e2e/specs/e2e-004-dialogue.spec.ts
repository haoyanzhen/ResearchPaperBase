/**
 * E2E-004: 深度研究对话（qa_design §7）
 */

import { test, expect } from "@playwright/test";
import { createTestProject, deleteTestProject, setAuthToken } from "./helpers";

test.describe("E2E-004 深度研究对话", () => {
  let projectId: string;

  test.beforeAll(async () => {
    projectId = await createTestProject("E2E Dialogue Test");
  });

  test.afterAll(async () => {
    await deleteTestProject(projectId);
  });

  test.beforeEach(async ({ page }) => {
    await setAuthToken(page);
  });

  test("对话输入框可见并可发送消息", async ({ page }) => {
    // 拦截 LLM 流式响应
    await page.route("**/chat/completions", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: [
          'data: {"choices":[{"delta":{"content":"这是一个测试回复。"},"finish_reason":null}]}',
          'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
          "data: [DONE]",
        ].join("\n\n"),
      });
    });

    await page.goto(`/projects/${projectId}/dialogue`);

    const input = page.locator(
      '[data-testid="chat-input"], textarea[placeholder], .chat-input'
    );
    await expect(input).toBeVisible({ timeout: 10_000 });

    await input.fill("请问这个领域的主要研究方向是什么？");
    await page.keyboard.press("Enter");

    // 应显示用户消息气泡
    const userMsg = page.locator('[data-testid="user-message"], .chat-bubble--user, .message--user');
    await expect(userMsg).toBeVisible({ timeout: 5_000 });
  });

  test("LLM API Key 错误时显示错误提示", async ({ page }) => {
    await page.route("**/chat/completions", async (route) => {
      await route.fulfill({ status: 401, body: '{"error": "invalid api key"}' });
    });

    await page.goto(`/projects/${projectId}/dialogue`);

    const input = page.locator('[data-testid="chat-input"], textarea, .chat-input');
    if (await input.isVisible({ timeout: 5_000 })) {
      await input.fill("测试消息");
      await page.keyboard.press("Enter");

      // 应显示错误提示
      const errIndicator = page.locator(
        '[role="alert"], .error-message, .chat-error, [data-testid="error-toast"]'
      );
      await expect(errIndicator).toBeVisible({ timeout: 10_000 });
    }
  });
});
