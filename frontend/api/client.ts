/**
 * 基础 HTTP 客户端 — 对齐 api.md 统一响应结构
 *
 * 统一响应格式：{ code: number, data: T | null, message: string }
 * 所有业务方法在 code !== 0 时抛出 ApiError，调用方只需处理成功数据。
 */

const BASE_URL = "/api/v1";

export class ApiError extends Error {
  constructor(
    public code: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// Token 存储（localStorage）
export const tokenStore = {
  get: () => localStorage.getItem("access_token"),
  set: (token: string) => localStorage.setItem("access_token", token),
  clear: () => localStorage.removeItem("access_token"),
};

type ApiResponse<T> = { code: number; data: T; message: string };

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const token = tokenStore.get();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal,
  });

  const json: ApiResponse<T> = await res.json();

  if (json.code !== 0) {
    throw new ApiError(json.code, json.message);
  }
  return json.data;
}

export const http = {
  get: <T>(path: string, signal?: AbortSignal) =>
    request<T>("GET", path, undefined, signal),
  post: <T>(path: string, body?: unknown) =>
    request<T>("POST", path, body),
  patch: <T>(path: string, body?: unknown) =>
    request<T>("PATCH", path, body),
  delete: <T>(path: string) =>
    request<T>("DELETE", path),
};
