import asyncio
import time
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import auth
import main

GRAPH = {
    "nodes": [
        {"id": "start", "type": "start", "title": "开始", "config": {}},
        {"id": "end", "type": "end", "title": "结束", "config": {}},
    ],
    "edges": [{"source": "start", "target": "end"}],
}


@pytest.fixture(autouse=True)
def clear_rate_state():
    """The windows are module globals, so one test's attempts would otherwise spend
    the next test's budget."""
    yield
    for window in auth.LIMITS.values():
        window.reset()
    auth.DAILY_RUNS.reset()


@pytest.fixture
def gated(monkeypatch):
    monkeypatch.setenv("AGENTFLOW_ACCESS_CODE", "demo-code")
    monkeypatch.setenv("AGENTFLOW_SESSION_SECRET", "unit-test-secret")


async def _workflow_id(client):
    created = await client.post("/api/workflows", json={"name": "Gated", **GRAPH})
    return created.json()["id"]


async def _login(client):
    """Everything except /api/login sits behind the gate, so tests that build a
    workflow first have to unlock it."""
    res = await client.post("/api/login", json={"code": "demo-code"})
    assert res.status_code == 200
    client.cookies.set(auth.SESSION_COOKIE, res.cookies[auth.SESSION_COOKIE])


class TestGateIsOptional:
    async def test_no_code_means_no_gate(self, client):
        assert auth.auth_enabled() is False
        assert (await client.get("/api/stats")).status_code == 200

        page = await client.get("/")
        assert "访问口令" not in page.text

    async def test_login_without_a_code_reports_itself(self, client):
        res = await client.post("/api/login", json={"code": "anything"})
        assert res.status_code == 200
        assert res.json()["auth_enabled"] is False


class TestAccessCode:
    async def test_api_calls_are_refused(self, client, gated):
        res = await client.get("/api/stats")
        assert res.status_code == 401
        assert res.json()["detail"]

    async def test_navigations_get_the_login_card(self, client, gated):
        res = await client.get("/")
        assert res.status_code == 302
        assert res.headers["location"] == "/login"

        card = await client.get("/login")
        assert card.status_code == 200
        assert "访问口令" in card.text
        # The bundle stays behind the gate; the card carries its own styling.
        assert "/static/js/app.js" not in card.text

    async def test_static_assets_are_not_served_unlocked(self, client, gated):
        res = await client.get("/static/js/app.js")
        assert res.status_code == 302

    async def test_health_stays_open_for_the_container(self, client, gated):
        assert (await client.get("/health")).status_code == 200

    async def test_wrong_code_gets_no_cookie(self, client, gated):
        res = await client.post("/api/login", json={"code": "guessed"})
        assert res.status_code == 401
        assert "set-cookie" not in res.headers

    async def test_right_code_issues_a_session(self, client, gated):
        res = await client.post("/api/login", json={"code": "demo-code"})
        assert res.status_code == 200
        token = res.cookies.get(auth.SESSION_COOKIE)
        assert token

        client.cookies.set(auth.SESSION_COOKIE, token)
        assert (await client.get("/api/stats")).status_code == 200

    def test_forged_or_expired_sessions_are_refused(self, gated, monkeypatch):
        assert auth.valid_session("9999999999.deadbeef") is False
        assert auth.valid_session(None) is False
        assert auth.valid_session("not-a-token") is False

        base = time.time()
        monkeypatch.setattr(auth, "_now", lambda: base)
        token = auth.issue_session()
        assert auth.valid_session(token) is True

        monkeypatch.setattr(auth, "_now", lambda: base + auth.SESSION_TTL + 1)
        assert auth.valid_session(token) is False

    def test_code_compare_is_not_a_plain_equality(self, gated):
        assert auth.code_matches("  demo-code  ") is True
        assert auth.code_matches("demoCod") is False
        assert auth.code_matches(None) is False


