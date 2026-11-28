"""
tests/test_logout_refresh_token_security.py — End-to-End Regression Suite for
DEF-UAT-01: Streamlit Login Refresh-Token Persistence & Logout Revocation Lifecycle.

Verifies:
1. Login stores actual refresh_token in st.session_state without exposing tokens in UI or logs.
2. Dashboard Log Out button sends actual refresh_token (never access_token) to POST /auth/logout.
3. Server-side RefreshToken row is marked is_revoked=True, subsequent /auth/refresh attempts are
   rejected (401), and protected API resources (/auth/me, /analytics/executive/summary) reject the
   blacklisted access_token (401).
4. Local Streamlit auth/navigation session state is completely cleared on successful logout.
5. Failed logout (HTTP 500 or ConnectionError) preserves local session state cleanly, surfaces a
   clear error without leaking raw tokens, and allows clean retry once recovered.
6. Expired access_token during logout rotates via refresh_token and revokes cleanly on server.
7. Offline local_db fallback login/logout persists and revokes DB refresh tokens cleanly.
"""

from datetime import timedelta
import logging
import types

import pytest
from streamlit.testing.v1 import AppTest

from app.core.security import hash_password, hash_token, create_access_token
from app.models.user import User, RefreshToken, UserRole


class _NonClosingSessionProxy:
    """Delegate DB calls to pytest db_session without closing transaction scope early."""

    def __init__(self, session):
        self._session = session

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._session, name)


def _bridge_dashboard_http(client, db_session, monkeypatch, *, overrides=None):
    """
    Route dashboard HTTP calls (requests.get/post/put) through FastAPI TestClient
    with X-Enforce-Auth enabled while recording every POST call for payload assertions.
    """
    import app.database as app_db
    import requests

    monkeypatch.setattr(app_db, "SessionLocal", lambda: _NonClosingSessionProxy(db_session))
    recorded_posts = []

    def _caller(method: str):
        def _fn(url: str, *args, **kwargs):
            path = url.replace("http://127.0.0.1:8000", "") if url.startswith("http") else url
            headers = dict(kwargs.pop("headers", {}) or {})
            headers["X-Enforce-Auth"] = "true"
            kwargs.pop("timeout", None)
            json_body = kwargs.pop("json", None)

            if method == "post":
                recorded_posts.append(
                    {"path": path, "json": json_body, "headers": dict(headers)}
                )
                if overrides and path in overrides:
                    return overrides[path](path, json_body, headers)

            tc_resp = getattr(client, method)(path, json=json_body, headers=headers)
            resp_obj = types.SimpleNamespace(
                status_code=tc_resp.status_code,
                text=tc_resp.text,
                content=tc_resp.content,
                headers=tc_resp.headers,
                json=tc_resp.json,
            )

            def _raise_for_status():
                if tc_resp.status_code >= 400:
                    raise RuntimeError(f"HTTP {tc_resp.status_code}: {tc_resp.text}")

            resp_obj.raise_for_status = _raise_for_status
            return resp_obj

        return _fn

    monkeypatch.setattr(requests, "get", _caller("get"))
    monkeypatch.setattr(requests, "post", _caller("post"))
    monkeypatch.setattr(requests, "put", _caller("put"))
    return recorded_posts


