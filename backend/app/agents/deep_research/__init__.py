"""
深度研究模式 Agent 入口（FR-025~028）

公开接口：
  - run_dialogue_turn()  — 处理单轮对话，返回 SSE 事件 async generator（FR-026）
  - generate_summary()   — 生成结构化研究进展摘要（FR-028）
  - build_graph_data()   — 构建知识图谱 JSON 数据（FR-025）
  - get_graphml()        — 导出 GraphML 格式图谱（FR-025）
  - rebuild_graph_stub() — 重建知识图谱（存根，FR-025）
"""

from app.agents.deep_research.dialogue_agent import generate_summary, run_dialogue_turn
from app.agents.deep_research.graph_builder import (
    build_graph_data,
    get_graphml,
    rebuild_graph_stub,
)

__all__ = [
    "run_dialogue_turn",
    "generate_summary",
    "build_graph_data",
    "get_graphml",
    "rebuild_graph_stub",
]
