from __future__ import annotations

from tests.conftest import ADMIN_EMAIL, login


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["service"] == "Deal Intelligence"


def test_ready_lists_components(client):
    body = client.get("/api/ready").json()
    assert body["status"] in {"ready", "degraded"}
    assert isinstance(body["checks"], dict)


def test_login_and_me(client, seed):
    headers = login(client, ADMIN_EMAIL)
    me = client.get("/api/auth/me", headers=headers).json()
    assert me["user"]["email"] == ADMIN_EMAIL
    assert me["organization"]["id"] == str(seed["organization_id"])
    assert "deals:read" in me["permissions"] or len(me["permissions"]) > 0


def test_login_rejects_bad_password(client):
    response = client.post(
        "/api/auth/login", json={"email": ADMIN_EMAIL, "password": "nope"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] in {"invalid_credentials", "unauthorized"}


def test_protected_route_requires_token(client):
    assert client.get("/api/deals").status_code in {401, 403}
