"""Registered source protocols; resource URLs are not configuration fields."""

from typing import Any, NoReturn
from urllib.parse import urlsplit


class SourceError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


PROVIDERS: dict[str, Any] = {
    "arxiv": {"url": "https://export.arxiv.org/api", "modes": {"anonymous"}, "rpm": 20},
    "openalex": {"url": "https://api.openalex.org", "modes": {"anonymous", "api_key"}, "rpm": 60},
    "semantic_scholar": {
        "url": "https://api.semanticscholar.org/graph/v1",
        "modes": {"anonymous", "api_key"},
        "rpm": 60,
    },
    "ads": {"url": "https://api.adsabs.harvard.edu/v1", "modes": {"api_key"}, "rpm": 60},
}


def validate_source(data: dict[str, Any]) -> dict[str, Any]:
    result = {k: v for k, v in data.items() if k not in {"secret", "expected_revision"}}
    if set(result) - {
        "name",
        "provider",
        "base_url",
        "access_mode",
        "enabled",
        "rate_limit_per_minute",
    }:
        raise SourceError("VALIDATION_UNKNOWN_FIELD")

    def invalid() -> NoReturn:
        raise SourceError("VALIDATION_FIELD_INVALID")

    if not isinstance(result.get("name"), str) or not 1 <= len(result["name"].strip()) <= 200:
        invalid()
    result["name"] = result["name"].strip()
    provider = result.get("provider")
    if not isinstance(provider, str) or provider not in PROVIDERS:
        invalid()
    if result.get("access_mode") not in PROVIDERS[provider]["modes"]:
        invalid()
    url = result.get("base_url")
    if not isinstance(url, str) or len(url) > 2048:
        invalid()
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.netloc.endswith(":")
        ):
            invalid()
        parsed.port
    except ValueError:
        invalid()
    result["base_url"] = url.rstrip("/")
    result.setdefault("enabled", True)
    result.setdefault("rate_limit_per_minute", None)
    if type(result["enabled"]) is not bool:
        invalid()
    rate = result["rate_limit_per_minute"]
    if rate is not None and (type(rate) is not int or rate < 1 or rate > 2147483647):
        invalid()
    return result
