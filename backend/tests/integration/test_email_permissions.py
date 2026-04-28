"""
集成测试：邮件配置权限与配置归属

覆盖：
  - 普通用户不能通过 /config/email 修改系统发件字段
  - 普通用户不能访问管理员系统邮件配置接口
  - 管理员可维护系统发件配置，普通用户仅看到自己的收件人偏好
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration


def _skip_if_no_db():
    url = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL", "")
    return "localhost" not in url and "postgres" not in url


@pytest.mark.skipif(_skip_if_no_db(), reason="需要真实 PostgreSQL")
async def test_non_admin_cannot_update_sender_fields(client, auth_headers):
    resp = await client.patch(
        "/api/v1/config/email",
        json={"sender_email": "sender@example.com"},
        headers=auth_headers,
    )

    assert resp.status_code == 422, resp.text


@pytest.mark.skipif(_skip_if_no_db(), reason="需要真实 PostgreSQL")
async def test_non_admin_cannot_access_system_email_config(client, auth_headers):
    resp = await client.get(
        "/api/v1/admin/system-config/email",
        headers=auth_headers,
    )

    assert resp.status_code == 403, resp.text


@pytest.mark.skipif(_skip_if_no_db(), reason="需要真实 PostgreSQL")
async def test_admin_updates_system_email_and_user_only_sees_preferences(
    client,
    auth_headers,
    admin_auth_headers,
):
    admin_resp = await client.patch(
        "/api/v1/admin/system-config/email",
        json={
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "sender_email": "bot@example.com",
        },
        headers=admin_auth_headers,
    )

    assert admin_resp.status_code == 200, admin_resp.text
    admin_data = admin_resp.json()["data"]
    assert admin_data["smtp_host"] == "smtp.example.com"
    assert admin_data["smtp_port"] == 587
    assert admin_data["sender_email"] == "bot@example.com"
    assert admin_data["sender_password_configured"] is False

    user_resp = await client.get("/api/v1/config/email", headers=auth_headers)

    assert user_resp.status_code == 200, user_resp.text
    user_data = user_resp.json()["data"]
    assert user_data == {
        "recipients": [],
        "sender_configured": True,
    }
