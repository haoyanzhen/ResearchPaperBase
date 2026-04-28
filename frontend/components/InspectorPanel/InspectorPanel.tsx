/**
 * InspectorPanel — 项目诊断面板（qa_design §8）
 *
 * 结构：
 *   ┌─────────────────────────────────────────────┐
 *   │ Inspector  [Refresh] [×]                    │
 *   ├─────────────────────────────────────────────┤
 *   │ [!] FATAL: LLM 未配置 ...                   │  ← Recommendations
 *   │ [!] ERROR: 阶段 3 失败 ...                  │
 *   ├───────────────┬─────────────────────────────┤
 *   │ 论文库         │ 配置状态                     │
 *   │ total / valid │ LLM: gpt-4o ✓              │
 *   ├───────────────┴─────────────────────────────┤
 *   │ 阶段历史（最近 10 条）                        │
 *   │ construction stage3  failed  2026-04-24     │
 *   │   ERR-LLM-002  rate limited  [retry?]       │
 *   └─────────────────────────────────────────────┘
 *
 * 设计为框架无关的纯 React 函数组件（不依赖 UI 库）。
 * 样式通过 CSS 类名约定传递，宿主应用提供样式表。
 */

import React, { useCallback, useEffect, useRef, useState } from "react";

import {
  getDeepHealth,
  getPipelineHealth,
  getProjectInspect,
  parseRecommendationSeverity,
} from "../../api/inspect";

import type {
  DeepHealthResponse,
  InspectResponse,
  PipelineHealthResponse,
  StageHistoryItem,
} from "../../api/inspect";

import type {
  DependencyRow,
  InspectorPanelProps,
  InspectorPanelState,
  ParsedRecommendation,
  RecommendationSeverity,
} from "./types";

// ── 常量 ──────────────────────────────────────────────────────────────────────

const SEVERITY_CLASSES: Record<RecommendationSeverity, string> = {
  fatal:   "inspector-rec--fatal",
  error:   "inspector-rec--error",
  warning: "inspector-rec--warning",
  info:    "inspector-rec--info",
};

const SEVERITY_ICONS: Record<RecommendationSeverity, string> = {
  fatal:   "🔴",
  error:   "🟠",
  warning: "🟡",
  info:    "🔵",
};

const STAGE_NAMES: Record<string, Record<number, string>> = {
  construction: { 1: "关键词生成", 2: "文献检索", 3: "评分筛选", 4: "下载解析", 5: "AI 分析", 6: "格式存储", 7: "邮件推送" },
  review:       { 1: "课题扩写", 2: "架构生成", 3: "章节撰写", 4: "审查迭代", 5: "汇总成文" },
};

// ── 辅助函数 ──────────────────────────────────────────────────────────────────

function parseRecommendations(recs: string[]): ParsedRecommendation[] {
  return recs.map((raw) => ({
    raw,
    severity: parseRecommendationSeverity(raw),
    text: raw.replace(/^\[(FATAL|ERROR|WARNING|INFO)\]\s*/, ""),
  }));
}

