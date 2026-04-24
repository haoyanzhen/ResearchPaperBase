/**
 * Playwright 全局准备：创建测试用户，将 JWT 写入 storageState。
 */

import { chromium } from "@playwright/test";

const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:5173";
const API_URL  = process.env.E2E_API_URL  ?? "http://localhost:8000/api/v1";

export default async function globalSetup() {
  // 注册 / 登录测试用户，获取 JWT
  const resp = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: process.env.E2E_USER    ?? "e2e_test_user",
      password: process.env.E2E_PASS    ?? "e2e_test_password",
    }),
  });

  if (!resp.ok) {
    // 若用户不存在则先注册
    await fetch(`${API_URL}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: process.env.E2E_USER ?? "e2e_test_user",
        password: process.env.E2E_PASS ?? "e2e_test_password",
        email:    "e2e@test.local",
      }),
    });
  }

  const loginResp = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: process.env.E2E_USER ?? "e2e_test_user",
      password: process.env.E2E_PASS ?? "e2e_test_password",
    }),
  });
  const { data } = await loginResp.json();
  process.env.E2E_JWT = data?.access_token ?? "";
}
