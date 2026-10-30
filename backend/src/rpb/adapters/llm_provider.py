"""Bounded HTTP adapter with DNS pinning, no redirects and explicit internal targets."""

import http.client
import ipaddress
import json
import socket
import ssl
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from queue import Empty, Queue
from threading import BoundedSemaphore, Event, Thread, Timer
from time import monotonic
from typing import Any
from urllib.parse import quote, urlsplit

from rpb.modules.account_config.domain.llm_profiles import compile_for_model


class ProviderFailure(Exception):
    def __init__(self, code: str, *, submitted: bool | None = None) -> None:
        self.code = code
        self.submitted = submitted
        self.attempts = 1
        super().__init__(code)


_DNS_SLOTS = BoundedSemaphore(4)


def resolve_addresses(host: str, port: int, deadline: float) -> Any:
    # OS resolution itself is not cancellable. Bound both caller wait and the number
    # of detached resolver threads; none receives credentials or sends API requests.
    if not _DNS_SLOTS.acquire(blocking=False):
        raise ProviderFailure("PROVIDER_UNAVAILABLE")
    result: Queue[tuple[bool, Any]] = Queue(maxsize=1)

    def resolve() -> None:
        try:
            result.put((True, socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)))
        except Exception:
            result.put((False, None))
        finally:
            _DNS_SLOTS.release()

    Thread(target=resolve, daemon=True).start()
    try:
        success, addresses = result.get(timeout=max(0, deadline - monotonic()))
    except Empty:
        raise ProviderFailure("PROVIDER_TIMEOUT") from None
    if not success:
        raise ProviderFailure("CONFIG_CONNECTION_FAILED")
    return addresses


