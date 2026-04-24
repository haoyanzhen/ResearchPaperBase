"""
错误码体系与结构化错误信封（qa_design.md §3-4）

提供：
  - AppErrorCode       — 全量错误码枚举（ERR-{层}-{模块}-{序号}）
  - ErrorEnvelope      — 结构化错误信封 Pydantic 模型
  - make_envelope()    — 构造 ErrorEnvelope（自动填充 retryable/suggestion/traceback）
  - classify_agent_error() — 根据异常消息和模式/阶段推断错误码
"""

from __future__ import annotations

import traceback as _traceback_mod
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel


# =============================================================================
# 错误码枚举
# =============================================================================

class AppErrorCode(str, Enum):
    """全量错误码（格式：ERR-{层}-{模块}-{序号}）。"""

    # ── 系统/数据库层 (SYS) ────────────────────────────────────────────────────
    DB_CONNECTION_FAILED     = "ERR-SYS-DB-001"
    DB_QUERY_TIMEOUT         = "ERR-SYS-DB-002"
    DB_CONSTRAINT_VIOLATION  = "ERR-SYS-DB-003"
    DB_DETACHED_INSTANCE     = "ERR-SYS-DB-004"
    CONFIG_MISSING           = "ERR-SYS-CFG-001"
    CONFIG_INVALID_FORMAT    = "ERR-SYS-CFG-002"

    # ── 认证/权限层 (AUTH) ─────────────────────────────────────────────────────
    TOKEN_EXPIRED            = "ERR-AUTH-001"
    TOKEN_INVALID            = "ERR-AUTH-002"
    ACCOUNT_DISABLED         = "ERR-AUTH-003"
    FORBIDDEN                = "ERR-AUTH-004"

    # ── LLM API 层 (LLM) ──────────────────────────────────────────────────────
    LLM_API_KEY_INVALID      = "ERR-LLM-001"
    LLM_RATE_LIMIT_EXCEEDED  = "ERR-LLM-002"
    LLM_CONTEXT_TOO_LONG     = "ERR-LLM-003"
    LLM_JSON_PARSE_FAILED    = "ERR-LLM-004"
    LLM_TIMEOUT              = "ERR-LLM-005"
    LLM_NO_CONFIG            = "ERR-LLM-006"

    # ── 外部 API 层 (EXT) ─────────────────────────────────────────────────────
    ARXIV_UNREACHABLE        = "ERR-EXT-ARXIV-001"
    ARXIV_RATE_LIMIT         = "ERR-EXT-ARXIV-002"
    OPENALEX_KEY_INVALID     = "ERR-EXT-OA-001"
    SEMANTIC_SCHOLAR_TIMEOUT = "ERR-EXT-SS-001"
    ADS_KEY_INVALID          = "ERR-EXT-ADS-001"
    PDF_DOWNLOAD_FAILED      = "ERR-EXT-PDF-001"
    PDF_PARSE_ERROR          = "ERR-EXT-PDF-002"
    SMTP_AUTH_FAILED         = "ERR-EXT-SMTP-001"
    SMTP_SEND_FAILED         = "ERR-EXT-SMTP-002"

    # ── 构建模式 Agent (AGT-C) ────────────────────────────────────────────────
    AGT_KEYWORD_GEN_EMPTY    = "ERR-AGT-C1-001"
    AGT_RETRIEVAL_ALL_FAILED = "ERR-AGT-C2-001"
    AGT_RETRIEVAL_PARTIAL    = "ERR-AGT-C2-002"
    AGT_SCORING_BATCH_FAILED = "ERR-AGT-C3-001"
    AGT_DOWNLOAD_ALL_FAILED  = "ERR-AGT-C4-001"
    AGT_ANALYSIS_BATCH_FAILED= "ERR-AGT-C5-001"

    # ── 综述模式 Agent (AGT-R) ────────────────────────────────────────────────
    AGT_TOPIC_EXPANSION_EMPTY= "ERR-AGT-R1-001"
    AGT_OUTLINE_INVALID_JSON = "ERR-AGT-R2-001"
    AGT_CHAPTER_WRITE_FAILED = "ERR-AGT-R3-001"
    AGT_REVIEW_LOOP_EXCEEDED = "ERR-AGT-R4-001"

    # ── 深度研究模式 Agent (AGT-D) ────────────────────────────────────────────
    AGT_GRAPH_RAG_NO_RESULTS = "ERR-AGT-D1-001"
    AGT_SUMMARY_INVALID_JSON = "ERR-AGT-D2-001"

    # ── 业务验证层 (VAL) ──────────────────────────────────────────────────────
    PROJECT_NOT_FOUND        = "ERR-VAL-001"
    EMPTY_PAPER_LIBRARY      = "ERR-VAL-002"
    TASK_ALREADY_RUNNING     = "ERR-VAL-003"
    DIALOGUE_ARCHIVED        = "ERR-VAL-004"
    OUTLINE_NOT_CONFIRMED    = "ERR-VAL-005"


