import { http, tokenStore } from "./client";
import type {
  AgentSummary,
  DialogueStatus,
  GraphEdgeType,
  GraphNodeType,
  ISODateString,
  SubMode,
} from "../types";

// ── 深度研究模式类型（对齐 api.md 第 6 节）───────────────────────────────────

export interface DialogueSummaryItem {
  dialogue_id: string;
  title: string | null;
  sub_mode: SubMode;
  status: DialogueStatus;
  turn_count: number;
  summary: string | null;
  tags: string[] | null;
  created_at: ISODateString;
  last_active_at: ISODateString;
}

export interface DialogueDetail extends DialogueSummaryItem {
  summary: AgentSummary | null;
}

export interface CreateDialogueRequest {
  title?: string;
  sub_mode?: SubMode;
}

export interface UpdateDialogueRequest {
  title?: string;
  sub_mode?: SubMode;
  tags?: string[];
  status?: DialogueStatus;
}

export interface DialogueTurnItem {
  turn_id: string;
  turn_index: number;
  user_content: string;
  assistant_content: string;
  sub_mode_before: SubMode;
  sub_mode_after: SubMode;
  referenced_papers: string[] | null;
  input_tokens: number | null;
  output_tokens: number | null;
  created_at: ISODateString;
}

export interface SendMessageRequest {
  user_content: string;
  sub_mode: SubMode;
}

export interface SummarizeResponse {
  dialogue_id: string;
  summary: AgentSummary;
}

// ── 知识图谱类型 ───────────────────────────────────────────────────────────────

export interface GraphNode {
  id: string;
  type: GraphNodeType;
  label: string;
  score?: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: GraphEdgeType;
  weight: number;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats: { node_count: number; edge_count: number };
}

export interface RebuildGraphResponse {
  task_id: string;
  message: string;
}

// ── SSE 事件数据类型（对话流） ────────────────────────────────────────────────

export interface SseTurnStart {
  turn_index: number;
  sub_mode: SubMode;
}

export interface SseTextDelta {
  delta: string;
}

export interface SseTurnComplete {
  turn_id: string;
  turn_index: number;
  assistant_content: string;
  sub_mode_before: SubMode;
  sub_mode_after: SubMode;
  referenced_papers: string[] | null;
  input_tokens: number;
  output_tokens: number;
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

export const dialoguesApi = {
  list: (projectId: string) =>
    http.get<DialogueSummaryItem[]>(`/projects/${projectId}/dialogues`),

  create: (projectId: string, body?: CreateDialogueRequest) =>
    http.post<DialogueDetail>(`/projects/${projectId}/dialogues`, body ?? {}),

  get: (projectId: string, dialogueId: string) =>
    http.get<DialogueDetail>(`/projects/${projectId}/dialogues/${dialogueId}`),

  update: (projectId: string, dialogueId: string, body: UpdateDialogueRequest) =>
    http.patch<DialogueDetail>(
      `/projects/${projectId}/dialogues/${dialogueId}`,
      body,
    ),

  delete: (projectId: string, dialogueId: string) =>
    http.delete(`/projects/${projectId}/dialogues/${dialogueId}`),

  getTurns: (
    projectId: string,
    dialogueId: string,
    params?: { offset?: number; limit?: number },
  ) =>
    http.get<DialogueTurnItem[]>(
      `/projects/${projectId}/dialogues/${dialogueId}/turns${qs(params ?? {})}`,
    ),

  /**
   * 发送消息（SSE 流）。
   * 返回 URL，调用方通过 fetch + ReadableStream 处理流式输出：
   *   const resp = await fetch(url, { method:'POST', ... })
   * 详见 api.md §10.2 约定。
   */
  sendMessage: (projectId: string, dialogueId: string, body: SendMessageRequest) =>
    fetch(`/api/v1/projects/${projectId}/dialogues/${dialogueId}/turns`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(tokenStore.get()
          ? { Authorization: `Bearer ${tokenStore.get()}` }
          : {}),
      },
      body: JSON.stringify(body),
    }),

  summarize: (projectId: string, dialogueId: string) =>
    http.post<SummarizeResponse>(
      `/projects/${projectId}/dialogues/${dialogueId}/summarize`,
    ),

  getGraph: (
    projectId: string,
    params?: { format?: "json" | "graphml"; node_types?: string },
  ) =>
    http.get<GraphData>(`/projects/${projectId}/graph${qs(params ?? {})}`),

  rebuildGraph: (projectId: string) =>
    http.post<RebuildGraphResponse>(`/projects/${projectId}/graph/rebuild`),
};
