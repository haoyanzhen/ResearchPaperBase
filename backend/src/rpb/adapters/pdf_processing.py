"""Bounded public PDF acquisition and OS-isolated static text extraction."""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from time import monotonic
from typing import Any
from urllib.parse import urljoin, urlsplit

from rpb.adapters.llm_provider import HTTPProvider, ProviderFailure
from rpb.adapters.pdf_container import container_extract
from rpb.adapters.pdf_engines import extraction_script

FILE_LIMIT = 52_428_800
TEXT_LIMIT = 200_000
PARSER_TIMEOUT = 20
PARSER_RSS_KIB = 262144


def isolated(script: str, raw: bytes, *, runner: str = "auto") -> dict[str, Any]:
    if runner not in {"auto", "seatbelt", "docker"}:
        raise ValueError("Unknown PDF isolation runner")
    if runner == "docker" or (runner == "auto" and sys.platform in {"win32", "linux"}):
        return container_extract(script, raw, timeout=PARSER_TIMEOUT, memory_kib=PARSER_RSS_KIB)
    return seatbelt_extract(script, raw)


def seatbelt_extract(script: str, raw: bytes) -> dict[str, Any]:
    if sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").is_file():
        return {"reason": "parser_unavailable", "text": None, "segments": []}
    with tempfile.TemporaryDirectory(prefix="rpb-pdf-") as directory:
        root = Path(directory).resolve()
        source, output = root / "input.pdf", root / "output.json"
        source.write_bytes(raw)
        runtime = {str(Path(sys.prefix).resolve()), str(Path(sys.base_prefix).resolve())}
        rules = [
            "(version 1)",
            "(deny default)",
            "(allow process-exec)",
            "(allow sysctl-read)",
            "(allow file-read-metadata)",
            '(allow file-read* (literal "/") (subpath "/usr") (subpath "/System") '
            '(subpath "/Library/Apple") (subpath "/opt/homebrew/Cellar") '
            '(subpath "/opt/homebrew/opt") (subpath "/opt/homebrew/lib") (literal "/dev/null") '
            '(literal "/dev/urandom") (literal "/dev/random"))',
        ]
        for path in sorted(runtime | {str(root)}):
            rules.append("(allow file-read* (subpath " + json.dumps(path) + "))")
        rules.append("(allow file-write* (subpath " + json.dumps(str(root)) + "))")
        try:
            process = subprocess.Popen(
                [
                    "/usr/bin/sandbox-exec",
                    "-p",
                    "\n".join(rules),
                    sys.executable,
                    "-I",
                    "-B",
                    "-c",
                    script,
                    str(source),
                    str(output),
                ],
                cwd=root,
                env={"PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8"},
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            deadline = monotonic() + PARSER_TIMEOUT
            try:
                while process.poll() is None:
                    if monotonic() >= deadline:
                        process.kill()
                        break
                    rss = subprocess.run(
                        ["/bin/ps", "-o", "rss=", "-p", str(process.pid)],
                        capture_output=True,
                        text=True,
                        timeout=1,
                    )
                    if rss.stdout.strip() and int(rss.stdout.strip()) > PARSER_RSS_KIB:
                        process.kill()
                        break
                    try:
                        process.wait(timeout=0.05)
                    except subprocess.TimeoutExpired:
                        pass
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()
            if process.returncode or not output.is_file() or output.stat().st_size > 2_000_000:
                return {"reason": "safety_limit", "text": None, "segments": []}
            result: dict[str, Any] = json.loads(output.read_text())
            return result
        except OSError, ValueError, subprocess.TimeoutExpired:
            return {"reason": "safety_limit", "text": None, "segments": []}


def parse_pdf(raw: bytes, *, engine: str = "pypdf", runner: str = "auto") -> dict[str, Any]:
    script = extraction_script(engine)
    if len(raw) > FILE_LIMIT:
        return {"reason": "safety_limit", "text": None, "segments": []}
    if not raw.startswith(b"%PDF-"):
        return {"reason": "corrupt_content", "text": None, "segments": []}
    result = isolated(script, raw, runner=runner)
    rejected: dict[str, Any] = {"reason": "safety_limit", "text": None, "segments": []}
    if not isinstance(result, dict):
        return rejected
    reason, text, segments = result.get("reason"), result.get("text"), result.get("segments")
    if isinstance(reason, str) and reason in {
        "safety_limit",
        "parser_unavailable",
        "corrupt_content",
        "encrypted_content",
        "no_usable_text",
    }:
        return {"reason": reason, "text": None, "segments": []}
    if (
        reason is not None
        or not isinstance(text, str)
        or not text.strip()
        or len(text) > TEXT_LIMIT
    ):
        return rejected
    if not isinstance(segments, list) or not 1 <= len(segments) <= 2000:
        return rejected
    end, page = 0, 0
    for segment in segments:
        if not isinstance(segment, dict) or any(
            type(segment.get(key)) is not int for key in ("start_offset", "end_offset", "page")
        ):
            return rejected
        if not (
            segment["start_offset"] == end < segment["end_offset"] <= len(text)
            and page < segment["page"] <= 2000
        ):
            return rejected
        end, page = segment["end_offset"], segment["page"]
    if end != len(text):
        return rejected
    return {"reason": None, "text": text, "segments": segments}


def urls(metadata: Any) -> list[str]:
    values = []
    arxiv = metadata.get("arxiv_id")
    if isinstance(arxiv, str) and re.fullmatch(r"(?:\d{4}\.\d{4,5}|[a-z-]+/\d{7})(?:v\d+)?", arxiv):
        values.append("https://arxiv.org/pdf/" + arxiv)
    if metadata.get("url"):
        values.append(metadata["url"])
    return list(dict.fromkeys(values))


class PDFProvider:
    engine = "pypdf"
    runner = "auto"

    def __init__(
        self, http: HTTPProvider | None = None, *, engine: str = "pypdf", runner: str | None = None
    ) -> None:
        extraction_script(engine)
        self.engine = engine
        self.runner = runner if runner is not None else os.environ.get("RPB_PDF_RUNNER", "auto")
        if self.runner not in {"auto", "seatbelt", "docker"}:
            raise ValueError("Unknown PDF isolation runner")
        # PDF requests never inherit a Provider's private-network allowlist or credentials.
        self.http = http or HTTPProvider()

    def prepare(self, sources: list[Any], authorize: Any) -> Any:
        diagnostics = []
        fallback_file = None
        for source in sources:
            links = urls(source["metadata"])
            if not links:
                diagnostics.append({"source_id": source["id"], "reason": "source_unavailable"})
            for link in links:
                try:
                    raw = self.download(link, authorize)
                    parsed = parse_pdf(raw, engine=self.engine, runner=self.runner)
                except ProviderFailure, ValueError:
                    diagnostics.append({"source_id": source["id"], "reason": "source_unavailable"})
                    continue
                if parsed["text"]:
                    return {
                        **parsed,
                        "raw": raw,
                        "source_id": source["id"],
                        "kind": "full_text",
                        "diagnostics": diagnostics,
                    }
                if fallback_file is None and parsed["reason"] in {
                    "encrypted_content",
                    "no_usable_text",
                }:
                    fallback_file = {"raw": raw, "source_id": source["id"]}
                diagnostics.append({"source_id": source["id"], "reason": parsed["reason"]})
        for source in sources:
            abstract = source["metadata"].get("abstract")
            if isinstance(abstract, str) and abstract.strip():
                return {
                    "text": abstract,
                    "raw": None,
                    "source_id": source["id"],
                    "kind": "abstract_fallback",
                    "fallback_file": fallback_file,
                    "segments": [],
                    "diagnostics": diagnostics,
                }
        return {
            "text": None,
            "raw": None,
            "source_id": None,
            "fallback_file": fallback_file,
            "kind": None,
            "segments": [],
            "diagnostics": diagnostics,
        }

    def download(self, link: str, authorize: Any) -> bytes:
        for _ in range(4):
            url = urlsplit(link)
            if (
                url.scheme not in {"http", "https"}
                or not url.hostname
                or url.username
                or url.password
                or url.fragment
            ):
                raise ProviderFailure("CONFIG_CONNECTION_FAILED")
            result = self.http.request(
                url.scheme + "://" + url.netloc,
                url.path + ("?" + url.query if url.query else ""),
                "",
                "public_document",
                "",
                None,
                30,
                authorize,
                response_format="pdf",
            )
            if isinstance(result, bytes):
                return result
            link = urljoin(link, result["redirect"])
        raise ProviderFailure("CONFIG_CONNECTION_FAILED")