# =============================================================================
# 可重试错误码集合
# =============================================================================

RETRYABLE_CODES: frozenset[AppErrorCode] = frozenset({
    AppErrorCode.DB_CONNECTION_FAILED,
    AppErrorCode.DB_QUERY_TIMEOUT,
    AppErrorCode.LLM_RATE_LIMIT_EXCEEDED,
    AppErrorCode.LLM_JSON_PARSE_FAILED,
    AppErrorCode.LLM_TIMEOUT,
    AppErrorCode.ARXIV_UNREACHABLE,
    AppErrorCode.ARXIV_RATE_LIMIT,
    AppErrorCode.SEMANTIC_SCHOLAR_TIMEOUT,
    AppErrorCode.PDF_DOWNLOAD_FAILED,
    AppErrorCode.SMTP_SEND_FAILED,
    AppErrorCode.AGT_KEYWORD_GEN_EMPTY,
    AppErrorCode.AGT_RETRIEVAL_ALL_FAILED,
    AppErrorCode.AGT_SCORING_BATCH_FAILED,
    AppErrorCode.AGT_DOWNLOAD_ALL_FAILED,
    AppErrorCode.AGT_ANALYSIS_BATCH_FAILED,
    AppErrorCode.AGT_TOPIC_EXPANSION_EMPTY,
    AppErrorCode.AGT_OUTLINE_INVALID_JSON,
    AppErrorCode.AGT_CHAPTER_WRITE_FAILED,
    AppErrorCode.AGT_SUMMARY_INVALID_JSON,
})

# =============================================================================
# 建议修复文本
# =============================================================================

