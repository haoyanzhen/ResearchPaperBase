/**
 * Inspector & Health API 客户端（qa_design §8）
 *
 * 对应后端端点：
 *   GET /api/v1/health                        — 浅层探针
 *   GET /api/v1/health/db                     — 数据库连通性
 *   GET /api/v1/health/deep                   — 全依赖探针（需认证）
 *   GET /api/v1/health/pipeline/{project_id}  — 流水线快照（需认证）
 *   GET /api/v1/projects/{id}/inspect         — 项目诊断快照（需认证）
 */

import { http } from "./client";

// =============================================================================
// 共用类型
// =============================================================================

export interface CheckResult {
  status: "ok" | "error" | "degraded" | "not_configured";
  latency_ms: number | null;
  message: string | null;
  code: string | null;       // AppErrorCode value，仅 error 时填写
  suggestion: string | null;
  last_success_at: string | null;
}

// =============================================================================
// GET /health
// =============================================================================

export interface ShallowHealthResponse {
  status: string;
  version: string;
  timestamp: string;
}

export async function getHealth(): Promise<ShallowHealthResponse> {
  return http.get<ShallowHealthResponse>("/health");
}

// =============================================================================
// GET /health/db
// =============================================================================

export interface DbHealthResponse {
  status: "ok" | "error";
  checks: {
    postgresql: CheckResult;
  };
}

export async function getDbHealth(): Promise<DbHealthResponse> {
  return http.get<DbHealthResponse>("/health/db");
}

// =============================================================================
// GET /health/deep（需认证）
// =============================================================================

export interface DeepChecks {
  llm_primary: CheckResult;
  llm_fallback: CheckResult;
  arxiv: CheckResult;
  openalex: CheckResult;
  semantic_scholar: CheckResult;
  ads: CheckResult;
  smtp: CheckResult;
}

export interface DeepHealthResponse {
  status: "ok" | "degraded" | "error";
  checks: DeepChecks;
  summary: string;
}

export async function getDeepHealth(
  signal?: AbortSignal,
): Promise<DeepHealthResponse> {
  return http.get<DeepHealthResponse>("/health/deep", signal);
}

// =============================================================================
// GET /health/pipeline/{project_id}（需认证）
// =============================================================================

export interface StageSnapshot {
  stage_record_id: string;
  stage: number;
  mode: string;
  status: string;
  started_at: string;
  elapsed_seconds: number | null;
  result_preview: Record<string, unknown> | null;
  error_preview: ErrorEnvelopePreview | { raw: string } | null;
  pending_user_action: string | null;
}

export interface PipelineHealthResponse {
  project_id: string;
  project_status: string;
  mode: string | null;
  active_stages: StageSnapshot[];
  last_error: Record<string, unknown> | null;
}

export async function getPipelineHealth(
  projectId: string,
): Promise<PipelineHealthResponse> {
  return http.get<PipelineHealthResponse>(`/health/pipeline/${projectId}`);
}

// =============================================================================
// GET /projects/{id}/inspect（需认证）
// =============================================================================

export interface ErrorEnvelopePreview {
  code: string;
  message: string;
  retryable: boolean;
  suggestion: string;
  occurred_at: string;
  detail: Record<string, unknown> | null;
}

export interface StageHistoryItem {
  stage_record_id: string;
  stage: number;
  mode: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  elapsed_seconds: number | null;
  error: ErrorEnvelopePreview | { raw: string } | null;
}

export interface KeywordSummary {
  total: number;
  search_done: number;
  pending: number;
}

export interface PaperSummary {
  total: number;
  valid: number;
  invalid: number;
  downloaded: number;
  analyzed: number;
}

export interface ConfigStatus {
  llm_configured: boolean;
  llm_active_provider: string | null;
  paper_db_sources: string[];
  smtp_configured: boolean;
}

export interface ProjectSnapshot {
  id: string;
  name: string;
  status: string;
  mode?: string;
}

export interface InspectResponse {
  snapshot_at: string;
  project: ProjectSnapshot;
  stage_history: StageHistoryItem[];
  keyword_summary: KeywordSummary;
  paper_summary: PaperSummary;
  config_status: ConfigStatus;
  recommendations: string[];
}

export async function getProjectInspect(
  projectId: string,
  signal?: AbortSignal,
): Promise<InspectResponse> {
  return http.get<InspectResponse>(`/projects/${projectId}/inspect`, signal);
}

// =============================================================================
// 辅助：从 recommendation 字符串解析严重程度
// =============================================================================

export type RecommendationSeverity = "fatal" | "error" | "warning" | "info";

const SEVERITY_PREFIXES: [RecommendationSeverity, string][] = [
  ["fatal",   "[FATAL]"],
  ["error",   "[ERROR]"],
  ["warning", "[WARNING]"],
  ["info",    "[INFO]"],
];

export function parseRecommendationSeverity(
  rec: string,
): RecommendationSeverity {
  for (const [severity, prefix] of SEVERITY_PREFIXES) {
    if (rec.startsWith(prefix)) return severity;
  }
  return "info";
}