def _create_admin(db_session, email: str = "uat_logout_admin@shopsense.com") -> User:
    user = User(
        email=email,
        hashed_password=hash_password("StrongPass!123"),
        role=UserRole.ADMIN,
        is_active=True,
        is_verified=True,
        token_version=1,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _find_button(at: AppTest, substr: str):
    for btn in at.button:
        if substr in (btn.label or ""):
            return btn
    raise AssertionError(f"Button {substr!r} not found. Available: {[b.label for b in at.button]}")


def _find_input(at: AppTest, key: str):
    for inp in at.text_input:
        if inp.key == key:
            return inp
    raise AssertionError(f"TextInput key={key!r} not found.")


def _collect_rendered_text(at: AppTest) -> str:
    """Gather all rendered UI text containers to verify raw tokens are never leaked."""
    parts = []
    for attr in ("markdown", "caption", "text", "error", "warning", "info", "success"):
        for widget in getattr(at, attr, []):
            parts.append(str(getattr(widget, "value", "")))
    return "\n".join(parts)


def test_ui_login_and_logout_submits_refresh_token_revokes_server_and_clears_session(
    client, db_session, monkeypatch, caplog
):
    """
    End-to-end test:
    1. UI login stores access_token + refresh_token cleanly (neither exposed in UI/logs).
    2. Clicking Log Out posts actual refresh_token (not access_token) to /auth/logout.
    3. DB RefreshToken record is marked revoked; /auth/refresh and protected routes reject 401.
    4. All local auth & navigation session keys are cleared and login gate is restored.
    """
    user = _create_admin(db_session)
    recorded_posts = _bridge_dashboard_http(client, db_session, monkeypatch)

    with caplog.at_level(logging.DEBUG):
        at = AppTest.from_file("dashboard/dashboard.py").run(timeout=60)
        assert len(at.exception) == 0
        assert len(at.radio) == 0

        _find_input(at, "login_email").set_value(user.email)
        _find_input(at, "login_pass").set_value("StrongPass!123")
        _find_button(at, "Sign In to ShopSense").click().run(timeout=60)

    assert len(at.exception) == 0
    access_token = at.session_state["auth_token"]
    refresh_token = at.session_state["refresh_token"]
    assert access_token and isinstance(access_token, str)
    assert refresh_token and isinstance(refresh_token, str)
    assert refresh_token != access_token
    assert at.session_state["auth_mode"] == "api"
    assert at.session_state["auth_user"]["email"] == user.email

    # Tokens must never appear in UI widgets or logs
    rendered_text = _collect_rendered_text(at)
    assert access_token not in rendered_text
    assert refresh_token not in rendered_text
    assert access_token not in caplog.text
    assert refresh_token not in caplog.text

    # Confirm DB holds active (unrevoked) RefreshToken row matching stored refresh_token
    rt_row = (
        db_session.query(RefreshToken)
        .filter(RefreshToken.token_hash == hash_token(refresh_token))
        .first()
    )
    assert rt_row is not None
    assert rt_row.is_revoked is False

    # Confirm protected endpoints accept active access_token prior to logout
    auth_headers = {"Authorization": f"Bearer {access_token}", "X-Enforce-Auth": "true"}
    assert client.get("/auth/me", headers=auth_headers).status_code == 200
    assert client.get("/analytics/executive/summary", headers=auth_headers).status_code == 200

    # Carry full authenticated session to post-login rerun frame & trigger UI Log Out
    at_logged_in = AppTest.from_file("dashboard/dashboard.py")
    at_logged_in.session_state["auth_token"] = access_token
    at_logged_in.session_state["refresh_token"] = refresh_token
    at_logged_in.session_state["auth_mode"] = "api"
    at_logged_in.session_state["auth_user"] = at.session_state["auth_user"]
    at_logged_in.session_state["pending_confirm_action"] = {"vendor_id": 99}
    at_logged_in.run(timeout=60)
    assert len(at_logged_in.exception) == 0

    recorded_posts.clear()
    _find_button(at_logged_in, "Log Out").click().run(timeout=60)
    assert len(at_logged_in.exception) == 0

    # Verify /auth/logout received actual refresh_token and Bearer access_token
    logout_calls = [c for c in recorded_posts if c["path"] == "/auth/logout"]
    assert len(logout_calls) == 1
    assert logout_calls[0]["json"] == {"refresh_token": refresh_token}
    assert logout_calls[0]["json"]["refresh_token"] != access_token
    assert logout_calls[0]["headers"]["Authorization"] == f"Bearer {access_token}"

    # Verify DB RefreshToken is now revoked cleanly
    db_session.expire_all()
    rt_after = (
        db_session.query(RefreshToken)
        .filter(RefreshToken.token_hash == hash_token(refresh_token))
        .first()
    )
    assert rt_after is not None
    assert rt_after.is_revoked is True
    assert rt_after.revoked_at is not None

    # Verify refresh attempts and protected endpoints reject revoked tokens with 401
    ref_after = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert ref_after.status_code == 401
    assert client.get("/auth/me", headers=auth_headers).status_code == 401
    assert client.get("/analytics/executive/summary", headers=auth_headers).status_code == 401

    # Verify local session & UI state completely cleared
    assert at_logged_in.session_state["auth_token"] is None
    assert at_logged_in.session_state["refresh_token"] is None
    assert at_logged_in.session_state["auth_user"] is None
    assert at_logged_in.session_state["auth_mode"] is None
    assert at_logged_in.session_state["auth_logout_error"] is None
    assert "nav_radio" not in at_logged_in.session_state
    assert "pending_confirm_action" not in at_logged_in.session_state

    # Next load lands cleanly on unauthenticated login gate
    at_login_gate = AppTest.from_file("dashboard/dashboard.py").run(timeout=60)
    assert len(at_login_gate.radio) == 0
    assert "Welcome to ShopSense" in _collect_rendered_text(at_login_gate)


def test_logout_failure_keeps_session_intact_and_allows_clean_retry(
    client, db_session, monkeypatch
):
    """
    When POST /auth/logout fails (HTTP 500 or network ConnectionError), the dashboard must:
    - NOT clear local session state (no false logout while server tokens stay live),
    - Surface a clear error in the UI without exposing raw tokens,
    - Succeed cleanly once the backend failure resolves.
    """
    user = _create_admin(db_session, email="fail_logout_admin@shopsense.com")
    fail_mode = {"mode": "http_500"}

    def _failing_logout(path, json_body, headers):
        if fail_mode["mode"] == "connection_error":
            raise ConnectionError("Simulated API outage during logout")
        return types.SimpleNamespace(
            status_code=500,
            text='{"detail": "Simulated server failure"}',
            content=b'{"detail": "Simulated server failure"}',
            headers={},
            json=lambda: {"detail": "Simulated server failure"},
        )

    _bridge_dashboard_http(
        client,
        db_session,
        monkeypatch,
        overrides={"/auth/logout": _failing_logout},
    )

    at = AppTest.from_file("dashboard/dashboard.py").run(timeout=60)
    _find_input(at, "login_email").set_value(user.email)
    _find_input(at, "login_pass").set_value("StrongPass!123")
    _find_button(at, "Sign In to ShopSense").click().run(timeout=60)

    access_token = at.session_state["auth_token"]
    refresh_token = at.session_state["refresh_token"]

    # 1. HTTP 500 on /auth/logout -> session preserved, error surfaced, token not exposed
    at_s = AppTest.from_file("dashboard/dashboard.py")
    at_s.session_state["auth_token"] = access_token
    at_s.session_state["refresh_token"] = refresh_token
    at_s.session_state["auth_mode"] = "api"
    at_s.session_state["auth_user"] = at.session_state["auth_user"]
    at_s.run(timeout=60)

    _find_button(at_s, "Log Out").click().run(timeout=60)
    assert len(at_s.exception) == 0
    assert at_s.session_state["auth_token"] == access_token
    assert at_s.session_state["refresh_token"] == refresh_token
    assert at_s.session_state["auth_user"]["email"] == user.email
    assert at_s.session_state["auth_logout_error"] is not None
    assert any("logout failed" in e.value.lower() for e in at_s.error)
    rendered_after_500 = _collect_rendered_text(at_s)
    assert refresh_token not in rendered_after_500
    assert access_token not in rendered_after_500

    # Server refresh token is still active (user can genuinely retry)
    rt_mid = (
        db_session.query(RefreshToken)
        .filter(RefreshToken.token_hash == hash_token(refresh_token))
        .first()
    )
    assert rt_mid is not None and rt_mid.is_revoked is False

    # 2. ConnectionError on /auth/logout -> also preserves session rather than faking logout
    fail_mode["mode"] = "connection_error"
    _find_button(at_s, "Log Out").click().run(timeout=60)
    assert at_s.session_state["auth_token"] == access_token
    assert at_s.session_state["refresh_token"] == refresh_token
    assert any("logout failed" in e.value.lower() for e in at_s.error)

    # 3. Recover backend and retry Log Out -> succeeds and revokes refresh token cleanly
    _bridge_dashboard_http(client, db_session, monkeypatch)
    _find_button(at_s, "Log Out").click().run(timeout=60)
    assert at_s.session_state["auth_token"] is None
    assert at_s.session_state["refresh_token"] is None
    assert at_s.session_state["auth_user"] is None
    assert client.post("/auth/refresh", json={"refresh_token": refresh_token}).status_code == 401


def test_logout_with_expired_access_token_rotates_and_revokes_cleanly(
    client, db_session, monkeypatch
):
    """
    If access_token expired while the dashboard remained open, Log Out should rotate via
    refresh_token and revoke the resulting session cleanly so neither refresh token works.
    """
    user = _create_admin(db_session, email="expired_access_logout@shopsense.com")
    _bridge_dashboard_http(client, db_session, monkeypatch)

    login_resp = client.post(
        "/auth/login",
        json={"email": user.email, "password": "StrongPass!123"},
    )
    assert login_resp.status_code == 200
    refresh_token = login_resp.json()["refresh_token"]

    expired_access = create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        token_version=user.token_version or 1,
        expires_delta=timedelta(seconds=-10),
    )

    at = AppTest.from_file("dashboard/dashboard.py")
    at.session_state["auth_token"] = expired_access
    at.session_state["refresh_token"] = refresh_token
    at.session_state["auth_mode"] = "api"
    at.session_state["auth_user"] = {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "vendor_id": None,
        "customer_id": None,
    }
    at.run(timeout=60)

    _find_button(at, "Log Out").click().run(timeout=60)
    assert len(at.exception) == 0
    assert at.session_state["auth_token"] is None
    assert at.session_state["refresh_token"] is None
    assert at.session_state["auth_user"] is None

    # Original and any rotated refresh token must now be rejected
    assert client.post("/auth/refresh", json={"refresh_token": refresh_token}).status_code == 401
    active_rows = (
        db_session.query(RefreshToken)
        .filter(RefreshToken.user_id == user.id, RefreshToken.is_revoked == False)
        .count()
    )
    assert active_rows == 0


