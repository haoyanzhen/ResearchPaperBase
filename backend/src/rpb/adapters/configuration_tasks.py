"""Route private task reads to their owning configuration store."""

from typing import Any

from rpb.adapters.llm import LLMStore
from rpb.adapters.sources import SourceStore
from rpb.modules.account_config.application.ports import AccountError


class ConfigurationTasks(LLMStore):
    def __init__(self, llm: LLMStore, sources: SourceStore) -> None:
        self.account, self.cipher = llm.account, llm.cipher
        self.llm, self.sources = llm, sources

    def invoke(
        self,
        operation: str,
        token: str,
        csrf: str | None,
        target: str | None,
        data: dict[str, Any],
        key: str | None,
        expected_actor: str | None = None,
    ) -> Any:
        try:
            return self.llm.invoke(operation, token, csrf, target, data, key, expected_actor)
        except AccountError as exc:
            if operation not in {"task", "result", "events"} or exc.status != 404:
                raise
        return self.sources.invoke(operation, token, csrf, target, data, key, expected_actor)