SUGGESTIONS: dict[AppErrorCode, str] = {
    AppErrorCode.DB_CONNECTION_FAILED:      "检查 DATABASE_URL 配置；确认数据库服务运行",
    AppErrorCode.DB_QUERY_TIMEOUT:          "检查慢查询；考虑添加索引",
    AppErrorCode.DB_CONSTRAINT_VIOLATION:   "检查重复提交逻辑",
    AppErrorCode.DB_DETACHED_INSTANCE:      "BackgroundTask 必须使用独立 AsyncSession，不可复用 HTTP session",
    AppErrorCode.CONFIG_MISSING:            "在设置界面补充 LLM/数据库配置",
    AppErrorCode.CONFIG_INVALID_FORMAT:     "检查配置值 JSON 格式是否合法",
    AppErrorCode.TOKEN_EXPIRED:             "重新登录获取新 Token",
    AppErrorCode.TOKEN_INVALID:             "清除本地 Token，重新登录",
    AppErrorCode.ACCOUNT_DISABLED:          "账号已被禁用，请联系管理员",
    AppErrorCode.FORBIDDEN:                 "当前账号无此操作权限，请确认是否为管理员",
    AppErrorCode.LLM_API_KEY_INVALID:       "在「设置 → LLM 配置」更新 API 密钥",
    AppErrorCode.LLM_RATE_LIMIT_EXCEEDED:   "等待后自动重试；建议在管理员面板配置备用模型",
    AppErrorCode.LLM_CONTEXT_TOO_LONG:      "缩短对话历史或减少论文上下文长度",
    AppErrorCode.LLM_JSON_PARSE_FAILED:     "系统将自动重试（最多3次）；持续失败请简化课题描述",
    AppErrorCode.LLM_TIMEOUT:              "检查网络连接；考虑切换响应更快的模型",
    AppErrorCode.LLM_NO_CONFIG:             "在「设置 → LLM 配置」添加模型，或联系管理员配置系统级默认模型",
    AppErrorCode.ARXIV_UNREACHABLE:         "检查网络连通性；arXiv 可能正在维护",
    AppErrorCode.ARXIV_RATE_LIMIT:          "降低 batch_size；增加请求间隔",
    AppErrorCode.OPENALEX_KEY_INVALID:      "在「设置 → 论文数据库」更新 OpenAlex API 密钥",
    AppErrorCode.SEMANTIC_SCHOLAR_TIMEOUT:  "网络超时，系统将自动重试",
    AppErrorCode.ADS_KEY_INVALID:           "在「设置 → 论文数据库」更新 ADS API 密钥",
    AppErrorCode.PDF_DOWNLOAD_FAILED:       "将尝试 Unpaywall 备用源；最终降级使用摘要替代",
    AppErrorCode.PDF_PARSE_ERROR:           "PDF 解析失败，已自动降级使用摘要替代",
    AppErrorCode.SMTP_AUTH_FAILED:          "在「设置 → 邮件」检查 SMTP 配置，更新应用密码",
    AppErrorCode.SMTP_SEND_FAILED:          "邮件发送失败，请检查收件人地址是否有效",
    AppErrorCode.AGT_KEYWORD_GEN_EMPTY:     "课题描述过于简短，补充更多背景信息后重试",
    AppErrorCode.AGT_RETRIEVAL_ALL_FAILED:  "所有数据源均不可达，请在「设置 → 论文数据库」检查各 API 配置",
    AppErrorCode.AGT_RETRIEVAL_PARTIAL:     "部分数据源检索失败，已使用可用数据源继续（仅警告）",
    AppErrorCode.AGT_SCORING_BATCH_FAILED:  "评分批次失败，请检查 LLM 配置或将 batch_size 调低后重试",
    AppErrorCode.AGT_DOWNLOAD_ALL_FAILED:   "本批次 PDF 全部下载失败，将降级使用摘要；检查网络",
    AppErrorCode.AGT_ANALYSIS_BATCH_FAILED: "AI 分析失败，请检查 LLM 配置或降低并发请求数",
    AppErrorCode.AGT_TOPIC_EXPANSION_EMPTY: "课题扩写结果为空，请补充课题描述后重试",
    AppErrorCode.AGT_OUTLINE_INVALID_JSON:  "架构生成 JSON 解析失败，系统将自动重试最多3次",
    AppErrorCode.AGT_CHAPTER_WRITE_FAILED:  "章节撰写失败，可在综述管理界面重新触发单章任务",
    AppErrorCode.AGT_REVIEW_LOOP_EXCEEDED:  "审查迭代超过上限（2次），可手动接受当前版本后继续",
    AppErrorCode.AGT_GRAPH_RAG_NO_RESULTS:  "当前课题论文库为空，请先在构建模式中收集论文",
    AppErrorCode.AGT_SUMMARY_INVALID_JSON:  "摘要 JSON 解析失败，系统将自动重试",
    AppErrorCode.PROJECT_NOT_FOUND:         "项目不存在或当前用户无权限访问",
    AppErrorCode.EMPTY_PAPER_LIBRARY:       "有效论文数为0，请先完成构建模式后再切换",
    AppErrorCode.TASK_ALREADY_RUNNING:      "项目已有运行中任务，请等待完成或取消后重试",
    AppErrorCode.DIALOGUE_ARCHIVED:         "对话已归档，请创建新的对话会话",
    AppErrorCode.OUTLINE_NOT_CONFIRMED:     "请先在综述界面确认架构，再触发章节撰写",
}


# =============================================================================
# 错误信封模型
# =============================================================================

class ErrorEnvelope(BaseModel):
    """
    结构化错误信封（qa_design.md §4）。

    用于：
      - SSE stage_error / error 事件的 data 字段
      - stage_records.error TEXT 字段（JSON 序列化存储）
      - /inspect 端点 stage_history[].error 字段
    """
    code: str
    message: str
    detail: dict[str, Any] | None = None
    traceback: str | None = None
    retryable: bool = False
    suggestion: str = ""
    occurred_at: str = ""
    project_id: str | None = None
    stage_record_id: str | None = None

    model_config = {"extra": "ignore"}


# =============================================================================
# 构造辅助函数
# =============================================================================

