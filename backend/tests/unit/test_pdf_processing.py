"""Requirement-derived real PDF extraction, source ordering and parser isolation."""

import io
from contextlib import nullcontext

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from rpb.adapters.llm_provider import ProviderFailure
from rpb.adapters.pdf_processing import PDFProvider, isolated, parse_pdf


def sample(text="First source evidence", encrypted=False, blank=False):
    writer = PdfWriter()
    page = writer.add_blank_page(612, 792)
    if not blank:
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        stream = DecodedStreamObject()
        stream.set_data(("BT /F1 12 Tf 72 720 Td (" + text + ") Tj ET").encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("secret")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def test_pp01_real_pdf_text_page_and_failure_states():
    result = parse_pdf(sample())
    assert result["reason"] is None, result
    assert "First source evidence" in result["text"]
    assert result["segments"][0]["page"] == 1
    assert result["segments"][0]["end_offset"] == len(result["text"])
    assert parse_pdf(sample(encrypted=True))["reason"] == "encrypted_content"
    assert parse_pdf(sample(blank=True))["reason"] == "no_usable_text"
    assert parse_pdf(b"%PDF-corrupt")["reason"] == "corrupt_content"
    assert parse_pdf(b"<html>not PDF</html>")["text"] is None


def test_pp02_os_sandbox_denies_network_secrets_and_other_files(tmp_path, monkeypatch):
    marker = tmp_path / "private-project"
    marker.write_text("not permitted")
    monkeypatch.setenv("RPB_SECRET", "do not inherit")
    script = """import json,os,socket,sys
from pathlib import Path
result={"env": os.environ.get("RPB_SECRET"), "read": False, "network": False}
try:
 Path(MARKER).read_text();result["read"]=True
except PermissionError: pass
try:
 socket.socket().connect(("127.0.0.1",1));result["network"]=True
except PermissionError: pass
Path(sys.argv[2]).write_text(json.dumps(result))
""".replace("MARKER", repr(str(marker)))
    assert isolated(script, b"input") == {"env": None, "read": False, "network": False}


class Files(PDFProvider):
    def __init__(self, replies):
        self.replies, self.calls = replies, []

    def download(self, link, authorize):
        with authorize():
            self.calls.append(link)
        reply = self.replies[link]
        if isinstance(reply, Exception):
            raise reply
        return reply


def sources():
    return [
        dict(
            id=str(i),
            metadata={"url": "https://example.org/" + str(i), "abstract": "Abstract " + str(i)},
            source={},
        )
        for i in range(3)
    ]


def test_pp03_later_fulltext_precedes_early_abstract_and_stops_after_first_fulltext():
    provider = Files(
        {
            "https://example.org/0": b"%PDF-bad",
            "https://example.org/1": sample("Second source"),
            "https://example.org/2": sample("Third source"),
        }
    )
    result = provider.prepare(sources(), nullcontext)
    assert result["source_id"] == "1" and result["kind"] == "full_text"
    assert "Second source" in result["text"]
    assert provider.calls == ["https://example.org/0", "https://example.org/1"]
    assert result["diagnostics"][0]["reason"] == "corrupt_content"


def test_pp04_real_first_nonempty_abstract_only_after_all_fulltext_fail():
    values = sources()
    values[0]["metadata"]["abstract"] = " "
    provider = Files({s["metadata"]["url"]: ProviderFailure("PROVIDER_TIMEOUT") for s in values})
    result = provider.prepare(values, nullcontext)
    assert len(provider.calls) == 3
    assert result["text"] == "Abstract 1" and result["source_id"] == "1"
    assert result["raw"] is None
    for value in values:
        value["metadata"]["abstract"] = None
    assert provider.prepare(values, nullcontext)["text"] is None


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "http://user:pass@example.org/a", "https://example.org/#fragment"]
)
def test_pp05_bad_urls_never_dispatch(url):
    class HTTP:
        def request(self, *args, **kwargs):
            raise AssertionError("must not dispatch")

    with pytest.raises(ProviderFailure):
        PDFProvider(HTTP()).download(url, nullcontext)


