import { http } from "./client";
import type { ISODateString } from "../types";

// ── 用户管理类型 ──────────────────────────────────────────────────────────────

export interface AdminUserItem {
  user_id: string;
  username: string;
  email: string;
  is_admin: boolean;
  is_active: boolean;
  created_at: ISODateString;
  last_login_at: ISODateString | null;
}

export interface ResetPasswordResponse {
  email_sent: boolean;
  target_email: string;
  /** 仅在邮件发送失败时返回，供管理员手动转告 */
  temp_password?: string;
  email_error?: string;
}

// ── 系统 LLM 配置类型 ─────────────────────────────────────────────────────────

export interface CreateSystemLLMRequest {
  provider: string;
  url: string;
  api_key: string;
  default_model: string;
  temperature?: number;
  max_tokens?: number;
}

export interface UpdateSystemLLMRequest {
  api_key?: string;
  default_model?: string;
  temperature?: number;
  max_tokens?: number;
  is_active?: boolean;
}

export interface SystemLLMProvider {
  provider: string;
  url: string;
  default_model: string;
  temperature: number;
  max_tokens: number;
  is_active: boolean;
}

// ── 系统数据库配置类型 ─────────────────────────────────────────────────────────

export interface UpdateSystemDatabaseRequest {
  enabled?: boolean;
  api_key?: string;
  rate_limit?: number;
  endpoint?: string;
}

export interface SystemDatabaseConfig {
  enabled: boolean;
  api_key: string | null;
  rate_limit: number;
  endpoint: string | null;
}

export interface SystemEmailConfig {
  smtp_host?: string | null;
  smtp_port?: number | null;
  sender_email?: string | null;
  sender_password_configured: boolean;
}

export interface UpdateSystemEmailRequest {
  smtp_host?: string;
  smtp_port?: number;
  sender_email?: string;
  sender_password?: string;
}

// ── API 方法 ──────────────────────────────────────────────────────────────────

export const adminApi = {
  // 用户管理
  listUsers: () =>
    http.get<AdminUserItem[]>("/admin/users"),

  setUserStatus: (userId: string, isActive: boolean) =>
    http.patch<{ user_id: string; is_active: boolean }>(
      `/admin/users/${userId}/status`,
      { is_active: isActive },
    ),

  setUserRole: (userId: string, isAdmin: boolean) =>
    http.patch<{ user_id: string; is_admin: boolean }>(
      `/admin/users/${userId}/role`,
      { is_admin: isAdmin },
    ),

  deleteUser: (userId: string) =>
    http.delete<void>(`/admin/users/${userId}`),

  resetPassword: (userId: string) =>
    http.post<ResetPasswordResponse>(`/admin/users/${userId}/reset-password`),

  // 系统级 LLM 配置
  getSystemLLMConfigs: () =>
    http.get<SystemLLMProvider[]>("/admin/system-config/llm"),

  addSystemLLMConfig: (body: CreateSystemLLMRequest) =>
    http.post<SystemLLMProvider>("/admin/system-config/llm", body),

  updateSystemLLMConfig: (provider: string, body: UpdateSystemLLMRequest) =>
    http.patch<SystemLLMProvider>(`/admin/system-config/llm/${provider}`, body),

  deleteSystemLLMConfig: (provider: string) =>
    http.delete<{ message: string }>(`/admin/system-config/llm/${provider}`),

  testSystemLLMConfig: (provider: string) =>
    http.post<{ success: boolean; latency_ms?: number; model_list?: string[]; error?: string }>(
      `/admin/system-config/llm/${provider}/test`,
    ),

  // 系统级数据库配置
  getSystemDatabasesConfig: () =>
    http.get<Record<string, SystemDatabaseConfig>>("/admin/system-config/databases"),

  updateSystemDatabaseConfig: (dbName: string, body: UpdateSystemDatabaseRequest) =>
    http.patch<SystemDatabaseConfig>(`/admin/system-config/databases/${dbName}`, body),

  // 系统级邮件配置
  getSystemEmailConfig: () =>
    http.get<SystemEmailConfig>("/admin/system-config/email"),

  updateSystemEmailConfig: (body: UpdateSystemEmailRequest) =>
    http.patch<SystemEmailConfig>("/admin/system-config/email", body),
};