def make_envelope(
    code: AppErrorCode,
    message: str,
    *,
    detail: dict[str, Any] | None = None,
    exc: BaseException | None = None,
    project_id: str | None = None,
    stage_record_id: str | None = None,
) -> ErrorEnvelope:
    """
    构造 ErrorEnvelope，自动填充：
      - retryable    — 根据 RETRYABLE_CODES 判断
      - suggestion   — 从 SUGGESTIONS 映射取对应文本
      - occurred_at  — 当前 UTC 时间 ISO 字符串
      - traceback    — 若传入 exc 则格式化完整堆栈
    """
    tb: str | None = None
    if exc is not None:
        tb = "".join(_traceback_mod.format_exception(type(exc), exc, exc.__traceback__))

    return ErrorEnvelope(
        code=code.value,
        message=message,
        detail=detail,
        traceback=tb,
        retryable=code in RETRYABLE_CODES,
        suggestion=SUGGESTIONS.get(code, ""),
        occurred_at=datetime.now(timezone.utc).isoformat(),
        project_id=project_id,
        stage_record_id=stage_record_id,
    )


def classify_llm_error(exc: Exception) -> AppErrorCode:
    """根据异常消息推断 LLM 错误码。"""
    msg = str(exc).lower()
    if "401" in msg or "invalid api key" in msg or "incorrect api key" in msg:
        return AppErrorCode.LLM_API_KEY_INVALID
    if "rate limit" in msg or "429" in msg or "too many requests" in msg:
        return AppErrorCode.LLM_RATE_LIMIT_EXCEEDED
    if "context length" in msg or ("token" in msg and "exceed" in msg):
        return AppErrorCode.LLM_CONTEXT_TOO_LONG
    if "timeout" in msg or "timed out" in msg or "read timeout" in msg:
        return AppErrorCode.LLM_TIMEOUT
    # 通用网络错误（连接拒绝、DNS 失败等）也用 TIMEOUT（可重试）
    return AppErrorCode.LLM_TIMEOUT


_CONSTRUCTION_STAGE_CODES: dict[int, AppErrorCode] = {
    1: AppErrorCode.AGT_KEYWORD_GEN_EMPTY,
    2: AppErrorCode.AGT_RETRIEVAL_ALL_FAILED,
    3: AppErrorCode.AGT_SCORING_BATCH_FAILED,
    4: AppErrorCode.AGT_DOWNLOAD_ALL_FAILED,
    5: AppErrorCode.AGT_ANALYSIS_BATCH_FAILED,
}

_REVIEW_STAGE_CODES: dict[int, AppErrorCode] = {
    1: AppErrorCode.AGT_TOPIC_EXPANSION_EMPTY,
    2: AppErrorCode.AGT_OUTLINE_INVALID_JSON,
    3: AppErrorCode.AGT_CHAPTER_WRITE_FAILED,
    4: AppErrorCode.AGT_REVIEW_LOOP_EXCEEDED,
}


def classify_agent_error(exc: Exception, mode: str, stage: int) -> AppErrorCode:
    """
    根据异常消息、模式和阶段编号推断最合适的错误码。

    优先识别 LLM 相关错误（API Key / Rate Limit / Timeout），
    其次按阶段映射到对应的 AGT-* 错误码。
    """
    msg = str(exc).lower()
    # LLM 相关关键词优先
    if any(kw in msg for kw in ("api key", "invalid key", "incorrect api")):
        return AppErrorCode.LLM_API_KEY_INVALID
    if any(kw in msg for kw in ("rate limit", "429", "too many requests")):
        return AppErrorCode.LLM_RATE_LIMIT_EXCEEDED
    if "context length" in msg or ("token" in msg and "exceed" in msg):
        return AppErrorCode.LLM_CONTEXT_TOO_LONG
    if any(kw in msg for kw in ("json", "parse", "decode")):
        return AppErrorCode.LLM_JSON_PARSE_FAILED

    # 阶段-模式映射
    if mode == "construction":
        return _CONSTRUCTION_STAGE_CODES.get(stage, AppErrorCode.LLM_TIMEOUT)
    if mode == "review":
        return _REVIEW_STAGE_CODES.get(stage, AppErrorCode.LLM_TIMEOUT)

    return AppErrorCode.LLM_TIMEOUT
