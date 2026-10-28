"""Explicit SMTP provider and authentication combinations; no network on save."""

import re
from typing import Any


class SMTPError(ValueError):
    def __init__(self, code: str = "VALIDATION_FIELD_INVALID") -> None:
        self.code = code
        super().__init__(code)


HOSTS = {
    "qq": "smtp.qq.com",
    "163": "smtp.163.com",
    "gmail": "smtp.gmail.com",
    "microsoft365": "smtp.office365.com",
    "sendgrid": "smtp.sendgrid.net",
}
MODES = {
    "qq": {"password"},
    "163": {"password"},
    "gmail": {"password", "token"},
    "microsoft365": {"token"},
    "sendgrid": {"api_key"},
    "custom": {"none", "password"},
}


def invalid() -> None:
    raise SMTPError()


def validate(data: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "sender_email",
        "server",
        "port",
        "encryption",
        "auth_type",
        "username",
        "provider",
        "oauth",
        "secret",
        "expected_revision",
    }
    if set(data) - fields:
        raise SMTPError("VALIDATION_UNKNOWN_FIELD")
    out = {k: v for k, v in data.items() if k not in {"secret", "expected_revision"}}
    out.setdefault("provider", "custom")
    out.setdefault("username", None)
    out.setdefault("oauth", None)
    if out.get("provider") not in MODES or out.get("auth_type") not in MODES[out["provider"]]:
        invalid()
    if out.get("encryption") not in {"none", "ssl_tls", "starttls"}:
        invalid()
    if type(out.get("port")) is not int or not 1 <= out["port"] <= 65535:
        invalid()
    for name in ("sender_email", "server"):
        value = out.get(name)
        if (
            not isinstance(value, str)
            or not value
            or len(value) > 254
            or any(c.isspace() for c in value)
        ):
            invalid()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", out["sender_email"]):
        invalid()
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", out["server"]):
        invalid()
    out["server"] = out["server"].lower()
    if out["provider"] in HOSTS and out["server"] != HOSTS[out["provider"]]:
        invalid()
    if out["provider"] != "custom" and out["encryption"] == "none":
        invalid()
    if out["auth_type"] in {"password", "token"}:
        if (
            not isinstance(out["username"], str)
            or not out["username"].strip()
            or len(out["username"]) > 254
            or any(c in out["username"] for c in "\r\n\x01")
        ):
            invalid()
    elif out["auth_type"] == "api_key":
        if out["username"] not in {None, "", "apikey"}:
            invalid()
        out["username"] = "apikey"
    elif out["username"] not in {None, ""}:
        invalid()
    else:
        out["username"] = None
    if out["auth_type"] == "token":
        oauth = out["oauth"]
        if not isinstance(oauth, dict) or set(oauth) - {"client_id", "tenant", "client_secret"}:
            invalid()
        client = oauth.get("client_id")
        if (
            not isinstance(client, str)
            or not 1 <= len(client) <= 512
            or any(c.isspace() for c in client)
        ):
            invalid()
        tenant = oauth.get("tenant")
        if out["provider"] == "microsoft365":
            if not isinstance(tenant, str) or not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", tenant):
                invalid()
        elif tenant is not None:
            invalid()
        out["oauth"] = {"client_id": client, "tenant": tenant}
    elif out["oauth"] is not None:
        invalid()
    return out
