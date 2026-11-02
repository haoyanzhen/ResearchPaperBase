"""Provider boundary regression: malformed output, paging, dates and current credentials."""

from contextlib import nullcontext
from urllib.parse import parse_qs, urlsplit

import pytest

from rpb.adapters.llm_provider import ProviderFailure
from rpb.adapters.paper_retrieval import PaperRetrieval


class HTTP:
    def __init__(self, responses, hook=None):
        self.responses = iter(responses)
        self.calls = []
        self.hook = hook

    def request(self, base, path, secret, protocol, version, body, timeout, authorize, **kwargs):
        with authorize():
            self.calls.append((path, secret))
        result = next(self.responses)
        if self.hook:
            self.hook()
        return result


def search(http, provider="ads", window=None, limit=10, secret="", authorize=None):
    return PaperRetrieval(http).search(
        {
            "provider": provider,
            "base_url": "https://example.invalid",
            "access_mode": "api_key" if secret else "anonymous",
        },
        secret,
        "graph AND science",
        window or {"published_from": None, "published_until": None},
        limit,
        authorize or (lambda key: nullcontext()),
    )


def ads(title="Paper", date="2026-01-01"):
    return {"title": [title], "bibcode": "2026Paper", "year": "2026", "pubdate": date}


def test_cr_provider_malformed_ads_is_classified_not_worker_exception():
    for value in (
        {"response": {"numFound": 1, "docs": [{**ads(), "title": []}]}},
        {"response": {"numFound": 1, "docs": [{**ads(), "title": None}]}},
        {"response": {"numFound": -1, "docs": []}},
    ):
        with pytest.raises(ProviderFailure, match="PROVIDER_RESPONSE_INVALID"):
            search(HTTP([value]))


def test_cr_provider_openalex_paging_and_credential_rotation():
    current = ["old-key"]

    def item(index):
        return {
            "id": f"https://openalex.org/W{index}",
            "title": f"Paper {index}",
            "publication_year": 2026,
            "publication_date": "2026-01-01",
            "authorships": [],
            "abstract_inverted_index": {"paper": [0]},
        }

    http = HTTP(
        [
            {"meta": {"count": 2, "next_cursor": "page2"}, "results": [item(1)]},
            {"meta": {"count": 2, "next_cursor": None}, "results": [item(2)]},
        ],
        hook=lambda: current.__setitem__(0, "rotated-key"),
    )
    result = search(http, "openalex", limit=2, secret=lambda: current[0])
    assert [c[1] for c in http.calls] == ["old-key", "rotated-key"]
    assert parse_qs(urlsplit(http.calls[1][0]).query)["cursor"] == ["page2"]
    assert [r["title"] for r in result["items"]] == ["Paper 1", "Paper 2"]


def test_cr_provider_local_pacing_before_send_retries_same_page(monkeypatch):
    sleeps = []
    monkeypatch.setattr("rpb.adapters.paper_retrieval.sleep", sleeps.append)
    attempts = []

    def authorize(secret):
        attempts.append(secret)
        if len(attempts) == 1:
            raise ProviderFailure("PROVIDER_RATE_LIMITED", submitted=False)
        return nullcontext()

    http = HTTP([{"response": {"numFound": 1, "docs": [ads()]}}])
    assert len(search(http, authorize=authorize)["items"]) == 1
    assert len(http.calls) == 1 and sleeps == [3]


def test_cr_provider_remote_rate_limit_not_implicitly_retried():
    class Remote(HTTP):
        def request(self, *args, **kwargs):
            raise ProviderFailure("PROVIDER_RATE_LIMITED")

    with pytest.raises(ProviderFailure):
        search(Remote([]))


def test_cr_provider_half_open_window_and_unknown_dates():
    http = HTTP(
        [
            {
                "response": {
                    "numFound": 3,
                    "docs": [
                        ads("before", "2025-12-31"),
                        ads("inside"),
                        ads("upper", "2026-01-02"),
                    ],
                }
            }
        ]
    )
    result = search(
        http,
        window={
            "published_from": "2026-01-01T00:00:00Z",
            "published_until": "2026-01-02T00:00:00Z",
        },
    )
    assert [r["title"] for r in result["items"]] == ["inside"]
    assert result["skipped_date"] == 2


