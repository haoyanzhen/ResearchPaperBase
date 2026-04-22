"""
Agent 基础设施层

提供：
  - LLMClient          — OpenAI 兼容 API 调用（从 user_configs 读取活跃提供商）
  - get_llm_client()   — 工厂函数，读取 DB 中用户配置后构造 LLMClient
  - get_sse_queue()    — 返回（或创建）项目级 SSE 事件队列
  - emit_sse_event()   — 非阻塞写入 SSE 队列
  - load_prompts()     — 加载并缓存构建模式提示词（来自 config/construction_prompts.yaml）
  - load_llm_defaults()— 加载并缓存 LLM 默认参数（来自 config/llm_defaults.yaml）
  - parse_json_response()— 健壮解析 LLM 返回的 JSON（处理 Markdown 代码块包装）
"""

import asyncio
import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.config_service import get_all_llm_providers

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).parent / "config"

# ── SSE 事件队列（每个 project_id 一个队列，最多缓存 200 条事件）──────────────
_sse_queues: dict[str, asyncio.Queue] = {}


def get_sse_queue(project_id: str) -> asyncio.Queue:
    """返回（或懒创建）项目的 SSE 事件队列。单进程内安全（asyncio 单线程）。"""
    return _sse_queues.setdefault(project_id, asyncio.Queue(maxsize=200))


def emit_sse_event(project_id: str, event_type: str, data: dict) -> None:
    """
    非阻塞地向 SSE 队列写入一条事件。

    若队列满（无 SSE 客户端连接或客户端消费慢）则静默丢弃，
    不阻塞 Agent 执行。
    """
    queue = get_sse_queue(project_id)
    event_str = f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
    try:
        queue.put_nowait(event_str)
    except asyncio.QueueFull:
        logger.debug("SSE queue full for project %s, dropping event: %s", project_id, event_type)


# ── 配置加载（模块级缓存，进程内只读一次）──────────────────────────────────────

@lru_cache(maxsize=1)
def load_construction_prompts() -> dict:
    """加载并缓存构建模式提示词配置（config/construction_prompts.yaml）。"""
    with open(_CONFIG_DIR / "construction_prompts.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def load_llm_defaults() -> dict:
    """加载并缓存 LLM 默认参数配置（config/llm_defaults.yaml）。"""
    with open(_CONFIG_DIR / "llm_defaults.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_stage_llm_params(stage_key: str) -> dict:
    """
    合并 defaults 与 stage 级覆盖，返回该阶段的 LLM 参数字典。
    stage_key 示例：'construction_1', 'construction_3', 'construction_5'
    """
    defaults = load_llm_defaults()
    params = dict(defaults.get("defaults", {}))
    stage_override = defaults.get("stages", {}).get(stage_key, {})
    params.update(stage_override)
    return params


def get_retrieval_config(source: str) -> dict:
    """返回指定学术数据库的检索配置（来自 llm_defaults.yaml retrieval 节）。"""
    return load_llm_defaults().get("retrieval", {}).get(source, {})


def get_pdf_download_config() -> dict:
    """返回 PDF 下载配置。"""
    return load_llm_defaults().get("pdf_download", {})


# ── JSON 解析工具 ────────────────────────────────────────────────────────────

def parse_json_response(text: str) -> Any:
    """
    健壮解析 LLM 返回的 JSON。

    处理 LLM 常见的包装格式：
      - ```json ... ``` 代码块
      - ``` ... ``` 代码块
      - 前后的空白字符
    """
    text = text.strip()
    # 剥离 Markdown 代码块包装
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)
    return json.loads(text.strip())


# ── LLM 客户端 ───────────────────────────────────────────────────────────────

class LLMClient:
    """
    OpenAI 兼容 API 客户端。

    支持任意遵循 OpenAI Chat Completions 格式的提供商
    （OpenAI、Azure OpenAI、DeepSeek、Qwen、本地 Ollama 等）。
    """

    def __init__(self, provider_config: dict, stage_key: str):
        """
        provider_config: 从 user_configs 读取的活跃 LLM 提供商配置，包含：
            url, api_key, default_model, temperature, max_tokens
        stage_key: 阶段标识（如 'construction_1'），用于加载阶段级 LLM 参数
        """
        self._base_url = provider_config.get("url", "").rstrip("/")
        self._api_key = provider_config.get("api_key", "")
        self._default_model = provider_config.get("default_model", "gpt-4o-mini")

        # 合并参数优先级：stage 配置 > 用户 provider 配置 > yaml defaults
        stage_params = get_stage_llm_params(stage_key)
        self._temperature = float(
            stage_params.get("temperature",
                provider_config.get("temperature", 0.3))
        )
        self._max_tokens = int(
            stage_params.get("max_tokens",
                provider_config.get("max_tokens", 2000))
        )
        self._timeout = float(stage_params.get("request_timeout_seconds", 60))
        self._max_retries = int(stage_params.get("max_retries", 3))
        self._retry_delay = float(stage_params.get("retry_delay_seconds", 2.0))

    async def complete(
        self,
        messages: list[dict],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """
        发送 Chat Completions 请求，返回第一个 choice 的 content 字符串。

        parameters temperature / max_tokens 覆盖实例默认值。
        失败时按指数退避重试 max_retries 次。
        """
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._default_model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self._temperature,
            "max_tokens": max_tokens if max_tokens is not None else self._max_tokens,
        }

        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                    return data["choices"][0]["message"]["content"]
            except Exception as exc:
                last_exc = exc
                if attempt < self._max_retries - 1:
                    delay = self._retry_delay * (2 ** attempt)
                    logger.warning("LLM request failed (attempt %d/%d): %s — retrying in %.1fs",
                                   attempt + 1, self._max_retries, exc, delay)
                    await asyncio.sleep(delay)

        raise RuntimeError(f"LLM 请求失败（已重试 {self._max_retries} 次）: {last_exc}") from last_exc


async def get_llm_client(db: AsyncSession, user_id: str, stage_key: str) -> LLMClient:
    """
    工厂函数：从 user_configs 读取用户激活的 LLM 提供商配置，构造 LLMClient。
    若未配置提供商则抛出 ValueError。
    """
    providers = await get_all_llm_providers(db, user_id)
    active = next((p for p in providers if p.get("is_active")), None)
    if active is None:
        if providers:
            active = providers[0]   # 降级：取第一个
        else:
            raise ValueError("未配置任何 LLM 提供商，请先在系统配置中添加 LLM 配置")
    return LLMClient(active, stage_key)
