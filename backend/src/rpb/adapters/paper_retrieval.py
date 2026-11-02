"""Bounded paper searches; remote payloads stay untrusted until normalized."""

from datetime import UTC
from time import sleep
from typing import Any
from urllib.parse import urlencode
from xml.etree import ElementTree as ET

from rpb.adapters.llm_provider import HTTPProvider, ProviderFailure
from rpb.modules.construction.domain.runs import instant


def text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


class PaperRetrieval:
    def __init__(self, http: HTTPProvider | None = None) -> None:
        self.http = http or HTTPProvider()

    def search(
        self, config: Any, secret: Any, query: str, window: Any, limit: int, authorize: Any
    ) -> Any:
        provider = config["provider"]
        rows: list[dict[str, Any]] = []
        offset, skipped = 0, 0
        cursor = "*"
        seen_cursors = {cursor}
        seen_ids: set[str] = set()
        first_total = None
        consistent = True
        identifiable = True
        lower, upper = instant(window["published_from"]), instant(window["published_until"])
        while len(rows) < limit:
            count = min(100, limit - len(rows))
            fields = "title,abstract,authors,year,publicationDate,externalIds,url"
            params: dict[str, Any]
            if provider == "arxiv":
                params = {
                    "search_query": query,
                    "start": offset,
                    "max_results": count,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                }
                path = "/query"
            elif provider == "openalex":
                params = {"search": query, "per_page": count, "cursor": cursor}
                filters = []
                if lower:
                    filters.append(
                        "from_publication_date:" + lower.astimezone(UTC).date().isoformat()
                    )
                if upper:
                    filters.append(
                        "to_publication_date:" + upper.astimezone(UTC).date().isoformat()
                    )
                if filters:
                    params["filter"] = ",".join(filters)
                path = "/works"
            elif provider == "semantic_scholar":
                params = {"query": query, "offset": offset, "limit": count, "fields": fields}
                if lower or upper:
                    params["publicationDateOrYear"] = (
                        (lower.date().isoformat() if lower else "")
                        + ":"
                        + (upper.date().isoformat() if upper else "")
                    )
                path = "/paper/search"
            else:
                params = {
                    "q": query,
                    "start": offset,
                    "rows": count,
                    "fl": "bibcode,title,author,year,abstract,doi,pubdate,identifier",
                }
                path = "/search/query"
            for pacing_attempt in range(21):
                try:
                    current_secret = secret() if callable(secret) else secret
                    response = self.http.request(
                        config["base_url"],
                        path + "?" + urlencode(params),
                        current_secret if config["access_mode"] == "api_key" else "",
                        "source_" + provider,
                        "",
                        None,
                        30,
                        lambda: authorize(current_secret),
                        response_format="xml" if provider == "arxiv" else "json",
                    )
                    break
                except ProviderFailure as exc:
                    if (
                        exc.code != "PROVIDER_RATE_LIMITED"
                        or exc.submitted is not False
                        or pacing_attempt == 20
                    ):
                        raise
                    sleep(3)
            try:
                batch, total, next_cursor, complete = self.normalize(provider, response)
                if len(batch) > count or type(total) is not int or total < 0:
                    raise ValueError("size")
                if first_total is None:
                    first_total = total
                consistent = consistent and complete and total == first_total
                for item in batch:
                    identity = item["url"] or item["arxiv_id"] or item["doi"]
                    if not identity:
                        identifiable = False
                    elif identity in seen_ids:
                        consistent = False
                    else:
                        seen_ids.add(identity)
                    published = item.pop("published_at")
                    if lower or upper:
                        if not published:
                            skipped += 1
                            continue
                        at = instant(published)
                        if at is None or (lower and at < lower) or (upper and at >= upper):
                            skipped += 1
                            continue
                    if current_secret and current_secret in str(item):
                        raise ValueError("credential echo")
                    rows.append(item)
                offset += len(batch)
                if not batch or offset >= total or len(rows) >= limit:
                    break
                if offset >= 1000:
                    # Provider's bounded search window cannot prove further coverage.
                    return {
                        "items": rows,
                        "skipped_date": skipped,
                        "limited": True,
                        "exhausted": False,
                    }
                if provider == "openalex":
                    if not next_cursor or next_cursor in seen_cursors:
                        raise ValueError("cursor")
                    seen_cursors.add(next_cursor)
                    cursor = next_cursor
            except (
                ValueError,
                KeyError,
                TypeError,
                AttributeError,
                IndexError,
                UnicodeError,
                ET.ParseError,
            ):
                raise ProviderFailure("PROVIDER_RESPONSE_INVALID") from None
        limited = not consistent or offset != first_total or len(rows) == limit
        return {
            "items": rows,
            "skipped_date": skipped,
            "limited": limited,
            "exhausted": not limited and identifiable,
        }

    def normalize(self, provider: str, response: Any) -> Any:
        result = []
        cursor = None
        complete = True
        if provider == "arxiv":
            document = response.decode("utf-8-sig")
            if "<!DOCTYPE" in document.upper() or "<!ENTITY" in document.upper():
                raise ValueError("xml")
            root = ET.fromstring(document)
            ns = "{http://www.w3.org/2005/Atom}"
            if root.tag != ns + "feed":
                raise ValueError("feed")
            total = int(root.findtext("{http://a9.com/-/spec/opensearch/1.1/}totalResults", "-1"))
            if total == 0:
                complete = (
                    root.find(ns + "link[@rel='next']") is None
                    and root.findtext("{http://a9.com/-/spec/opensearch/1.1/}startIndex", "0")
                    == "0"
                )
            for entry in root.findall(ns + "entry"):
                url = entry.findtext(ns + "id")
                if not url or "/api/errors" in url:
                    raise ValueError("id")
                result.append(
                    {
                        "title": entry.findtext(ns + "title"),
                        "authors": [a.findtext(ns + "name") for a in entry.findall(ns + "author")],
                        "abstract": entry.findtext(ns + "summary"),
                        "url": url,
                        "arxiv_id": url.split("/abs/")[-1],
                        "doi": entry.findtext("{http://arxiv.org/schemas/atom}doi"),
                        "year": int(entry.findtext(ns + "published", "")[:4]),
                        "published_at": entry.findtext(ns + "published"),
                    }
                )
        else:
            if not isinstance(response, dict) or "error" in response:
                raise ValueError("response")
            if provider == "openalex":
                total, items = response["meta"]["count"], response["results"]
                cursor = response["meta"].get("next_cursor")
                complete = total != 0 or cursor is None
            elif provider == "semantic_scholar":
                total, items = response["total"], response["data"]
                complete = total != 0 or (
                    response.get("next") is None and response.get("offset", 0) == 0
                )
            else:
                page = response["response"]
                total, items = page["numFound"], page["docs"]
                header = response.get("responseHeader", {})
                complete = (
                    header.get("partialResults", False) is False
                    and header.get("status", 0) == 0
                    and page.get("numFoundExact", True) is True
                    and (total != 0 or page.get("start", 0) == 0)
                )
            if not isinstance(items, list):
                raise ValueError("items")
            for item in items:
                if provider == "openalex":
                    date = item.get("publication_date")
                    abstract = item.get("abstract_inverted_index")
                    words = {}
                    if isinstance(abstract, dict):
                        for word, positions in abstract.items():
                            for index in positions:
                                if type(index) is not int or not 0 <= index <= 100000:
                                    raise ValueError("abstract")
                                words[index] = word
                    result.append(
                        {
                            "title": item.get("title"),
                            "authors": [
                                a["author"]["display_name"] for a in item.get("authorships", [])
                            ],
                            "abstract": " ".join(words[i] for i in sorted(words)) or None,
                            "url": item.get("id"),
                            "doi": item.get("doi"),
                            "arxiv_id": None,
                            "year": item.get("publication_year"),
                            "published_at": date + "T00:00:00Z" if date else None,
                        }
                    )
                elif provider == "semantic_scholar":
                    date = item.get("publicationDate")
                    result.append(
                        {
                            "title": item.get("title"),
                            "authors": [a["name"] for a in item.get("authors", [])],
                            "abstract": item.get("abstract"),
                            "url": item.get("url"),
                            "doi": item.get("externalIds", {}).get("DOI"),
                            "arxiv_id": item.get("externalIds", {}).get("ArXiv"),
                            "year": item.get("year"),
                            "published_at": date + "T00:00:00Z" if date else None,
                        }
                    )
                else:
                    date = item.get("pubdate")
                    result.append(
                        {
                            "title": item["title"][0],
                            "authors": item.get("author", []),
                            "abstract": item.get("abstract"),
                            "url": "https://ui.adsabs.harvard.edu/abs/" + item["bibcode"],
                            "doi": next(iter(item.get("doi", [])), None),
                            "arxiv_id": None,
                            "year": int(item["year"]) if item.get("year") else None,
                            "published_at": date + "T00:00:00Z"
                            if date and "-00" not in date
                            else None,
                        }
                    )
        for item in result:
            if (
                not text(item["title"])
                or not isinstance(item["authors"], list)
                or any(not text(a) for a in item["authors"])
            ):
                raise ValueError("metadata")
            if item["year"] is not None and (
                type(item["year"]) is not int or not 1 <= item["year"] <= 9999
            ):
                raise ValueError("year")
            for key in ("title", "abstract", "url", "doi", "arxiv_id"):
                item[key] = text(item[key])
        return result, total, cursor, complete