class TestRateLimits:
    async def test_login_attempts_are_bounded(self, client, gated, monkeypatch):
        monkeypatch.setenv("AGENTFLOW_LIMIT_LOGIN", "2")

        assert (await client.post("/api/login", json={"code": "a"})).status_code == 401
        assert (await client.post("/api/login", json={"code": "b"})).status_code == 401
        res = await client.post("/api/login", json={"code": "c"})
        assert res.status_code == 429
        assert "稍后再试" in res.json()["detail"]

    async def test_execute_is_bounded_per_ip(self, client, gated, monkeypatch):
        monkeypatch.setenv("AGENTFLOW_LIMIT_EXECUTE", "2")
        await _login(client)
        wf_id = await _workflow_id(client)

        for _ in range(2):
            res = await client.post(f"/api/workflows/{wf_id}/execute", json={"input": {"input": "x"}})
            assert res.status_code != 429
            await asyncio.sleep(0.05)

        blocked = await client.post(f"/api/workflows/{wf_id}/execute", json={"input": {"input": "x"}})
        assert blocked.status_code == 429
        assert "分钟" in blocked.json()["detail"]

    async def test_the_daily_budget_stops_new_runs(self, client, gated, monkeypatch):
        monkeypatch.setattr(auth.DAILY_RUNS, "hard_max", 1)
        await _login(client)
        wf_id = await _workflow_id(client)

        first = await client.post(f"/api/workflows/{wf_id}/execute", json={"input": {"input": "x"}})
        assert first.status_code == 200
        second = await client.post(f"/api/workflows/{wf_id}/execute", json={"input": {"input": "x"}})
        assert second.status_code == 429
        assert "今天" in second.json()["detail"]

    async def test_a_rejected_workflow_does_not_eat_the_budget(self, client, gated, monkeypatch):
        monkeypatch.setattr(auth.DAILY_RUNS, "hard_max", 1)
        await _login(client)
        empty = await client.post("/api/workflows", json={"name": "Empty", "nodes": [], "edges": []})
        wf_id = empty.json()["id"]

        invalid = await client.post(f"/api/workflows/{wf_id}/execute", json={"input": {"input": "x"}})
        assert invalid.status_code == 400
        assert auth.DAILY_RUNS.remaining == 1

    def test_window_prunes_but_still_counts(self):
        window = auth.Window(limit=2, seconds=60)
        assert window.allow("1.2.3.4") == (True, 0)
        allowed, _ = window.allow("1.2.3.4")
        assert allowed is True
        assert window.allow("1.2.3.4")[0] is False
        assert window.allow("5.6.7.8")[0] is True

    def test_forwarded_header_is_only_trusted_when_configured(self, monkeypatch):
        class Peer:
            host = "10.0.0.1"

        class Req:
            client = Peer()
            headers = {"x-forwarded-for": "203.0.113.7, 10.0.0.1"}

        monkeypatch.delenv("AGENTFLOW_TRUST_PROXY", raising=False)
        assert auth.client_ip(Req()) == "10.0.0.1"

        monkeypatch.setenv("AGENTFLOW_TRUST_PROXY", "1")
        assert auth.client_ip(Req()) == "203.0.113.7"


class TestWebSocketGate:
    @staticmethod
    def _execution(status):
        db = main.SessionLocal()
        execution = main.Execution(
            workflow_id=1,
            status=status,
            started_at=datetime.now(timezone.utc),
            logs=[],
        )
        db.add(execution)
        db.commit()
        exec_id = execution.id
        db.close()
        return exec_id

    def test_socket_is_refused_without_a_session(self, gated):
        exec_id = self._execution("running")

        client = TestClient(main.app)
        # Closing before accept means the handshake never opens, so the client sees
        # a disconnect instead of a snapshot it has no business reading.
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"/ws/execute/{exec_id}") as ws:
                ws.receive_json()
        assert exec_id not in main.active_connections

    def test_socket_opens_for_a_valid_session(self, gated):
        token = auth.issue_session()
        exec_id = self._execution("completed")

        client = TestClient(main.app, cookies={auth.SESSION_COOKIE: token})
        with client.websocket_connect(f"/ws/execute/{exec_id}") as ws:
            assert ws.receive_json()["type"] == "snapshot"
