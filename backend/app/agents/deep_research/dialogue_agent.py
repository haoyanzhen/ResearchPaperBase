"""
深度研究模式 — 对话 Agent（FR-026 / FR-028）

职责：
  - run_dialogue_turn()  — 处理单轮对话，以 SSE 事件流形式返回 LLM 回复
  - generate_summary()   — FR-028：生成结构化研究进展摘要（AgentSummary）

单轮对话执行流程（FR-026 规格）：
  1. Graph-RAG 检索：从论文库中按关键词匹配最相关论文
  2. 构建上下文：对话历史 + 论文上下文 + 子模式 system prompt
  3. LLM 推理：调用 LLM 生成回复
  4. 提取引用：从回复中识别 [paper_id] 格式引用
  5. 持久化：写入 dialogue_turns 表，更新 dialogue 元数据
  6. SSE 事件流：依次推送 turn_start / text_delta / turn_complete
"""

import json
import logging
from datetime import datetime, timezone
from typing import AsyncGenerator

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import get_llm_client, parse_json_response
from app.agents.deep_research.pipeline import (
    SUB_MODE_NAMES,
    build_context_from_papers,
    build_history_text,
    extract_referenced_papers,
    graph_rag_retrieve,
    load_deep_research_prompts,
)
from app.models.dialogue import DialogueTurn, ResearchDialogue
from app.models.project import Project
from app.utils.ids import new_id

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sse(event: str, data: dict) -> str:
    """格式化单条 SSE 事件字符串。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def run_dialogue_turn(
    db: AsyncSession,
    user_id: str,
    project_id: str,
    dialogue: ResearchDialogue,
    user_content: str,
    sub_mode: str,
) -> AsyncGenerator[str, None]:
    """
    处理单轮对话，以 async generator 形式 yield SSE 事件字符串。

    SSE 事件顺序：
      1. turn_start        — 告知前端轮次开始
      2. text_delta × N   — LLM 回复内容（分段推送）
      3. turn_complete     — 完整轮次数据

    注意：此函数在 HTTP 请求的 db 会话中运行（与 BackgroundTask 不同，
    StreamingResponse generator 在请求期间保持 session 存活）。
    """
    # ── 1. 获取历史轮次 ─────────────────────────────────────────────────────
    turns_res = await db.execute(
        select(DialogueTurn)
        .where(DialogueTurn.dialogue_id == dialogue.id)
        .order_by(DialogueTurn.turn_index)
    )
    history_turns = list(turns_res.scalars().all())

    # ── 2. 计算下一轮 turn_index ────────────────────────────────────────────
    next_index = len(history_turns) + 1
    sub_mode_before = history_turns[-1].sub_mode if history_turns else sub_mode

    # ── 3. Graph-RAG 检索 ────────────────────────────────────────────────────
    retrieved_papers = await graph_rag_retrieve(db, project_id, user_content)
    papers_context = build_context_from_papers(retrieved_papers)
    paper_ids = {p["paper_id"] for p in retrieved_papers}

    # ── 4. 构建 Prompt ───────────────────────────────────────────────────────
    project_res = await db.execute(select(Project).where(Project.id == project_id))
    project = project_res.scalar_one_or_none()
    project_name = project.name if project else project_id
    topic_desc = (
        f"课题描述：{project.description}" if (project and project.description) else ""
    )

    prompts = load_deep_research_prompts()
    prompt_key = f"dialogue_{sub_mode}"
    cfg = prompts.get(prompt_key, prompts["dialogue_technical"])

    history_text = build_history_text(history_turns)

    user_msg = cfg["user_template"].format_map({
        "project_name": project_name,
        "topic_desc": topic_desc,
        "papers_context": papers_context,
        "history": history_text,
        "user_question": user_content,
    })

    # ── 5. 推送 turn_start ──────────────────────────────────────────────────
    yield _sse("turn_start", {
        "turn_index": next_index,
        "sub_mode": sub_mode,
        "sub_mode_name": SUB_MODE_NAMES.get(sub_mode, sub_mode),
    })

    # ── 6. 调用 LLM ─────────────────────────────────────────────────────────
    try:
        llm = await get_llm_client(db, user_id, "deep_research")
        assistant_content = await llm.complete(
            [
                {"role": "system", "content": cfg["system"]},
                {"role": "user",   "content": user_msg},
            ],
            temperature=cfg.get("llm_params", {}).get("temperature"),
            max_tokens=cfg.get("llm_params", {}).get("max_tokens"),
        )
        assistant_content = assistant_content.strip()
    except Exception as exc:
        error_msg = f"LLM 调用失败：{exc}"
        logger.exception("dialogue_agent: LLM failed for project %s: %s", project_id, exc)
        yield _sse("error", {"message": error_msg})
        return

    # ── 7. 推送 text_delta（按段落分块，模拟流式输出）───────────────────────
    # 按段落分割，每段作为一个 delta；最小粒度 200 chars
    paragraphs = [p for p in assistant_content.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [assistant_content]

    for para in paragraphs:
        yield _sse("text_delta", {"delta": para + "\n\n"})

    # ── 8. 提取引用论文 ─────────────────────────────────────────────────────
    referenced = extract_referenced_papers(assistant_content, paper_ids)

    # graph_nodes_used：记录 Graph-RAG 命中的论文节点
    graph_nodes_used = [p["paper_id"] for p in retrieved_papers if p["matched_keywords"] > 0]

    # ── 9. 持久化 turn 记录 ─────────────────────────────────────────────────
    # 估算 token 数（粗略：汉字/英文单词各计1）
    input_tokens  = len(user_msg) // 4
    output_tokens = len(assistant_content) // 4

    turn = DialogueTurn(
        id=new_id("tu"),
        dialogue_id=dialogue.id,
        project_id=project_id,
        turn_index=next_index,
        sub_mode=sub_mode,
        user_content=user_content,
        assistant_content=assistant_content,
        referenced_papers=referenced if referenced else None,
        graph_nodes_used=graph_nodes_used if graph_nodes_used else None,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    db.add(turn)

    # 更新对话元数据
    dialogue.turn_count = next_index
    dialogue.last_active_at = _utcnow()
    await db.commit()
    await db.refresh(turn)

    # ── 10. 推送 turn_complete ──────────────────────────────────────────────
    yield _sse("turn_complete", {
        "turn_id": turn.id,
        "turn_index": turn.turn_index,
        "assistant_content": assistant_content,
        "sub_mode_before": sub_mode_before,
        "sub_mode_after": sub_mode,
        "referenced_papers": referenced,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    })


async def generate_summary(
    db: AsyncSession,
    user_id: str,
    project_id: str,
    dialogue: ResearchDialogue,
) -> dict:
    """
    FR-028：生成结构化研究进展摘要（AgentSummary）。

    返回 AgentSummary dict：
      {progress, key_findings, pending_issues, next_steps, generated_at}
    """
    # 获取所有轮次
    turns_res = await db.execute(
        select(DialogueTurn)
        .where(DialogueTurn.dialogue_id == dialogue.id)
        .order_by(DialogueTurn.turn_index)
    )
    turns = list(turns_res.scalars().all())

    if not turns:
        now = _utcnow().isoformat()
        return {
            "progress": "当前对话暂无内容，无法生成摘要。",
            "key_findings": [],
            "pending_issues": [],
            "next_steps": ["开始与 Agent 进行深度探讨"],
            "generated_at": now,
        }

    # 构建对话历史文本（全量，摘要需要完整历史）
    turns_lines: list[str] = []
    for t in turns:
        turns_lines.append(f"【轮{t.turn_index} - {SUB_MODE_NAMES.get(t.sub_mode, t.sub_mode)}】")
        turns_lines.append(f"用户：{t.user_content}")
        turns_lines.append(f"助手：{t.assistant_content[:800]}{'...' if len(t.assistant_content) > 800 else ''}")
    turns_text = "\n\n".join(turns_lines)

    project_res = await db.execute(select(Project).where(Project.id == project_id))
    project = project_res.scalar_one_or_none()
    project_name = project.name if project else project_id
    topic_desc = (
        f"课题描述：{project.description}" if (project and project.description) else ""
    )

    prompts = load_deep_research_prompts()
    cfg = prompts["dialogue_summarize"]
    now_str = _utcnow().isoformat()

    user_msg = cfg["user_template"].format_map({
        "project_name": project_name,
        "topic_desc": topic_desc,
        "turn_count": len(turns),
        "turns_text": turns_text,
    }).replace("{now}", now_str)

    llm = await get_llm_client(db, user_id, "deep_research")
    raw = await llm.complete(
        [
            {"role": "system", "content": cfg["system"]},
            {"role": "user",   "content": user_msg},
        ],
        temperature=cfg.get("llm_params", {}).get("temperature"),
        max_tokens=cfg.get("llm_params", {}).get("max_tokens"),
    )

    summary_data = parse_json_response(raw)

    # 确保 generated_at 字段存在
    if "generated_at" not in summary_data:
        summary_data["generated_at"] = now_str

    # 将 AgentSummary 序列化后存入对话记录
    dialogue.summary = json.dumps(summary_data, ensure_ascii=False)
    await db.commit()

    return summary_data
