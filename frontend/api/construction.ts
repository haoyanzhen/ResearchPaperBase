import { http, tokenStore } from "./client";
import type { ISODateString, PaperSource } from "../types";

// ── 构建模式类型（对齐 api.md 第 4 节）────────────────────────────────────────

export interface StartConstructionRequest {
  databases?: PaperSource[];
  score_threshold?: number;
}

export interface StartConstructionResponse {
  task_id: string;
  project_id: string;
  stage: number;
  status: string;
  message: string;
}

export interface ConstructionStatus {
  current_stage: number;
  stage_name: string;
  status: string;
  stage_result: Record<string, unknown> | null;
  started_at: ISODateString;
}

export interface KeywordItem {
  keyword_id: string;
  search_word: string;
  boolean_expressions: {
    arxiv?: string;
    openalex?: string;
    semantic_scholar?: string;
    ads?: string;
  } | null;
  is_selected: boolean;
  searched_papers_total: number;
}

export interface KeywordUpdate {
  keyword_id?: string;      // 有 id = 更新已有；无 id = 新增
  search_word: string;
  is_selected?: boolean;
}

export interface UpdateKeywordsRequest {
  keywords: KeywordUpdate[];
}

export interface StageAction {
  action: "confirm" | "retry" | "skip";
  modifications?: Record<string, unknown>;
}

export interface StageActionResponse {
  stage: number;
  action: string;
  next_stage: number | null;
  status: string;
  message: string;
}

// ── SSE 事件数据类型 ───────────────────────────────────────────────────────────

export interface SseStageStart {
  stage: number;
  stage_name: string;
  started_at: ISODateString;
}

export interface SseStageProgress {
  stage: number;
  progress: number;
  detail: string;
}

export interface SseStagePause {
  stage: number;
  status: "paused";
  result: Record<string, unknown>;
}

export interface SseStageError {
  stage: number;
  error: string;
  retryable: boolean;
}

export interface SsePipelineComplete {
  total_papers: number;
  valid_papers: number;
  email_sent: boolean;
}

// ── API 方法 ──────────────────────────────────────────────────────────────────

export const constructionApi = {
  start: (projectId: string, body?: StartConstructionRequest) =>
    http.post<StartConstructionResponse>(
      `/projects/${projectId}/construction/start`,
      body ?? {},
    ),

  getStatus: (projectId: string) =>
    http.get<ConstructionStatus>(`/projects/${projectId}/construction/status`),

  getKeywords: (projectId: string) =>
    http.get<KeywordItem[]>(`/projects/${projectId}/construction/keywords`),

  updateKeywords: (projectId: string, body: UpdateKeywordsRequest) =>
    http.patch<KeywordItem[]>(
      `/projects/${projectId}/construction/keywords`,
      body,
    ),

  stageAction: (projectId: string, stage: number, body: StageAction) =>
    http.post<StageActionResponse>(
      `/projects/${projectId}/construction/stages/${stage}/action`,
      body,
    ),

  /**
   * 返回构建进度 SSE 流的 URL（含 token query param）。
   * 调用方自行创建 EventSource：
   *   new EventSource(constructionApi.streamUrl(projectId))
   */
  streamUrl: (projectId: string): string => {
    const token = tokenStore.get();
    const q = token ? `?token=${encodeURIComponent(token)}` : "";
    return `/api/v1/projects/${projectId}/construction/stream${q}`;
  },
};