def test_offline_local_db_login_and_logout_revokes_refresh_token(client, db_session, monkeypatch):
    """Verify local_db offline auth mode also persists refresh_token and revokes DB state on logout."""
    import app.database as app_db
    import requests

    user = _create_admin(db_session, email="offline_db_logout@shopsense.com")
    monkeypatch.setattr(app_db, "SessionLocal", lambda: _NonClosingSessionProxy(db_session))

    def _offline_req(*args, **kwargs):
        raise ConnectionError("Simulated offline FastAPI")

    monkeypatch.setattr(requests, "get", _offline_req)
    monkeypatch.setattr(requests, "post", _offline_req)
    monkeypatch.setattr(requests, "put", _offline_req)

    at = AppTest.from_file("dashboard/dashboard.py").run(timeout=60)
    _find_input(at, "login_email").set_value(user.email)
    _find_input(at, "login_pass").set_value("StrongPass!123")
    _find_button(at, "Sign In to ShopSense").click().run(timeout=60)

    refresh_token = at.session_state["refresh_token"]
    assert refresh_token
    assert at.session_state["auth_mode"] == "local_db"

    # Carry post-login session state into fresh rerun frame (mirrors browser session behavior)
    at_logged_in = AppTest.from_file("dashboard/dashboard.py")
    at_logged_in.session_state["auth_token"] = at.session_state["auth_token"]
    at_logged_in.session_state["refresh_token"] = refresh_token
    at_logged_in.session_state["auth_mode"] = "local_db"
    at_logged_in.session_state["auth_user"] = at.session_state["auth_user"]
    at_logged_in.run(timeout=60)

    _find_button(at_logged_in, "Log Out").click().run(timeout=60)
    assert len(at_logged_in.exception) == 0
    assert at_logged_in.session_state["auth_token"] is None
    assert at_logged_in.session_state["refresh_token"] is None
    assert at_logged_in.session_state["auth_user"] is None
    assert at_logged_in.session_state["auth_mode"] is None

    db_session.expire_all()
    rt_row = (
        db_session.query(RefreshToken)
        .filter(RefreshToken.token_hash == hash_token(refresh_token))
        .first()
    )
    assert rt_row is not None
    assert rt_row.is_revoked is True
    assert client.post("/auth/refresh", json={"refresh_token": refresh_token}).status_code == 401
