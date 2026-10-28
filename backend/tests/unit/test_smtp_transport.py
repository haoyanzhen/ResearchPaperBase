"""Controlled local SMTP protocol exercises; never contact a mail provider."""

import base64
import json
import socketserver
import threading
import time
from contextlib import contextmanager
from urllib.parse import parse_qs

import pytest

from rpb.adapters.llm_provider import ProviderFailure
from rpb.adapters.smtp_provider import OAuthProvider, SMTPProvider


@contextmanager
def server(ehlo=250, auth=235, delay=0):
    commands = []

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            time.sleep(delay)
            try:
                self.wfile.write(b"220 test SMTP\r\n")
                while line := self.rfile.readline():
                    commands.append(line.decode().strip())
                    if line.startswith(b"ehlo"):
                        self.wfile.write(
                            f"{ehlo}-test\r\n{ehlo} AUTH PLAIN LOGIN XOAUTH2\r\n".encode()
                        )
                    elif line.startswith(b"AUTH"):
                        self.wfile.write(f"{auth} auth result\r\n".encode())
                    else:
                        self.wfile.write(b"500 unsupported\r\n")
            except OSError, BrokenPipeError:
                pass

    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler) as daemon:
        thread = threading.Thread(target=daemon.serve_forever, daemon=True)
        thread.start()
        try:
            yield daemon.server_address[1], commands
        finally:
            daemon.shutdown()
            thread.join(timeout=2)


@pytest.mark.parametrize("mode", ["none", "password", "api_key", "token"])
def test_smtp_transport_only_connects_and_authenticates(mode):
    with server() as (port, commands):
        config = {
            "server": "127.0.0.1",
            "port": port,
            "encryption": "none",
            "auth_type": mode,
            "username": "apikey" if mode == "api_key" else "sender@test.invalid",
        }
        result = SMTPProvider(frozenset({("127.0.0.1", port)})).execute(config, "CREDENTIAL", 2)
        assert result["authenticated"] == (mode != "none")
    assert not any(line.upper().startswith(("MAIL", "RCPT", "DATA")) for line in commands)
    if mode == "token":
        decoded = base64.b64decode(commands[1].split(" ")[2]).decode()
        assert decoded == "user=sender@test.invalid\x01auth=Bearer CREDENTIAL\x01\x01"
    if mode == "api_key":
        assert base64.b64decode(commands[1].split(" ")[2]) == b"\x00apikey\x00CREDENTIAL"


def test_smtp_rejected_ehlo_is_not_success_for_anonymous():
    with server(ehlo=550) as (port, commands):
        with pytest.raises(ProviderFailure):
            SMTPProvider(frozenset({("127.0.0.1", port)})).execute(
                {"server": "127.0.0.1", "port": port, "encryption": "none", "auth_type": "none"},
                "",
                2,
            )
    assert len(commands) == 1


def test_smtp_total_deadline_and_private_network_policy():
    with server(delay=0.3) as (port, commands):
        with pytest.raises(ProviderFailure):
            SMTPProvider().execute(
                {"server": "127.0.0.1", "port": port, "encryption": "none", "auth_type": "none"},
                "",
                1,
            )
        start = time.monotonic()
        with pytest.raises(ProviderFailure):
            SMTPProvider(frozenset({("127.0.0.1", port)})).execute(
                {"server": "127.0.0.1", "port": port, "encryption": "none", "auth_type": "none"},
                "",
                0.05,
            )
        assert time.monotonic() - start < 0.25
    assert not commands


@pytest.mark.parametrize(
    "status,payload,code",
    [
        (302, {}, "PROVIDER_UNAVAILABLE"),
        (401, {"error_description": "SENSITIVE"}, "CONFIG_SECRET_UNAVAILABLE"),
        (
            200,
            {"access_token": "t", "token_type": 42, "expires_in": 3600},
            "PROVIDER_RESPONSE_INVALID",
        ),
        (
            200,
            {"access_token": "t", "token_type": "Bearer", "expires_in": -1},
            "PROVIDER_RESPONSE_INVALID",
        ),
    ],
)
def test_oauth_response_validation_and_no_redirect(monkeypatch, status, payload, code):
    calls = []

    class Connection:
        sock = None

        def __init__(self, host, **kwargs):
            calls.append(host)

        def connect(self):
            pass

        def request(self, method, path, body, headers):
            calls.append((method, path, parse_qs(body.decode())))

        def getresponse(self):
            class Response:
                def read(self, limit):
                    return json.dumps(payload).encode()

            response = Response()
            response.status = status
            return response

        def close(self):
            pass

    monkeypatch.setattr(
        "rpb.adapters.smtp_provider.resolve_addresses",
        lambda *args: [(None, None, None, None, ("8.8.8.8", 443))],
    )
    monkeypatch.setattr("rpb.adapters.smtp_provider.http.client.HTTPSConnection", Connection)
    config = {"provider": "gmail", "oauth": {"client_id": "client", "tenant": None}}
    with pytest.raises(ProviderFailure) as failure:
        OAuthProvider().exchange(
            config,
            "SECRET",
            {"grant_type": "authorization_code", "code": "CODE", "code_verifier": "VERIFIER"},
        )
    assert failure.value.code == code and "SENSITIVE" not in str(failure.value)
    assert calls[0] == "oauth2.googleapis.com" and len(calls) == 2
    assert calls[1][2]["client_secret"] == ["SECRET"]
    assert calls[1][2]["code_verifier"] == ["VERIFIER"]


