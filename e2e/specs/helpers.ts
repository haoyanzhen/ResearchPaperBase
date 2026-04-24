/**
 * E2E 测试辅助函数
 */

import { Page, expect } from "@playwright/test";

const API_URL = process.env.E2E_API_URL ?? "http://localhost:8000/api/v1";

/** 通过 API 创建测试项目，返回 project_id */
export async function createTestProject(name: string): Promise<string> {
  const resp = await fetch(`${API_URL}/projects`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${process.env.E2E_JWT ?? ""}`,
    },
    body: JSON.stringify({ name, description: `E2E test: ${name}` }),
  });
  const { data } = await resp.json();
  return data.project_id;
}

/** 通过 API 删除测试项目 */
export async function deleteTestProject(projectId: string): Promise<void> {
  await fetch(`${API_URL}/projects/${projectId}`, {
    method: "DELETE",
    headers: {
      Authorization: `Bearer ${process.env.E2E_JWT ?? ""}`,
    },
  });
}

/** 设置 localStorage token，模拟已登录状态 */
export async function setAuthToken(page: Page): Promise<void> {
  await page.addInitScript((token: string) => {
    localStorage.setItem("access_token", token);
  }, process.env.E2E_JWT ?? "");
}

/** 等待 SSE 流中出现指定 event_type，超时后 fail */
export async function waitForSseEvent(
  page: Page,
  eventType: string,
  timeoutMs = 30_000,
): Promise<Record<string, unknown>> {
  return page.evaluate(
    async ({ type, timeout }) => {
      return new Promise<Record<string, unknown>>((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error(`SSE timeout: ${type}`)), timeout);
        // 监听从 page 注入的 sse_received 自定义事件
        window.addEventListener(`sse:${type}`, ((e: CustomEvent) => {
          clearTimeout(timer);
          resolve(e.detail);
        }) as EventListener, { once: true });
      });
    },
    { type: eventType, timeout: timeoutMs },
  );
}