class HTTPProvider:
    def __init__(self, allowed_internal: frozenset[tuple[str, int]] = frozenset()) -> None:
        self.allowed_internal = allowed_internal

    def request(
        self,
        base_url: str,
        path: str,
        secret: str,
        protocol: str,
        api_version: str,
        payload: dict[str, Any] | None,
        timeout: int,
        authorize: Callable[[], AbstractContextManager[None]] = nullcontext,
        response_format: str = "json",
    ) -> Any:
        deadline = monotonic() + timeout
        submitted = False
        url = urlsplit(base_url)
        host = url.hostname or ""
        port = url.port or (443 if url.scheme == "https" else 80)
        internal = (host, port) in self.allowed_internal and response_format != "pdf"
        if (
            url.scheme != "https"
            and not internal
            and not (response_format == "pdf" and url.scheme == "http")
        ):
            raise ProviderFailure("CONFIG_CONNECTION_FAILED")
        try:
            try:
                addresses = resolve_addresses(host, port, deadline)
            except ProviderFailure as exc:
                if exc.code in {"CONFIG_CONNECTION_FAILED", "PROVIDER_TIMEOUT"}:
                    exc.submitted = False
                raise
            if not addresses or (
                not internal and any(not ipaddress.ip_address(x[4][0]).is_global for x in addresses)
            ):
                raise ProviderFailure("CONFIG_CONNECTION_FAILED")
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise ProviderFailure("PROVIDER_TIMEOUT")
            pinned = str(addresses[0][4][0])
            connection: http.client.HTTPConnection
            if url.scheme == "https":
                connection = http.client.HTTPSConnection(
                    host, port, timeout=remaining, context=ssl.create_default_context()
                )
            else:
                connection = http.client.HTTPConnection(host, port, timeout=remaining)

            sockets: list[socket.socket] = []

            # HTTPSConnection retains the hostname for SNI and certificate checks; TCP uses
            # exactly the previously checked address, preventing a second DNS lookup.
            def connect(
                address: Any, timeout: Any = None, source_address: Any = None
            ) -> socket.socket:
                left = deadline - monotonic()
                if left <= 0:
                    raise TimeoutError()
                sock = socket.create_connection((pinned, port), min(timeout, left), source_address)
                left = deadline - monotonic()
                if left <= 0:
                    sock.close()
                    raise TimeoutError()
                sock.settimeout(left)  # TLS handshake inherits only the remaining budget.
                sockets.append(sock)
                return sock

            setattr(connection, "_create_connection", connect)
            headers = {"Accept": "application/json", "Content-Type": "application/json"}
            if protocol == "anthropic_messages":
                headers.update({"x-api-key": secret, "anthropic-version": api_version})
            elif protocol == "gemini_content":
                headers["x-goog-api-key"] = secret
            elif protocol == "source_semantic_scholar":
                if secret:
                    headers["x-api-key"] = secret
            elif secret:
                headers["Authorization"] = "Bearer " + secret
            if response_format == "pdf":
                headers = {"Accept": "application/pdf"}
            if response_format == "xml":
                headers["Accept"] = "application/atom+xml"
            expired = Event()

            def expire() -> None:
                expired.set()
                for sock in sockets:
                    try:
                        sock.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass

            timer = Timer(remaining, expire)
            timer.daemon = True
            timer.start()
            try:
                connection.connect()
                if connection.sock is not None:
                    sockets.append(connection.sock)
                with authorize():
                    if expired.is_set():
                        raise ProviderFailure("PROVIDER_TIMEOUT")
                    submitted = True
                    connection.request(
                        "GET" if payload is None else "POST",
                        url.path.rstrip("/") + path,
                        body=json.dumps(payload).encode() if payload is not None else None,
                        headers=headers,
                    )
                response = connection.getresponse()
                if response_format == "pdf" and response.status in {301, 302, 303, 307, 308}:
                    location = response.getheader("Location")
                    if not location or len(location) > 8192:
                        raise ProviderFailure("CONFIG_CONNECTION_FAILED")
                    return {"redirect": location}
                if response.status in {401, 403}:
                    raise ProviderFailure("CONFIG_SECRET_UNAVAILABLE")
                if response.status == 429:
                    raise ProviderFailure("PROVIDER_RATE_LIMITED")
                if response.status in {400, 404, 422}:
                    raise ProviderFailure("CONFIG_CONNECTION_FAILED")
                if not 200 <= response.status < 300:
                    raise ProviderFailure("CONFIG_CONNECTION_FAILED")
                limit = 52_428_800 if response_format == "pdf" else 1_048_576
                raw = response.read(limit + 1)
                if len(raw) > limit:
                    raise ProviderFailure("PROVIDER_RESPONSE_INVALID")
                if expired.is_set():
                    raise ProviderFailure("PROVIDER_TIMEOUT")
                if response_format in {"xml", "pdf"}:
                    return raw
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise ProviderFailure("PROVIDER_RESPONSE_INVALID")
                return value
            finally:
                timer.cancel()
                connection.close()
        except ProviderFailure:
            raise
        except ssl.SSLCertVerificationError:
            raise ProviderFailure("CONFIG_CONNECTION_FAILED") from None
        except TimeoutError:
            raise ProviderFailure("PROVIDER_TIMEOUT", submitted=submitted) from None
        except OSError, ValueError, http.client.HTTPException, UnicodeError:
            if monotonic() >= deadline:
                raise ProviderFailure("PROVIDER_TIMEOUT", submitted=submitted) from None
            raise ProviderFailure("CONFIG_CONNECTION_FAILED", submitted=submitted) from None

    def execute(
        self,
        config: dict[str, Any],
        operation: str,
        model: str | None,
        secret: str,
        authorize: Callable[[], AbstractContextManager[None]] = nullcontext,
    ) -> dict[str, Any]:
        protocol = config["protocol"]
        if operation == "refresh":
            value = self.request(
                config["base_url"],
                "/models",
                secret,
                protocol,
                config["api_version"],
                None,
                config["timeout_seconds"],
                authorize,
            )
            found = value.get("models" if protocol == "gemini_content" else "data", [])
            if not isinstance(found, list):
                raise ProviderFailure("PROVIDER_RESPONSE_INVALID")
            names = []
            for item in found[:1000]:
                if isinstance(item, dict):
                    name = item.get("name" if protocol == "gemini_content" else "id")
                    if isinstance(name, str) and 1 <= len(name) <= 200 and secret not in name:
                        name = (
                            name.removeprefix("models/") if protocol == "gemini_content" else name
                        )
                        if name not in names:
                            names.append(name)
            return {"discovered_models": names, "tested_parameters": None, "test_overrides": {}}
        assert model is not None
        params = compile_for_model(protocol, model, config["parameters"], config["api_version"])
        # Preserve explicit output limits: the fixed short prompt requests a tiny response.
        # Missing mandatory Anthropic output limit is an explicit documented test override.
        overrides: dict[str, Any] = {}
        prompt = "Reply with the single word OK."
        if protocol == "openai_chat":
            path = "/chat/completions"
            body = {
                **params,
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            }
        elif protocol == "openai_responses":
            path = "/responses"
            body = {**params, "model": model, "input": prompt, "stream": False}
        elif protocol == "anthropic_messages":
            path = "/messages"
            body = {
                **params,
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            }
            if "max_tokens" not in body:
                body["max_tokens"] = 32
                overrides = {"max_tokens": 32}
        else:
            path = "/models/" + quote(model, safe="") + ":generateContent"
            body = {**params, "contents": [{"role": "user", "parts": [{"text": prompt}]}]}
        value = self.request(
            config["base_url"],
            path,
            secret,
            protocol,
            config["api_version"],
            body,
            config["timeout_seconds"],
            authorize,
        )
        contents = value.get(
            {
                "openai_chat": "choices",
                "openai_responses": "output",
                "anthropic_messages": "content",
                "gemini_content": "candidates",
            }[protocol]
        )
        if not isinstance(contents, list) or not contents:
            raise ProviderFailure("PROVIDER_RESPONSE_INVALID")
        if "error" in value or value.get("status") in {
            "failed",
            "cancelled",
            "in_progress",
            "queued",
        }:
            raise ProviderFailure("PROVIDER_RESPONSE_INVALID")

        def text(part: Any) -> bool:
            return (
                isinstance(part, dict)
                and isinstance(part.get("text"), str)
                and bool(part["text"].strip())
            )

        valid = False
        for item in contents:
            if not isinstance(item, dict):
                continue
            if protocol == "openai_chat":
                message = item.get("message")
                valid |= (
                    isinstance(message, dict)
                    and isinstance(message.get("content"), str)
                    and bool(message["content"].strip())
                )
            elif protocol == "openai_responses":
                valid |= (
                    item.get("type") == "message"
                    and isinstance(item.get("content"), list)
                    and any(text(p) for p in item["content"])
                )
            elif protocol == "anthropic_messages":
                valid |= item.get("type") == "text" and text(item)
            else:
                content = item.get("content")
                valid |= (
                    isinstance(content, dict)
                    and isinstance(content.get("parts"), list)
                    and any(text(p) for p in content["parts"])
                )
        if not valid:
            raise ProviderFailure("PROVIDER_RESPONSE_INVALID")
        return {"discovered_models": [], "tested_parameters": params, "test_overrides": overrides}
