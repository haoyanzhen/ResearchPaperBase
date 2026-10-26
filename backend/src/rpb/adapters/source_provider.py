"""Fixed, minimal source searches validate protocol, not a generic HTTP 200."""

from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from typing import Any
from xml.etree import ElementTree

from rpb.adapters.llm_provider import HTTPProvider, ProviderFailure


class SourceProvider(HTTPProvider):
    def execute(
        self,
        config: dict[str, Any],
        operation: str,
        model: str | None,
        secret: str,
        authorize: Callable[[], AbstractContextManager[None]] = nullcontext,
    ) -> dict[str, Any]:
        provider = config["provider"]
        paths = {
            "arxiv": "/query?search_query=all:electron&start=0&max_results=1",
            "openalex": "/works?search=electron&per_page=1",
            "semantic_scholar": "/paper/search?query=electron&limit=1&fields=title",
            "ads": "/search/query?q=title:electron&rows=1&fl=title",
        }
        if config["access_mode"] == "anonymous":
            secret = ""
        if config["access_mode"] == "api_key" and not secret:
            raise ProviderFailure("CONFIG_SECRET_UNAVAILABLE")
        value = self.request(
            config["base_url"],
            paths[provider],
            secret,
            "source_" + provider,
            "",
            None,
            30,
            authorize,
            response_format="xml" if provider == "arxiv" else "json",
        )
        valid = False
        if provider == "arxiv":
            try:
                document = value.decode("utf-8-sig")
                if "<!DOCTYPE" in document.upper() or "<!ENTITY" in document.upper():
                    raise ValueError()
                root = ElementTree.fromstring(document)
                total = root.find("{http://a9.com/-/spec/opensearch/1.1/}totalResults")
                valid = (
                    root.tag == "{http://www.w3.org/2005/Atom}feed"
                    and total is not None
                    and int(total.text or "-1") >= 0
                )
                valid = valid and not any(
                    "/api/errors" in (n.text or "")
                    for n in root.iter("{http://www.w3.org/2005/Atom}id")
                )
            except ValueError, UnicodeError, ElementTree.ParseError:
                valid = False
        elif isinstance(value, dict) and "error" not in value:
            if provider == "openalex":
                meta = value.get("meta", {})
                valid = (
                    isinstance(meta, dict)
                    and type(meta.get("count")) is int
                    and meta["count"] >= 0
                    and isinstance(value.get("results"), list)
                )
            elif provider == "semantic_scholar":
                valid = (
                    type(value.get("total")) is int
                    and value["total"] >= 0
                    and isinstance(value.get("data"), list)
                )
            else:
                response = value.get("response", {})
                valid = (
                    isinstance(response, dict)
                    and type(response.get("numFound")) is int
                    and response["numFound"] >= 0
                    and isinstance(response.get("docs"), list)
                )
        if not valid:
            raise ProviderFailure("PROVIDER_RESPONSE_INVALID")
        return {}
