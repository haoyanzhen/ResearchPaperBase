import { http } from "./client";
import type { ISODateString, StageStatus } from "../types";

// ── 任务管理类型（对齐 api.md 第 8 节）───────────────────────────────────────

export type TaskType = "construction" | "review" | "graph_rebuild";

export interface TaskItem {
  task_id: string;
  project_id: string;
  task_type: TaskType;
  status: StageStatus | "cancelled";
  stage: number | null;
  created_at: ISODateString;
}

export interface TaskStatusResponse {
  task_id: string;
  status: StageStatus | "cancelled";
}

// ── API 方法 ──────────────────────────────────────────────────────────────────

function qs(params: Record<string, unknown>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null) p.append(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

export const tasksApi = {
  list: (params?: { status?: string; project_id?: string }) =>
    http.get<TaskItem[]>(`/tasks${qs(params ?? {})}`),

  pause: (taskId: string) =>
    http.post<TaskStatusResponse>(`/tasks/${taskId}/pause`),

  resume: (taskId: string) =>
    http.post<TaskStatusResponse>(`/tasks/${taskId}/resume`),

  cancel: (taskId: string) =>
    http.post<TaskStatusResponse>(`/tasks/${taskId}/cancel`),
};