function formatElapsed(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m${seconds % 60}s`;
}

function errorSummary(item: StageHistoryItem): string | null {
  if (!item.error) return null;
  if ("raw" in item.error) return item.error.raw.slice(0, 80);
  return `${item.error.code}: ${item.error.message.slice(0, 60)}`;
}

// ── 子组件：建议条目 ──────────────────────────────────────────────────────────

function RecommendationItem({ rec }: { rec: ParsedRecommendation }) {
  return (
    <div className={`inspector-rec ${SEVERITY_CLASSES[rec.severity]}`}>
      <span className="inspector-rec__icon">{SEVERITY_ICONS[rec.severity]}</span>
      <span className="inspector-rec__text">{rec.text}</span>
    </div>
  );
}

// ── 子组件：阶段历史行 ─────────────────────────────────────────────────────────

function StageHistoryRow({ item }: { item: StageHistoryItem }) {
  const stageName =
    STAGE_NAMES[item.mode]?.[item.stage] ?? `阶段 ${item.stage}`;
  const summary = errorSummary(item);

  return (
    <div className={`inspector-stage inspector-stage--${item.status}`}>
      <div className="inspector-stage__header">
        <span className="inspector-stage__mode">{item.mode}</span>
        <span className="inspector-stage__name">{stageName}</span>
        <span className={`inspector-stage__status inspector-stage__status--${item.status}`}>
          {item.status}
        </span>
        <span className="inspector-stage__elapsed">
          {formatElapsed(item.elapsed_seconds)}
        </span>
      </div>
      {summary && (
        <div className="inspector-stage__error">
          <code>{summary}</code>
          {"error" in item && item.error && "retryable" in item.error && item.error.retryable && (
            <span className="inspector-stage__retryable"> (可重试)</span>
          )}
        </div>
      )}
    </div>
  );
}

// ── 子组件：依赖项检查格 ──────────────────────────────────────────────────────

function DependencyGrid({ health }: { health: DeepHealthResponse | null }) {
  if (!health) return null;

  const rows: DependencyRow[] = [
    { label: "LLM (主)", check: health.checks.llm_primary },
    { label: "LLM (备)", check: health.checks.llm_fallback },
    { label: "arXiv",    check: health.checks.arxiv },
    { label: "OpenAlex", check: health.checks.openalex },
    { label: "Semantic", check: health.checks.semantic_scholar },
    { label: "ADS",      check: health.checks.ads },
    { label: "SMTP",     check: health.checks.smtp },
  ];

  return (
    <div className="inspector-deps">
      <h4 className="inspector-section__title">外部依赖</h4>
      <div className="inspector-deps__grid">
        {rows.map(({ label, check }) => (
          <div
            key={label}
            className={`inspector-dep inspector-dep--${check.status}`}
            title={check.message ?? check.suggestion ?? ""}
          >
            <span className="inspector-dep__label">{label}</span>
            <span className="inspector-dep__status">{check.status}</span>
            {check.latency_ms !== null && (
              <span className="inspector-dep__latency">{check.latency_ms}ms</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── 主组件 ────────────────────────────────────────────────────────────────────

export function InspectorPanel({
  projectId,
  refreshInterval = 0,
  open = true,
  onClose,
}: InspectorPanelProps) {
  const [state, setState] = useState<InspectorPanelState>({
    loadState: "idle",
    errorMessage: null,
    inspect: null,
    pipeline: null,
    deepHealth: null,
  });

  const abortRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    setState((s) => ({ ...s, loadState: "loading", errorMessage: null }));

    try {
      const [inspect, pipeline, deepHealth] = await Promise.all([
        getProjectInspect(projectId, ac.signal),
        getPipelineHealth(projectId),
        getDeepHealth(ac.signal),
      ]);

      if (ac.signal.aborted) return;

      setState({
        loadState: "success",
        errorMessage: null,
        inspect,
        pipeline,
        deepHealth,
      });
    } catch (err: unknown) {
      if (ac.signal.aborted) return;
      const msg = err instanceof Error ? err.message : String(err);
      setState((s) => ({ ...s, loadState: "error", errorMessage: msg }));
    }
  }, [projectId]);

  // 首次加载
  useEffect(() => {
    if (open) load();
    return () => abortRef.current?.abort();
  }, [open, load]);

  // 定时刷新
  useEffect(() => {
    if (!open || refreshInterval <= 0) return;
    const id = setInterval(load, refreshInterval);
    return () => clearInterval(id);
  }, [open, refreshInterval, load]);

  if (!open) return null;

  const { loadState, errorMessage, inspect, pipeline, deepHealth } = state;
  const recommendations = inspect
    ? parseRecommendations(inspect.recommendations)
    : [];

  return (
    <div className="inspector-panel" role="complementary" aria-label="项目诊断面板">
      {/* ── 标题栏 ─────────────────────────────────────────────────────── */}
      <div className="inspector-panel__header">
        <h3 className="inspector-panel__title">Inspector</h3>
        <div className="inspector-panel__actions">
          <button
            className="inspector-panel__btn"
            onClick={load}
            disabled={loadState === "loading"}
            aria-label="刷新"
          >
            {loadState === "loading" ? "加载中…" : "刷新"}
          </button>
          {onClose && (
            <button
              className="inspector-panel__btn inspector-panel__btn--close"
              onClick={onClose}
              aria-label="关闭"
            >
              ×
            </button>
          )}
        </div>
      </div>

      {/* ── 错误提示 ────────────────────────────────────────────────────── */}
      {loadState === "error" && errorMessage && (
        <div className="inspector-panel__load-error" role="alert">
          加载失败：{errorMessage}
        </div>
      )}

      {/* ── 建议列表 ─────────────────────────────────────────────────────── */}
      {recommendations.length > 0 && (
        <section className="inspector-section">
          <h4 className="inspector-section__title">诊断建议</h4>
          <div className="inspector-recs">
            {recommendations.map((rec, i) => (
              <RecommendationItem key={i} rec={rec} />
            ))}
          </div>
        </section>
      )}

      {/* ── 摘要统计 ─────────────────────────────────────────────────────── */}
      {inspect && (
        <section className="inspector-section inspector-summary">
          <div className="inspector-summary__block">
            <h4 className="inspector-section__title">论文库</h4>
            <dl className="inspector-dl">
              <dt>总数</dt><dd data-testid="paper-total">{inspect.paper_summary.total}</dd>
              <dt>有效</dt><dd>{inspect.paper_summary.valid}</dd>
              <dt>已下载</dt><dd>{inspect.paper_summary.downloaded}</dd>
              <dt>已分析</dt><dd>{inspect.paper_summary.analyzed}</dd>
            </dl>
          </div>
          <div className="inspector-summary__block">
            <h4 className="inspector-section__title">配置状态</h4>
            <dl className="inspector-dl">
              <dt>LLM</dt>
              <dd className={inspect.config_status.llm_configured ? "inspector-dl__ok" : "inspector-dl__err"}>
                {inspect.config_status.llm_configured
                  ? inspect.config_status.llm_active_provider ?? "已配置"
                  : "未配置"}
              </dd>
              <dt>论文库</dt>
              <dd>{inspect.config_status.paper_db_sources?.join(", ") || "未配置"}</dd>
              <dt>邮件</dt>
              <dd>{inspect.config_status.smtp_configured ? "已配置" : "未配置"}</dd>
            </dl>
          </div>
        </section>
      )}

      {/* ── 外部依赖 ─────────────────────────────────────────────────────── */}
      <DependencyGrid health={deepHealth} />

      {/* ── 活跃阶段 ─────────────────────────────────────────────────────── */}
      {pipeline && pipeline.active_stages.length > 0 && (
        <section className="inspector-section">
          <h4 className="inspector-section__title">活跃阶段</h4>
          {pipeline.active_stages.map((snap) => (
            <StageHistoryRow
              key={snap.stage_record_id}
              item={{
                stage_record_id: snap.stage_record_id,
                stage: snap.stage,
                mode: snap.mode,
                status: snap.status,
                started_at: snap.started_at,
                completed_at: null,
                elapsed_seconds: snap.elapsed_seconds,
                error: snap.error_preview,
              }}
            />
          ))}
        </section>
      )}

      {/* ── 阶段历史 ─────────────────────────────────────────────────────── */}
      {inspect && inspect.stage_history.length > 0 && (
        <section className="inspector-section">
          <h4 className="inspector-section__title">阶段历史（最近 10 条）</h4>
          {inspect.stage_history.slice(0, 10).map((item) => (
            <StageHistoryRow key={item.stage_record_id} item={item} />
          ))}
        </section>
      )}

      {/* ── 空状态 ───────────────────────────────────────────────────────── */}
      {loadState === "success" && !inspect && (
        <div className="inspector-panel__empty">暂无诊断数据</div>
      )}
    </div>
  );
}
