/**
 * InspectorPanel 组件内部类型（qa_design §8）
 */

import type {
  CheckResult,
  ConfigStatus,
  DeepHealthResponse,
  InspectResponse,
  KeywordSummary,
  PaperSummary,
  PipelineHealthResponse,
  RecommendationSeverity,
  StageHistoryItem,
} from "../../api/inspect";

export type { RecommendationSeverity };

// ── Panel 展示状态 ────────────────────────────────────────────────────────────

export type PanelLoadState = "idle" | "loading" | "success" | "error";

export interface InspectorPanelState {
  loadState: PanelLoadState;
  errorMessage: string | null;
  inspect: InspectResponse | null;
  pipeline: PipelineHealthResponse | null;
  deepHealth: DeepHealthResponse | null;
}

// ── 单条建议的结构化表示 ──────────────────────────────────────────────────────

export interface ParsedRecommendation {
  severity: RecommendationSeverity;
  text: string;
  raw: string;
}

// ── 阶段历史行的展示数据 ──────────────────────────────────────────────────────

export interface StageHistoryRow {
  item: StageHistoryItem;
  modeName: string;
  stageName: string;
  statusLabel: string;
  errorSummary: string | null;
}

// ── 依赖项检查行 ──────────────────────────────────────────────────────────────

export interface DependencyRow {
  label: string;
  check: CheckResult;
}

// ── Props ─────────────────────────────────────────────────────────────────────

export interface InspectorPanelProps {
  projectId: string;
  /** 自动刷新间隔（毫秒），0 表示不刷新，默认 0 */
  refreshInterval?: number;
  /** 面板展开/折叠受控状态 */
  open?: boolean;
  onClose?: () => void;
}