def test_pp06_redirects_bounded_no_credentials_or_internal_allowlist():
    class HTTP:
        def __init__(self):
            self.calls = []

        def request(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return {"redirect": "https://other.example/pdf"}

    http = HTTP()
    with pytest.raises(ProviderFailure):
        PDFProvider(http).download("https://example.org/a", nullcontext)
    assert len(http.calls) == 4
    assert all(a[2] == "" and k["response_format"] == "pdf" for a, k in http.calls)


def test_pp07_actual_wall_and_memory_limits(monkeypatch):
    from rpb.adapters import pdf_processing as module

    monkeypatch.setattr(module, "PARSER_TIMEOUT", 0.2)
    assert isolated("while True: pass", b"input")["reason"] == "safety_limit"
    monkeypatch.setattr(module, "PARSER_TIMEOUT", 5)
    monkeypatch.setattr(module, "PARSER_RSS_KIB", 65536)
    assert (
        isolated(
            "import time\na=[]\nwhile True:\n a.append(bytearray(10_000_000));time.sleep(0.02)",
            b"input",
        )["reason"]
        == "safety_limit"
    )


@pytest.mark.parametrize("address", ["127.0.0.1", "169.254.169.254", "::1", "10.0.0.1"])
def test_pp08_actual_http_transport_rejects_nonpublic_and_provider_allowlist(monkeypatch, address):
    import socket

    from rpb.adapters import llm_provider

    monkeypatch.setattr(
        llm_provider,
        "resolve_addresses",
        lambda *args: [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (address, 443))],
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("must not connect")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    http = llm_provider.HTTPProvider(frozenset({("example.org", 443)}))
    with pytest.raises(ProviderFailure):
        http.request(
            "https://example.org",
            "/paper",
            "",
            "public_document",
            "",
            None,
            30,
            response_format="pdf",
        )


def test_pp09_pdf_file_limit_and_text_limit_are_failures_not_truncation():
    assert parse_pdf(b"%PDF-" + bytes(52_428_800))["reason"] == "safety_limit"
    result = parse_pdf(sample("a" * 200_001))
    assert result["reason"] == "safety_limit" and result["text"] is None


def test_pp23_real_unicode_multipage_ranges_and_newlines():
    writer = PdfWriter()
    cmap = DecodedStreamObject()
    cmap.set_data(
        b"1 begincodespacerange <00> <FF> endcodespacerange "
        b"2 beginbfchar <41> <4E2D> <42> <6587> endbfchar"
    )
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
            NameObject("/ToUnicode"): writer._add_object(cmap),
        }
    )
    for _ in range(2):
        page = writer.add_blank_page(612, 792)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        stream = DecodedStreamObject()
        stream.set_data(b"BT /F1 12 Tf 72 720 Td (AB) Tj ET")
        page[NameObject("/Contents")] = writer._add_object(stream)
    out = io.BytesIO()
    writer.write(out)
    result = parse_pdf(out.getvalue())
    assert result["text"] == "中文" + chr(10) + "中文" + chr(10)
    assert result["segments"] == [
        dict(start_offset=0, end_offset=3, page=1),
        dict(start_offset=3, end_offset=6, page=2),
    ]


def test_pp24_missing_isolation_runtime_does_not_parse_in_process(monkeypatch):
    from rpb.adapters import pdf_processing

    monkeypatch.setattr(pdf_processing.sys, "platform", "unsupported")
    assert parse_pdf(sample()) == dict(reason="parser_unavailable", text=None, segments=[])


@pytest.mark.parametrize("bad", ["https://example.org:bad/paper", "https://[broken/paper"])
def test_pp27_bad_metadata_url_preserves_other_sources_and_abstract(bad):
    values = sources()
    values[0]["metadata"]["url"] = bad

    class HTTP:
        def request(self, *args, **kwargs):
            raise ValueError("invalid port or host")

    result = PDFProvider(HTTP()).prepare(values, nullcontext)
    assert result["text"] == "Abstract 0"
    assert result["kind"] == "abstract_fallback"
    assert len(result["diagnostics"]) == 3


@pytest.mark.parametrize("mode", ["redirect_private", "oversized"])
def test_pp28_pdf_transport_pins_dns_rechecks_redirect_and_bounds_stream(monkeypatch, mode):
    import socket

    from rpb.adapters import llm_provider as transport

    dns, connected, requests = [], [], []

    def resolve(host, port, deadline):
        dns.append(host)
        address = "127.0.0.1" if host == "private.invalid" else "8.8.8.8"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]

    class Sock:
        def settimeout(self, value):
            pass

        def shutdown(self, value):
            pass

        def close(self):
            pass

    def connect(address, *args):
        connected.append(address)
        return Sock()

    class Reply:
        status = 302 if mode == "redirect_private" else 200

        def getheader(self, name):
            return "http://private.invalid/paper"

        def read(self, limit):
            assert limit == 52_428_801
            return bytes(limit)

    class Connection:
        def __init__(self, host, port, timeout):
            self.host, self.port, self.timeout, self.sock = host, port, timeout, None

        def connect(self):
            self.sock = self._create_connection((self.host, self.port), self.timeout)

        def request(self, *args, **kwargs):
            requests.append((args, kwargs))

        def getresponse(self):
            return Reply()

        def close(self):
            pass

    monkeypatch.setattr(transport, "resolve_addresses", resolve)
    monkeypatch.setattr(socket, "create_connection", connect)
    monkeypatch.setattr(transport.http.client, "HTTPConnection", Connection)
    with pytest.raises(ProviderFailure):
        PDFProvider().download("http://public.invalid/paper?token=sensitive", nullcontext)
    assert connected == [("8.8.8.8", 80)]
    assert len(requests) == 1
    assert requests[0][1]["headers"] == {"Accept": "application/pdf"}
    assert dns == (
        ["public.invalid", "private.invalid"] if mode == "redirect_private" else ["public.invalid"]
    )
