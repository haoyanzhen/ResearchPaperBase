import { http } from "./client";

// ── LLM 配置 (FR-002, api.md 第 2 节) ────────────────────────────────────────

export interface LLMConfig {
  provider: string;
  url: string;
  models: string[];
  default_model: string;
  temperature: number;
  max_tokens: number;
  is_active: boolean;
}

export interface CreateLLMConfigRequest {
  provider: string;
  url: string;
  api_key: string;
  default_model: string;
  temperature?: number;
  max_tokens?: number;
}

export interface UpdateLLMConfigRequest {
  api_key?: string;
  default_model?: string;
  temperature?: number;
  max_tokens?: number;
  is_active?: boolean;
}

export interface TestLLMResponse {
  success: boolean;
  latency_ms?: number;
  model_list: string[];
  error?: string;
}

// ── 学术数据库配置 (FR-003) ───────────────────────────────────────────────────

export interface DatabaseConfig {
  enabled: boolean;
  api_key?: string | null;
  rate_limit: number;
  endpoint?: string | null;
}

export type DatabasesConfigResponse = Record<
  "arxiv" | "openalex" | "semantic_scholar" | "ads",
  DatabaseConfig
>;

export interface UpdateDatabaseConfigRequest {
  enabled?: boolean;
  api_key?: string;
  rate_limit?: number;
  endpoint?: string;
}

// ── 邮件配置 (FR-004) ────────────────────────────────────────────────────────

export interface EmailConfig {
  recipients: string[];
  sender_configured: boolean;
}

export interface UpdateEmailConfigRequest {
  recipients?: string[];
}

export interface TestEmailResponse {
  success: boolean;
  message: string;
}

// ── API 方法 ──────────────────────────────────────────────────────────────────

export type DbName = "arxiv" | "openalex" | "semantic_scholar" | "ads";

export const configApi = {
  // LLM
  getLLMConfigs: () => http.get<LLMConfig[]>("/config/llm"),
  addLLMConfig: (body: CreateLLMConfigRequest) =>
    http.post<LLMConfig>("/config/llm", body),
  updateLLMConfig: (provider: string, body: UpdateLLMConfigRequest) =>
    http.patch<LLMConfig>(`/config/llm/${provider}`, body),
  deleteLLMConfig: (provider: string) =>
    http.delete(`/config/llm/${provider}`),
  testLLMConfig: (provider: string) =>
    http.post<TestLLMResponse>(`/config/llm/${provider}/test`),

  // 学术数据库
  getDatabasesConfig: () =>
    http.get<DatabasesConfigResponse>("/config/databases"),
  updateDatabaseConfig: (dbName: DbName, body: UpdateDatabaseConfigRequest) =>
    http.patch<DatabaseConfig>(`/config/databases/${dbName}`, body),

  // 邮件
  getEmailConfig: () => http.get<EmailConfig>("/config/email"),
  updateEmailConfig: (body: UpdateEmailConfigRequest) =>
    http.patch<EmailConfig>("/config/email", body),
  testEmail: () => http.post<TestEmailResponse>("/config/email/test"),
};
