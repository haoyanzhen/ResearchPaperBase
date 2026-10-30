"""Text-only model adapter. Application authorization and durable budgets are required."""

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any
from urllib.parse import quote

from rpb.adapters.llm_provider import HTTPProvider, ProviderFailure
from rpb.adapters.pdf_cleanup_capacity import effective_config
from rpb.adapters.pdf_text_cleanup import Batch, validate
from rpb.modules.account_config.domain.llm_profiles import compile_for_model


class CleanupProvider:
    def __init__(self, http: HTTPProvider | None = None) -> None:
        self.http = http or HTTPProvider()

    def propose(
        self,
        config: dict[str, Any],
        model: str,
        secret: str,
        batch: Batch,
        timeout: float,
        authorize: Callable[[], AbstractContextManager[None]],
    ) -> dict[str, Any]:
        """Exactly one request, no fallback/retry and no implicit configuration probes."""
        if not 0 < timeout <= 30:
            raise ProviderFailure("CONFIG_CONNECTION_FAILED")
        config, _, _ = effective_config(config, model)
        prompt = batch.prompt()
        protocol = config["protocol"]
        params = compile_for_model(protocol, model, config["parameters"], config["api_version"])
        if protocol in {"openai_chat", "anthropic_messages"}:
            if protocol == "anthropic_messages" and "max_tokens" not in params:
                raise ProviderFailure("CONFIG_CONNECTION_FAILED")
            path = "/messages" if protocol == "anthropic_messages" else "/chat/completions"
            body = {
                **params,
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            }
        elif protocol == "openai_responses":
            path, body = "/responses", {**params, "model": model, "input": prompt, "stream": False}
        elif protocol == "gemini_content":
            path = "/models/" + quote(model, safe="") + ":generateContent"
            body = {**params, "contents": [{"role": "user", "parts": [{"text": prompt}]}]}
        else:
            raise ProviderFailure("CONFIG_CONNECTION_FAILED")
        response = self.http.request(
            config["base_url"],
            path,
            secret,
            protocol,
            config["api_version"],
            body,
            min(timeout, config["timeout_seconds"]),
            authorize,
        )
        try:
            if protocol == "openai_chat":
                item = response["choices"][0]
                if item.get("finish_reason") not in {None, "stop"}:
                    raise ValueError("incomplete response")
                text = item["message"]["content"]
            elif protocol == "openai_responses":
                if response.get("status") not in {None, "completed"}:
                    raise ValueError("incomplete response")
                text = "".join(
                    part["text"]
                    for item in response["output"]
                    if item.get("type") == "message"
                    for part in item["content"]
                    if part.get("type") == "output_text"
                )
            elif protocol == "anthropic_messages":
                if response.get("stop_reason") not in {None, "end_turn", "stop_sequence"}:
                    raise ValueError("incomplete response")
                text = "".join(
                    part["text"] for part in response["content"] if part.get("type") == "text"
                )
            else:
                item = response["candidates"][0]
                if item.get("finishReason") not in {None, "STOP"}:
                    raise ValueError("incomplete response")
                text = "".join(
                    part["text"]
                    for part in item["content"]["parts"]
                    if part.get("thought") is not True
                )
            if not isinstance(text, str) or (secret and secret in text):
                raise ValueError("invalid or credential-bearing response")
            result: dict[str, Any] = json.loads(text)
            validate(batch, result)
            return result
        except ValueError, KeyError, TypeError, IndexError, RecursionError, AttributeError:
            raise ProviderFailure("PROVIDER_RESPONSE_INVALID") from None
