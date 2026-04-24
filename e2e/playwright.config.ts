/**
 * Playwright E2E 测试配置（qa_design §7）
 *
 * 覆盖场景（FR-*）：
 *   E2E-001 用户注册与登录
 *   E2E-002 构建模式完整流程（模拟 LLM）
 *   E2E-003 综述模式完整流程（模拟 LLM）
 *   E2E-004 深度研究对话
 *   E2E-005 Inspector Panel 显示 LLM 未配置 fatal 建议
 *   E2E-006 健康检查面板降级状态展示
 *   E2E-007 阶段失败后 SSE 推送 stage_error 事件
 */

import { defineConfig, devices } from "@playwright/test";

const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:5173";

export default defineConfig({
  testDir: "./specs",
  fullyParallel: false,         // E2E 测试有状态，串行执行防冲突
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: [
    ["html", { outputFolder: "../test-reports/e2e", open: "never" }],
    ["junit", { outputFile: "../test-reports/e2e/results.xml" }],
    ["list"],
  ],
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    // 响应超时：E2E 场景包含 SSE 流，适当延长
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  // 每个测试前后的全局钩子
  globalSetup: "./global-setup.ts",
  globalTeardown: "./global-teardown.ts",
});
