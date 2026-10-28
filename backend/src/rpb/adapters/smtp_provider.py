"""Bounded SMTP AUTH and provider-owned OAuth endpoints. Never send a message."""

import base64
import http.client
import ipaddress
import json
import smtplib
import socket
import ssl
from threading import Timer
from time import monotonic
from typing import Any
from urllib.parse import urlencode, urlsplit

from rpb.adapters.llm_provider import ProviderFailure, resolve_addresses


def endpoints(config: dict[str, Any]) -> tuple[str, str, str]:
    if config["provider"] == "gmail":
        return (
            "https://accounts.google.com/o/oauth2/v2/auth",
            "https://oauth2.googleapis.com/token",
            "https://mail.google.com/",
        )
    if config["provider"] == "microsoft365":
        base = "https://login.microsoftonline.com/" + config["oauth"]["tenant"] + "/oauth2/v2.0/"
        return (
            base + "authorize",
            base + "token",
            "https://outlook.office.com/SMTP.Send offline_access",
        )
    raise ProviderFailure("CONFIG_CONNECTION_FAILED")


class OAuthProvider:
    def exchange(
        self,
        config: dict[str, Any],
        client_secret: str,
        fields: dict[str, str],
        timeout: float = 30,
    ) -> dict[str, Any]:
        _, url, _ = endpoints(config)
        data = {"client_id": config["oauth"]["client_id"], "client_secret": client_secret, **fields}
        deadline = monotonic() + timeout
        host = urlsplit(url).hostname or ""
        connection: http.client.HTTPSConnection | None = None
        sockets: list[socket.socket] = []
        timer: Timer | None = None

        def expire() -> None:
            for sock in sockets:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

        try:
            addresses = resolve_addresses(host, 443, deadline)
            if not addresses or any(
                not ipaddress.ip_address(item[4][0]).is_global for item in addresses
            ):
                raise ProviderFailure("CONFIG_CONNECTION_FAILED")
            left = deadline - monotonic()
            if left <= 0:
                raise ProviderFailure("PROVIDER_TIMEOUT")
            pinned = addresses[0][4][0]
            connection = http.client.HTTPSConnection(
                host, timeout=left, context=ssl.create_default_context()
            )

            def connect(
                address: Any, timeout: Any = None, source_address: Any = None
            ) -> socket.socket:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                sock = socket.create_connection(
                    (pinned, 443), min(timeout, remaining), source_address
                )
                sockets.append(sock)
                return sock

            setattr(connection, "_create_connection", connect)
            timer = Timer(left, expire)
            timer.daemon = True
            timer.start()
            connection.connect()
            if connection.sock is not None:
                sockets.append(connection.sock)
                connection.sock.settimeout(max(0.001, deadline - monotonic()))
            connection.request(
                "POST",
                urlsplit(url).path,
                body=urlencode(data).encode(),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response = connection.getresponse()
            if response.status in {400, 401, 403}:
                raise ProviderFailure("CONFIG_SECRET_UNAVAILABLE")
            if response.status != 200:
                raise ProviderFailure("PROVIDER_UNAVAILABLE")
            raw = response.read(65537)
            if len(raw) > 65536 or monotonic() >= deadline:
                raise ProviderFailure("PROVIDER_RESPONSE_INVALID")
            result = json.loads(raw)
        except OSError, ValueError, http.client.HTTPException:
            raise ProviderFailure("PROVIDER_RESULT_UNKNOWN") from None
        finally:
            if timer:
                timer.cancel()
            if connection:
                connection.close()
            for sock in sockets:
                sock.close()
        if (
            not isinstance(result, dict)
            or not isinstance(result.get("access_token"), str)
            or not result["access_token"]
            or len(result["access_token"]) > 16384
        ):
            raise ProviderFailure("PROVIDER_RESPONSE_INVALID")
        if (
            not isinstance(result.get("token_type"), str)
            or result["token_type"].lower() != "bearer"
            or type(result.get("expires_in")) is not int
            or not 0 < result["expires_in"] <= 31536000
        ):
            raise ProviderFailure("PROVIDER_RESPONSE_INVALID")
        if "refresh_token" in result and (
            not isinstance(result["refresh_token"], str)
            or not result["refresh_token"]
            or len(result["refresh_token"]) > 16384
        ):
            raise ProviderFailure("PROVIDER_RESPONSE_INVALID")
        if any(c in result["access_token"] for c in "\r\n\x01"):
            raise ProviderFailure("PROVIDER_RESPONSE_INVALID")
        return result


class SMTPProvider:
    def __init__(self, allowed_internal: frozenset[tuple[str, int]] = frozenset()) -> None:
        self.allowed_internal = allowed_internal

    def execute(self, config: dict[str, Any], secret: str, timeout: float) -> dict[str, Any]:
        deadline = monotonic() + timeout
        host, port = config["server"], config["port"]
        smtp: smtplib.SMTP | None = None
        sockets: list[socket.socket] = []
        submitted = False
        timer: Timer | None = None

        def left() -> float:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise ProviderFailure("PROVIDER_TIMEOUT", submitted=submitted)
            return remaining

        def expire() -> None:
            for sock in sockets:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

        try:
            addresses = resolve_addresses(host, port, deadline)
            if not addresses or (
                (host, port) not in self.allowed_internal
                and any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses)
            ):
                raise ProviderFailure("CONFIG_CONNECTION_FAILED")
            if config["encryption"] == "none" and (host, port) not in self.allowed_internal:
                raise ProviderFailure("CONFIG_CONNECTION_FAILED")
            pinned = addresses[0][4][0]
            context = ssl.create_default_context()

            def connect(server: str, server_port: int, socket_timeout: float) -> socket.socket:
                sock = socket.create_connection((pinned, port), timeout=left())
                sockets.append(sock)
                if config["encryption"] == "ssl_tls":
                    sock.settimeout(left())
                    sock = context.wrap_socket(sock, server_hostname=host)
                    sockets.append(sock)
                return sock

            smtp = smtplib.SMTP(timeout=left())
            setattr(smtp, "_host", host)
            setattr(smtp, "_get_socket", connect)
            timer = Timer(left(), expire)
            timer.daemon = True
            timer.start()
            code, _ = smtp.connect(host, port)
            if code != 220:
                raise ProviderFailure("CONFIG_CONNECTION_FAILED")
            submitted = True

            def prepare() -> None:
                assert smtp is not None and smtp.sock is not None
                smtp.sock.settimeout(left())

            prepare()
            if smtp.ehlo()[0] != 250:
                raise ProviderFailure("CONFIG_CONNECTION_FAILED")
            if config["encryption"] == "starttls":
                prepare()
                smtp.starttls(context=context)
                if smtp.sock is not None:
                    sockets.append(smtp.sock)
                prepare()
                if smtp.ehlo()[0] != 250:
                    raise ProviderFailure("CONFIG_CONNECTION_FAILED")
            mode = config["auth_type"]
            prepare()
            if mode in {"password", "api_key"}:
                mechanisms = smtp.esmtp_features.get("auth", "").upper().split()
                mechanism = next((item for item in ("PLAIN", "LOGIN") if item in mechanisms), None)
                if mechanism is None:
                    raise ProviderFailure("CONFIG_CONNECTION_FAILED")
                setattr(smtp, "user", config["username"])
                setattr(smtp, "password", secret)
                # Unlike SMTP.login, do not try another credential mechanism after
                # an explicit authentication rejection (which may lock accounts).
                smtp.auth(mechanism, smtp.auth_plain if mechanism == "PLAIN" else smtp.auth_login)
            elif mode == "token":
                value = "user=" + config["username"] + "\x01auth=Bearer " + secret + "\x01\x01"
                payload = base64.b64encode(value.encode()).decode()
                code, _ = smtp.docmd("AUTH", "XOAUTH2 " + payload)
                if code == 334:
                    prepare()
                    smtp.docmd("")
                if code != 235:
                    raise ProviderFailure("CONFIG_CONNECTION_FAILED")
            left()
            return {"authenticated": mode != "none"}
        except socket.gaierror, ConnectionRefusedError:
            raise ProviderFailure("CONFIG_CONNECTION_FAILED", submitted=submitted) from None
        except smtplib.SMTPException, OSError:
            raise ProviderFailure("CONFIG_CONNECTION_FAILED", submitted=submitted) from None
        finally:
            if timer:
                timer.cancel()
            if smtp is not None:
                smtp.close()
            for sock in sockets:
                sock.close()
