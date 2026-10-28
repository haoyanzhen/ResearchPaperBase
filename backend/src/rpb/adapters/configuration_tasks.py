"""Route private task reads to their owning configuration store."""

from typing import Any

from rpb.adapters.llm import LLMStore
from rpb.adapters.runs import RunStore
from rpb.adapters.search_terms import TermStore
from rpb.adapters.smtp import SMTPStore
from rpb.adapters.sources import SourceStore
from rpb.modules.account_config.application.ports import AccountError


class ConfigurationTasks(LLMStore):
    def __init__(
        self,
        llm: LLMStore,
        sources: SourceStore,
        smtp: SMTPStore | None = None,
        terms: TermStore | None = None,
        runs: RunStore | None = None,
    ) -> None:
        self.account, self.cipher = llm.account, llm.cipher
        self.llm, self.sources = llm, sources
        self.terms = terms
        self.runs = runs
        self.smtp = smtp or SMTPStore(llm.account)
        self.system_sources = SourceStore(llm.account, system=True)
        self.system_llm = LLMStore(llm.account, system=True)

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
        try:
            return self.sources.invoke(operation, token, csrf, target, data, key, expected_actor)
        except AccountError as exc:
            if exc.status != 404:
                raise
        try:
            return self.system_llm.invoke(operation, token, csrf, target, data, key, expected_actor)
        except AccountError as exc:
            if exc.status != 404:
                raise
        try:
            return self.system_sources.invoke(
                operation, token, csrf, target, data, key, expected_actor
            )
        except AccountError as exc:
            if exc.status != 404:
                raise
        try:
            return self.smtp.invoke(operation, token, csrf, target, data, key, expected_actor)
        except AccountError as exc:
            if exc.status != 404 or self.terms is None:
                raise
        try:
            return self.terms.invoke(operation, token, csrf, target, data, key, expected_actor)
        except AccountError as exc:
            if exc.status != 404 or self.runs is None:
                raise
        return self.runs.invoke(operation, token, csrf, target, data, key, expected_actor)
