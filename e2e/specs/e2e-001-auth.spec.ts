/**
 * E2E-001: 用户注册与登录（qa_design §7）
 */

import { test, expect } from "@playwright/test";

test.describe("E2E-001 用户注册与登录", () => {
  test("登录成功后跳转到项目列表页", async ({ page }) => {
    await page.goto("/login");
    await page.fill('[name="username"]', process.env.E2E_USER ?? "e2e_test_user");
    await page.fill('[name="password"]', process.env.E2E_PASS ?? "e2e_test_password");
    await page.click('[type="submit"]');

    // 登录后应跳转到 /projects 或 /dashboard
    await expect(page).toHaveURL(/\/(projects|dashboard)/);
  });

  test("错误密码显示错误提示", async ({ page }) => {
    await page.goto("/login");
    await page.fill('[name="username"]', "nonexistent_user_xyz");
    await page.fill('[name="password"]', "wrong_password");
    await page.click('[type="submit"]');

    // 页面上应显示错误信息
    await expect(page.locator('[role="alert"], .error-message, .login-error')).toBeVisible({
      timeout: 5_000,
    });
    // 不应跳转
    await expect(page).toHaveURL(/\/login/);
  });

  test("未认证用户访问受保护页面重定向到登录页", async ({ page }) => {
    await page.goto("/projects");
    await expect(page).toHaveURL(/\/login/);
  });
});
