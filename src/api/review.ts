import { http, tokenStore } from "./client";
import type {
  ChapterCitation,
  ChapterStatus,
  ISODateString,
  OutlineStatus,
  ReviewIteration,
  ReviewOutlineContent,
} from "../types";

// ── 综述模式类型（对齐 api.md 第 7 节）───────────────────────────────────────

export interface StartReviewRequest {
  topic_hint?: string;
}

export interface StartReviewResponse {
  task_id: string;
  outline_id: string;
  stage: number;
  status: string;
}

export interface OutlineSummaryItem {
  outline_id: string;
  version: number;
  status: OutlineStatus;
  confirmed_at: ISODateString | null;
  created_at: ISODateString;
}

export interface OutlineDetail extends OutlineSummaryItem {
  topic_expansion: string | null;
  outline: ReviewOutlineContent | null;
}

export interface UpdateOutlineRequest {
  topic_expansion?: string;
  outline?: ReviewOutlineContent;
}

export interface ConfirmOutlineResponse {
  outline_id: string;
  status: OutlineStatus;
  confirmed_at: ISODateString;
  message: string;
}

export interface ChapterSummaryItem {
  chapter_id: string;
  chapter_index: number;
  title: string;
  status: ChapterStatus;
  iteration_count: number;
  completed_at: ISODateString | null;
}

export interface ChapterDetail extends ChapterSummaryItem {
  content: string | null;
  citations: ChapterCitation[] | null;
  review_history: ReviewIteration[] | null;
  created_at: ISODateString;
  updated_at: ISODateString;
}

export interface UpdateChapterRequest {
  content?: string;
  citations?: ChapterCitation[];
}

export interface ReviewChapterResponse {
  chapter_id: string;
  status: ChapterStatus;
  message: string;
}

export interface CompileResponse {
  task_id: string;
  message: string;
}

export type ReviewExportFormat = "markdown" | "pdf" | "docx";

// ── SSE 事件数据类型（综述流） ────────────────────────────────────────────────

export interface SseReviewStageStart {
  stage: number;
  stage_name: string;
}

export interface SseChapterWriting {
  chapter_index: number;
  title: string;
  status: "writing";
}

export interface SseChapterReviewing {
  chapter_index: number;
  iteration: number;
  issues: string[];
}

export interface SseChapterComplete {
  chapter_index: number;
  iteration_count: number;
}

export interface SseReviewTextDelta {
  chapter_index: number;
  delta: string;
}

export interface SseReviewPipelineComplete {
  outline_id: string;
  total_chapters: number;
  compiled: boolean;
}

// ── API 方法 ──────────────────────────────────────────────────────────────────

export const reviewApi = {
  start: (projectId: string, body?: StartReviewRequest) =>
    http.post<StartReviewResponse>(
      `/projects/${projectId}/review/start`,
      body ?? {},
    ),

  getOutlines: (projectId: string) =>
    http.get<OutlineSummaryItem[]>(`/projects/${projectId}/review/outlines`),

  getOutline: (projectId: string, outlineId: string) =>
    http.get<OutlineDetail>(
      `/projects/${projectId}/review/outlines/${outlineId}`,
    ),

  updateOutline: (
    projectId: string,
    outlineId: string,
    body: UpdateOutlineRequest,
  ) =>
    http.patch<OutlineDetail>(
      `/projects/${projectId}/review/outlines/${outlineId}`,
      body,
    ),

  confirmOutline: (projectId: string, outlineId: string) =>
    http.post<ConfirmOutlineResponse>(
      `/projects/${projectId}/review/outlines/${outlineId}/confirm`,
    ),

  getChapters: (projectId: string, outlineId: string) =>
    http.get<ChapterSummaryItem[]>(
      `/projects/${projectId}/review/outlines/${outlineId}/chapters`,
    ),

  getChapter: (projectId: string, outlineId: string, chapterId: string) =>
    http.get<ChapterDetail>(
      `/projects/${projectId}/review/outlines/${outlineId}/chapters/${chapterId}`,
    ),

  updateChapter: (
    projectId: string,
    outlineId: string,
    chapterId: string,
    body: UpdateChapterRequest,
  ) =>
    http.patch<ChapterDetail>(
      `/projects/${projectId}/review/outlines/${outlineId}/chapters/${chapterId}`,
      body,
    ),

  reviewChapter: (
    projectId: string,
    outlineId: string,
    chapterId: string,
  ) =>
    http.post<ReviewChapterResponse>(
      `/projects/${projectId}/review/outlines/${outlineId}/chapters/${chapterId}/review`,
    ),

  compile: (projectId: string, outlineId: string) =>
    http.post<CompileResponse>(
      `/projects/${projectId}/review/outlines/${outlineId}/compile`,
    ),

  /**
   * 导出综述文章（文件流）。
   * 返回原始 fetch Response，调用方通过 response.blob() 获取文件内容。
   */
  exportOutline: (
    projectId: string,
    outlineId: string,
    format: ReviewExportFormat = "markdown",
  ) =>
    fetch(
      `/api/v1/projects/${projectId}/review/outlines/${outlineId}/export?format=${format}`,
      {
        headers: tokenStore.get()
          ? { Authorization: `Bearer ${tokenStore.get()}` }
          : {},
      },
    ),

  /**
   * 返回综述流程进度 SSE 流的 URL（含 token query param）。
   *   new EventSource(reviewApi.streamUrl(projectId))
   */
  streamUrl: (projectId: string): string => {
    const token = tokenStore.get();
    const q = token ? `?token=${encodeURIComponent(token)}` : "";
    return `/api/v1/projects/${projectId}/review/stream${q}`;
  },
};
