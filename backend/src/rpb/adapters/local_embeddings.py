"""Private, bounded subprocess client for the separately installed offline E5 worker.

The caller supplies a current authorization context for each source read and
must revalidate the resulting dependencies before storing or publishing them.
"""

import hashlib
import json
import math
import os
import select
import subprocess
import threading
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any


class EmbeddingUnavailable(RuntimeError):
    pass


def valid_profile(profile: Any) -> bool:
    fixed = {
        "model_id": "intfloat/multilingual-e5-base",
        "weights_revision": "d128750597153bb5987e10b1c3493a34e5a4502a",
        "weights_digest": "a18a44fad1d0b46ded15928144138cff1135d5cc8233bdd90be5f18822de09a7",
        "tokenizer_revision": "721e17b7fb6b2a3388d0a9c6ff8a99784672cdacd98e2b6cb9cdab92237be08e",
        "dimension": 768,
        "normalization": "l2",
        "distance": "cosine",
        "query_prefix": "query: ",
        "passage_prefix": "passage: ",
    }
    if not isinstance(profile, dict) or set(profile) != set(fixed) | {
        "runtime_digest",
        "profile_id",
    }:
        return False
    if any(profile[key] != value for key, value in fixed.items()):
        return False
    for key in ("tokenizer_revision", "runtime_digest", "profile_id"):
        value = profile[key]
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)
        ):
            return False
    identity = {key: value for key, value in profile.items() if key != "profile_id"}
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return digest == str(profile["profile_id"])


class LocalEmbeddings:
    def __init__(
        self,
        command: list[str],
        environment: dict[str, str],
        permit: Callable[[], AbstractContextManager[Any]],
        expected_profile: dict[str, Any] | None = None,
        timeout: float = 120,
    ) -> None:
        self.timeout, self.permit = timeout, permit
        self.lock = threading.RLock()
        try:
            self.process = subprocess.Popen(
                command,
                env=environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0,
            )
        except OSError:
            raise EmbeddingUnavailable("embedding worker unavailable") from None
        try:
            assert self.process.stdin is not None
            os.set_blocking(self.process.stdin.fileno(), False)
            first = self._read()
            self.profile = first["profile"]
            if not valid_profile(self.profile) or (
                expected_profile is not None and self.profile != expected_profile
            ):
                raise EmbeddingUnavailable("embedding profile mismatch")
        except BaseException as error:
            self.close()
            if not isinstance(error, Exception):
                raise
            raise EmbeddingUnavailable("embedding worker unavailable") from None

    def _read(self) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout
        data = bytearray()
        assert self.process.stdout is not None
        fd = self.process.stdout.fileno()
        while len(data) <= 1_000_000:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([fd], [], [], remaining)[0]:
                raise EmbeddingUnavailable("embedding worker timed out")
            byte = os.read(fd, 1)
            if not byte:
                raise EmbeddingUnavailable("embedding worker closed")
            if byte == b"\n":
                result = json.loads(data)
                if not isinstance(result, dict) or "error" in result:
                    raise EmbeddingUnavailable("embedding worker rejected request")
                return result
            data.extend(byte)
        raise EmbeddingUnavailable("embedding response too large")

    def _request(self, kind: str, text: str) -> dict[str, Any]:
        request = json.dumps({"kind": kind, "text": text}, ensure_ascii=False).encode() + b"\n"
        if len(request) > 1_000_000:
            raise EmbeddingUnavailable("embedding request too large")
        with self.lock:
            try:
                with self.permit():
                    assert self.process.stdin is not None
                    fd = self.process.stdin.fileno()
                    deadline = time.monotonic() + self.timeout
                    sent = 0
                    while sent < len(request):
                        remaining = deadline - time.monotonic()
                        if remaining <= 0 or not select.select([], [fd], [], remaining)[1]:
                            raise EmbeddingUnavailable("embedding worker timed out")
                        sent += os.write(fd, request[sent:])
                return self._read()
            except BaseException as error:
                self.close()
                if not isinstance(error, PermissionError) and isinstance(
                    error, (OSError, ValueError, TypeError, EmbeddingUnavailable)
                ):
                    raise EmbeddingUnavailable("embedding request failed") from None
                raise

    def offsets(self, text: str) -> list[tuple[int, int]]:
        value = self._request("tokenize", text)
        try:
            spans = value["offsets"]
            if not isinstance(spans, list) or any(
                not isinstance(span, list)
                or len(span) != 2
                or any(type(part) is not int for part in span)
                for span in spans
            ):
                raise ValueError("invalid offsets")
            return [(span[0], span[1]) for span in spans]
        except KeyError, TypeError, ValueError:
            self.close()
            raise EmbeddingUnavailable("invalid tokenizer output") from None

    def passage_length(self, text: str) -> int:
        value = self._request("tokenize", text)
        length = value.get("passage_length")
        if type(length) is not int or length < 0:
            self.close()
            raise EmbeddingUnavailable("invalid tokenizer length")
        return length

    def embed(self, text: str) -> list[float]:
        value = self._request("passage", text).get("vector")
        try:
            invalid = (
                not isinstance(value, list)
                or len(value) != 768
                or any(type(x) not in (int, float) or not math.isfinite(x) for x in value)
                or abs(sum(x * x for x in value) - 1) > 0.0001
            )
        except OverflowError:
            invalid = True
        if invalid or not isinstance(value, list):
            self.close()
            raise EmbeddingUnavailable("invalid embedding output")
        return value

    def close(self) -> None:
        with self.lock:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            for stream in (self.process.stdin, self.process.stdout):
                if stream:
                    stream.close()

    def __enter__(self) -> LocalEmbeddings:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