def test_cr_provider_semantic_scholar_metadata_and_arxiv_xml():
    http = HTTP(
        [
            {
                "total": 1,
                "data": [
                    {
                        "title": "Semantic",
                        "authors": [{"name": "A"}],
                        "year": 2026,
                        "publicationDate": "2026-01-01",
                        "externalIds": {"DOI": "10.1/example", "ArXiv": "2601.1"},
                    }
                ],
            }
        ]
    )
    assert search(http, "semantic_scholar")["items"][0]["doi"] == "10.1/example"
    feed = b"""<feed xmlns="http://www.w3.org/2005/Atom" xmlns:o="http://a9.com/-/spec/opensearch/1.1/"><o:totalResults>1</o:totalResults><entry><id>https://arxiv.org/abs/2601.1</id><title>Arxiv</title><published>2026-01-01T00:00:00Z</published><author><name>A</name></author><summary>Abstract</summary></entry></feed>"""
    assert search(HTTP([feed]), "arxiv")["items"][0]["arxiv_id"] == "2601.1"
    with pytest.raises(ProviderFailure):
        search(HTTP([b"<!DOCTYPE feed><feed/>"]), "arxiv")


@pytest.mark.parametrize(
    "pages",
    [
        [(2, [ads()]), (2, [])],
        [(2, [ads()]), (1, [])],
        [(0, [ads()])],
        [(2, [ads()]), (2, [ads()])],
    ],
)
def test_inconsistent_paging_keeps_results_without_proving_exhaustion(pages):
    http = HTTP([{"response": {"numFound": total, "docs": docs}} for total, docs in pages])
    result = search(http)
    assert result["items"]
    assert result["limited"] is True
    assert result["exhausted"] is False


def test_paging_exhaustion_requires_a_consistent_complete_window():
    first = ads()
    second = ads("Second") | {"bibcode": "2026Other"}
    result = search(
        HTTP([{"response": {"numFound": 2, "docs": [item]}} for item in (first, second)])
    )
    assert not result["limited"] and result["exhausted"] is True


def test_unidentified_row_preserves_result_without_attesting_pagination():
    http = HTTP([{"total": 1, "data": [{"title": "No external ID", "authors": []}]}])
    result = search(http, "semantic_scholar")
    assert [row["title"] for row in result["items"]] == ["No external ID"]
    assert result["limited"] is False and result["exhausted"] is False


EMPTY_ARXIV_FEED = (
    b'<feed xmlns="http://www.w3.org/2005/Atom" '
    b'xmlns:o="http://a9.com/-/spec/opensearch/1.1/">'
    b"<o:totalResults>0</o:totalResults>"
)


@pytest.mark.parametrize(
    "provider,response",
    [
        ("ads", {"response": {"numFound": 0, "docs": []}}),
        ("semantic_scholar", {"total": 0, "data": []}),
        ("openalex", {"meta": {"count": 0, "next_cursor": None}, "results": []}),
        (
            "arxiv",
            EMPTY_ARXIV_FEED + b"</feed>",
        ),
    ],
)
def test_empty_search_attests_only_exhausted_pages(provider, response):
    assert search(HTTP([response]), provider) == {
        "items": [],
        "limited": False,
        "exhausted": True,
        "skipped_date": 0,
    }


def test_empty_page_with_outstanding_hits_is_incomplete():
    result = search(HTTP([{"response": {"numFound": 1, "docs": []}}]))
    assert not result["items"] and result["limited"] and not result["exhausted"]


@pytest.mark.parametrize(
    "provider,response",
    [
        (
            "ads",
            {"responseHeader": {"partialResults": True}, "response": {"numFound": 0, "docs": []}},
        ),
        ("ads", {"response": {"numFound": 0, "numFoundExact": False, "docs": []}}),
        ("openalex", {"meta": {"count": 0, "next_cursor": "more"}, "results": []}),
        ("semantic_scholar", {"total": 0, "next": 1, "data": []}),
        (
            "arxiv",
            EMPTY_ARXIV_FEED + b'<link rel="next" href="more"/></feed>',
        ),
    ],
)
def test_conflicting_empty_provider_page_cannot_prove_zero(provider, response):
    result = search(HTTP([response]), provider)
    assert result["items"] == [] and result["limited"] and not result["exhausted"]