@contextmanager
def tls_server(tmp_path, mode, reject_starttls=False):
    import ssl
    from datetime import UTC, datetime, timedelta

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "smtp.test.invalid")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("smtp.test.invalid")]), critical=False
        )
        .sign(private_key, hashes.SHA256())
    )
    cert_path, key_path = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    names, commands = [], []
    context.set_servername_callback(lambda sock, name, ctx: names.append(name))

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            sock = self.request
            reader = None
            try:
                if mode == "ssl_tls":
                    sock = context.wrap_socket(sock, server_side=True)
                sock.sendall(b"220 test SMTP\r\n")
                reader = sock.makefile("rb")
                while line := reader.readline():
                    commands.append(line.decode().strip())
                    if line.startswith(b"ehlo"):
                        sock.sendall(b"250-test\r\n250-STARTTLS\r\n250 AUTH PLAIN\r\n")
                    elif line.startswith(b"STARTTLS"):
                        if reject_starttls:
                            sock.sendall(b"454 TLS unavailable\r\n")
                            continue
                        sock.sendall(b"220 ready\r\n")
                        reader.close()
                        sock = context.wrap_socket(sock, server_side=True)
                        reader = sock.makefile("rb")
                    elif line.startswith(b"AUTH"):
                        sock.sendall(b"235 authenticated\r\n")
                    else:
                        sock.sendall(b"500 unsupported\r\n")
            except OSError, ssl.SSLError:
                pass
            finally:
                if reader:
                    reader.close()
                sock.close()

    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler) as daemon:
        thread = threading.Thread(target=daemon.serve_forever, daemon=True)
        thread.start()
        try:
            yield daemon.server_address[1], commands, names, cert_path
        finally:
            daemon.shutdown()
            thread.join(2)


@pytest.mark.parametrize("mode", ["ssl_tls", "starttls"])
def test_smtp_real_tls_preserves_verification_and_sni(tmp_path, monkeypatch, mode):
    import ssl

    with tls_server(tmp_path, mode) as (port, commands, names, cert_path):
        trusted = ssl.create_default_context(cafile=str(cert_path))
        assert trusted.check_hostname and trusted.verify_mode == ssl.CERT_REQUIRED
        monkeypatch.setattr(
            "rpb.adapters.smtp_provider.ssl.create_default_context", lambda: trusted
        )
        monkeypatch.setattr(
            "rpb.adapters.smtp_provider.resolve_addresses",
            lambda *args: [(None, None, None, None, ("127.0.0.1", port))],
        )
        provider = SMTPProvider(frozenset({("smtp.test.invalid", port)}))
        result = provider.execute(
            {
                "server": "smtp.test.invalid",
                "port": port,
                "encryption": mode,
                "auth_type": "password",
                "username": "sender",
            },
            "SECRET",
            2,
        )
        assert result["authenticated"]
    assert names == ["smtp.test.invalid"]
    assert sum(line.startswith("AUTH") for line in commands) == 1
    assert sum(line.startswith("ehlo") for line in commands) == (2 if mode == "starttls" else 1)
    assert not any(line.startswith(("MAIL", "RCPT", "DATA")) for line in commands)


@pytest.mark.parametrize(
    "mode,reject", [("ssl_tls", False), ("starttls", False), ("starttls", True)]
)
def test_smtp_tls_failure_never_authenticates(tmp_path, monkeypatch, mode, reject):
    with tls_server(tmp_path, mode, reject) as (port, commands, names, cert_path):
        monkeypatch.setattr(
            "rpb.adapters.smtp_provider.resolve_addresses",
            lambda *args: [(None, None, None, None, ("127.0.0.1", port))],
        )
        provider = SMTPProvider(frozenset({("smtp.test.invalid", port)}))
        # Production's default trust store intentionally does not trust our test certificate.
        with pytest.raises(ProviderFailure):
            provider.execute(
                {
                    "server": "smtp.test.invalid",
                    "port": port,
                    "encryption": mode,
                    "auth_type": "password",
                    "username": "sender",
                },
                "SECRET",
                2,
            )
    assert not any(line.startswith(("AUTH", "MAIL", "RCPT", "DATA")) for line in commands)


def test_smtp_authentication_rejection_does_not_try_another_mechanism():
    with server(auth=535) as (port, commands):
        with pytest.raises(ProviderFailure):
            SMTPProvider(frozenset({("127.0.0.1", port)})).execute(
                {
                    "server": "127.0.0.1",
                    "port": port,
                    "encryption": "none",
                    "auth_type": "password",
                    "username": "sender",
                },
                "SECRET",
                2,
            )
    assert sum(line.startswith("AUTH") for line in commands) == 1
