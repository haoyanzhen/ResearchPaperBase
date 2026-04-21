import { http } from "./client";
import type {
  ExportFilters,
  ExportResult,
  ISODateString,
  PaperWithRelation,
  ProjectMode,
  ProjectStatus,
} from "../types";

// ── Project 类型（对齐 api.md 第 3~5 节）─────────────────────────────────────

export interface ProjectSummary {
  project_id: string;
  name: string;
  mode: ProjectMode;
  status: ProjectStatus;
  total_papers: number;
  valid_papers: number;
  created_at: ISODateString;
  updated_at: ISODateString;
}

export interface ProjectDetail extends ProjectSummary {
  description: string | null;
  auto_push: boolean;
  push_interval: number | null;
  last_push_at: ISODateString | null;
  next_push_at: ISODateString | null;
}

export interface ProjectListResponse {
  total: number;
  page: number;
  page_size: number;
  items: ProjectSummary[];
}

export interface CreateProjectRequest {
  name: string;
  description?: string;
}

export interface UpdateProjectRequest {
  name?: string;
  description?: string;
}

export interface ModeSwitchRequest {
  target_mode: ProjectMode;
  reason?: string;
  running_task_action?: "stay" | "leave_and_cancel";
}

export interface ModeSwitchResponse {
  project_id: string;
  previous_mode: ProjectMode;
  current_mode: ProjectMode;
  switched_at: ISODateString;
}

export interface PaperListResponse {
  total: number;
  items: PaperItem[];
}

export interface PaperItem {
  paper_id: string;
  title: string;
  authors: string[] | null;
  pub_date: string | null;
  venue: string | null;
  abstract: string | null;
  total_score: number | null;
  reference_score: number | null;
  technical_score: number | null;
  is_valid: boolean;
  push_status: boolean;
  download_status: string;
  ai_analysis: Record<string, unknown> | null;
}

export interface PaperListParams {
  is_valid?: boolean;
  push_status?: boolean;
  keyword?: string;
  order_by?: "total_score" | "pub_date" | "created_at";
  page?: number;
  page_size?: number;
}

export interface AddPaperRequest {
  doi?: string;
  arxiv_id?: string;
  pdf_file?: string;  // base64
}

export interface AddPaperResponse {
  paper_id: string;
  title: string;
  status: string;
  message: string;
}

export interface UpdatePaperScoreRequest {
  reference_score: number;
  technical_score: number;
  scoring_reason?: string;
}

export interface PaperScoreResponse {
  paper_id: string;
  reference_score: number;
  technical_score: number;
  total_score: number;
  is_valid: boolean;
  scoring_reason: string | null;
}

export interface ScheduleConfig {
  auto_push: boolean;
  push_interval: number | null;
  next_push_at: ISODateString | null;
}

export interface ExportTaskResponse {
  task_id: string;
  status: string;
  message: string;
}

export interface RecommendationItem {
  recommendation_id: string;
  user_id: string;
  username: string;
  content_type: string;
  title: string;
  content: string;
  tags: string[] | null;
  contact_info: string | null;
  view_count: number;
  like_count: number;
  created_at: ISODateString;
}

export interface CreateRecommendationRequest {
  content_type: string;
  title: string;
  content: string;
  tags?: string[];
  contact_info?: string;
  dialogue_id?: string;
}

// ── 辅助：构建 query string ───────────────────────────────────────────────────

function qs(params: Record<string, unknown>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null) p.append(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

// ── API 方法 ──────────────────────────────────────────────────────────────────

export const projectsApi = {
  // Project CRUD
  list: (params?: { status?: string; mode?: string; page?: number; page_size?: number }) =>
    http.get<ProjectListResponse>(`/projects${qs(params ?? {})}`),

  create: (body: CreateProjectRequest) =>
    http.post<ProjectDetail>("/projects", body),

  get: (projectId: string) =>
    http.get<ProjectDetail>(`/projects/${projectId}`),

  update: (projectId: string, body: UpdateProjectRequest) =>
    http.patch<ProjectDetail>(`/projects/${projectId}`, body),

  delete: (projectId: string) =>
    http.delete(`/projects/${projectId}`),

  // FR-005 模式切换
  switchMode: (projectId: string, body: ModeSwitchRequest) =>
    http.post<ModeSwitchResponse>(`/projects/${projectId}/mode`, body),

  // FR-006 检索历史
  getStageRecords: (projectId: string, mode?: string) =>
    http.get(`/projects/${projectId}/stage-records${qs({ mode })}`),

  // FR-007 论文库
  listPapers: (projectId: string, params?: PaperListParams) =>
    http.get<PaperListResponse>(`/projects/${projectId}/papers${qs(params ?? {})}`),

  addPaper: (projectId: string, body: AddPaperRequest) =>
    http.post<AddPaperResponse>(`/projects/${projectId}/papers`, body),

  getPaper: (projectId: string, paperId: string) =>
    http.get<PaperWithRelation>(`/projects/${projectId}/papers/${paperId}`),

  updatePaperScore: (projectId: string, paperId: string, body: UpdatePaperScoreRequest) =>
    http.patch<PaperScoreResponse>(
      `/projects/${projectId}/papers/${paperId}/score`,
      body,
    ),

  removePaper: (projectId: string, paperId: string) =>
    http.delete(`/projects/${projectId}/papers/${paperId}`),

  // FR-008 任务管理
  getStatus: (projectId: string) =>
    http.get(`/projects/${projectId}/status`),

  cancelTask: (projectId: string) =>
    http.post(`/projects/${projectId}/cancel`),

  // FR-009 数据导出
  exportData: (
    projectId: string,
    exportType: "excel" | "pdf_zip",
    filters?: { is_valid?: boolean; push_status?: boolean },
  ) =>
    http.post<ExportTaskResponse>(`/projects/${projectId}/export`, {
      export_type: exportType,
      ...filters,
    }),

  // FR-010 定时任务
  getSchedule: (projectId: string) =>
    http.get<ScheduleConfig>(`/projects/${projectId}/schedule`),

  updateSchedule: (
    projectId: string,
    body: { auto_push: boolean; push_interval?: number },
  ) => http.patch<ScheduleConfig>(`/projects/${projectId}/schedule`, body),
};

// FR-011 推荐模块（全局，与 project 无关）
export const recommendationsApi = {
  list: (params?: {
    content_type?: string;
    keyword?: string;
    order_by?: "created_at" | "like_count" | "view_count";
    page?: number;
    page_size?: number;
  }) =>
    http.get<{ total: number; page: number; page_size: number; items: RecommendationItem[] }>(
      `/recommendations${qs(params ?? {})}`,
    ),

  create: (body: CreateRecommendationRequest) =>
    http.post<{ recommendation_id: string }>("/recommendations", body),

  delete: (recId: string) =>
    http.delete(`/recommendations/${recId}`),

  like: (recId: string) =>
    http.post(`/recommendations/${recId}/like`),
};
