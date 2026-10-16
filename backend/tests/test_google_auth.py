import json
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app import google_auth
from app.main import app
from app.memory_main import app as memory_app
from app.memory_control import database

CALLBACK = "http://localhost:3000/api/auth/google/callback"
FORM = {
    "redirect_uri": CALLBACK,
    "code": "single-use-code",
    "verifier": "v" * 43,
    "nonce": "n" * 43,
}


@pytest.fixture
def clients(monkeypatch, tmp_path):
    monkeypatch.setenv("LIGHTHOUSE_MEMORY_CONTROL_DB", str(tmp_path / "oauth.sqlite3"))
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("LIGHTHOUSE_APP_URL", "http://localhost:3000")
    monkeypatch.setenv("MEMORY_SITE_URL", "http://localhost:3003")
    return TestClient(app, raise_server_exceptions=False), TestClient(
        memory_app, raise_server_exceptions=False
    )


def claims(email="google@example.test", sub="google-subject"):
    return {
        "sub": sub,
        "email": email,
        "email_verified": True,
        "name": "Google user",
        "nonce": FORM["nonce"],
    }


def test_new_google_account_and_repeat_login_share_both_products(clients, monkeypatch):
    ops, memory = clients
    identity = claims()
    monkeypatch.setattr(google_auth, "google_identity", lambda *args: identity)
    created = ops.post("/api/auth/google/exchange", json=FORM)
    assert created.status_code == 200
    first = created.json()
    assert first["user"]["google_connected"] is True
    headers = {"Authorization": "Bearer " + first["token"]}
    account = ops.get("/api/auth/me", headers=headers).json()
    assert account["user"]["google_connected"] is True
    assert account["user"]["name"] == "Google user"
    workspace = account["workspace"]
    assert (
        memory.get("/console/overview", headers=headers).json()["workspaces"][0]["id"] == workspace
    )
    second = memory.post(
        "/auth/google/exchange", json={**FORM, "redirect_uri": CALLBACK.replace("3000", "3003")}
    ).json()
    assert second["user"]["id"] == first["user"]["id"] and second["token"] != first["token"]
    # The stable Google subject, not a changing email address, owns the account.
    identity["email"] = "renamed@example.test"
    assert (
        ops.post("/api/auth/google/exchange", json=FORM).json()["user"]["id"] == first["user"]["id"]
    )
    with database() as db:
        assert db.execute("SELECT count(*) FROM users").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM workspaces").fetchone()[0] == 1
    assert ops.post("/api/auth/logout", headers=headers).status_code == 200
    assert ops.get("/api/auth/me", headers=headers).status_code == 401


def test_existing_password_account_requires_authenticated_explicit_link(clients, monkeypatch):
    ops, memory = clients
    account = ops.post(
        "/api/auth/register",
        json={
            "email": "owner@example.test",
            "password": "existing-account-password",
            "name": "Owner",
        },
    ).json()
    monkeypatch.setattr(google_auth, "google_identity", lambda *args: claims("owner@example.test"))
    assert ops.post("/api/auth/google/exchange", json=FORM).status_code == 409
    assert ops.post("/api/auth/google/exchange", json={**FORM, "link": True}).status_code == 401
    headers = {"Authorization": "Bearer " + account["token"]}
    linked = ops.post("/api/auth/google/exchange", headers=headers, json={**FORM, "link": True})
    assert linked.json()["user"]["google_connected"] is True
    assert linked.status_code == 200 and linked.json()["user"]["id"] == account["user"]["id"]
    assert (
        memory.post(
            "/auth/google/exchange", json={**FORM, "redirect_uri": CALLBACK.replace("3000", "3003")}
        ).json()["user"]["id"]
        == account["user"]["id"]
    )
    monkeypatch.setattr(
        google_auth,
        "google_identity",
        lambda *args: claims("someone-else@example.test", "another-subject"),
    )
    assert (
        ops.post(
            "/api/auth/google/exchange", headers=headers, json={**FORM, "link": True}
        ).status_code
        == 409
    )
    with database() as db:
        assert db.execute("SELECT count(*) FROM oauth_identities").fetchone()[0] == 1


def test_authorization_parameters_and_redirect_allowlist(clients):
    ops, _ = clients
    body = {"redirect_uri": CALLBACK, "state": "s" * 43, "nonce": "n" * 43, "challenge": "c" * 43}
    result = ops.post("/api/auth/google/start", json=body)
    assert result.status_code == 200
    target = urlparse(result.json()["url"])
    query = parse_qs(target.query)
    assert target.scheme == "https" and target.netloc == "accounts.google.com"
    assert query["scope"] == ["openid email profile"]
    assert query["code_challenge_method"] == ["S256"] and query["state"] == [body["state"]]
    assert query["nonce"] == [body["nonce"]] and "client_secret" not in query
    assert (
        ops.post(
            "/api/auth/google/start",
            json={**body, "redirect_uri": "https://attacker.example/callback"},
        ).status_code
        == 400
    )
    assert (
        ops.post(
            "/api/auth/google/exchange",
            json={**FORM, "redirect_uri": "https://attacker.example/callback"},
        ).status_code
        == 400
    )


@pytest.mark.parametrize("invalid", ["nonce", "email", "signature"])
def test_google_token_verification_rejects_invalid_identity(clients, monkeypatch, invalid):
    ops, _ = clients

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, size):
            return json.dumps({"id_token": "signed-google-token"}).encode()

    def token_request(request, timeout):
        body = parse_qs(request.data.decode())
        assert request.full_url == "https://oauth2.googleapis.com/token"
        assert body["code_verifier"] == [FORM["verifier"]]
        assert body["redirect_uri"] == [CALLBACK]
        return Response()

    monkeypatch.setattr(google_auth, "urlopen", token_request)

    def verify(token, transport, audience):
        assert token == "signed-google-token" and audience == "test-client-id"
        if invalid == "signature":
            raise ValueError("Invalid signed token: internal detail")
        identity = claims()
        if invalid == "nonce":
            identity["nonce"] = "wrong"
        if invalid == "email":
            identity["email_verified"] = False
        return identity

    monkeypatch.setattr(google_auth, "verify_oauth2_token", verify)
    result = ops.post("/api/auth/google/exchange", json=FORM)
    assert result.status_code == 401 and "internal detail" not in result.text
    with database() as db:
        assert db.execute("SELECT count(*) FROM users").fetchone()[0] == 0


def test_missing_configuration_is_safe(clients, monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET")
    ops, _ = clients
    result = ops.post("/api/auth/google/exchange", json=FORM)
    assert result.status_code == 503 and "test-client-id" not in result.text
