"""SMTP port keeps HTTP delivery independent from persistence adapters."""

from typing import Protocol

from rpb.modules.account_config.application.llm import LLMPort


class SMTPPort(LLMPort, Protocol):
    def callback(self, token: str, state: str, code: str | None, denied: bool = False) -> bool: ...
