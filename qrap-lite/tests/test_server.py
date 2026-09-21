#QRAP_LITE_TEST_SERVER_V1
"""Unit tests for qrap-lite HTTP endpoints."""
import asyncio
import os
import tempfile

import pytest
from aiohttp.test_utils import TestClient, TestServer

from qrap_lite.server import create_app


def _make_app(api_key=None):
    tmp = tempfile.mkdtemp(prefix="qrap_lite_srv_")
    db = os.path.join(tmp, "test.db")
    return create_app(db, api_key=api_key)


@pytest.fixture
def app_open():
    return _make_app(api_key=None)


@pytest.fixture
def app_auth():
    return _make_app(api_key="secret123")


async def _client(app):
    return TestClient(TestServer(app))


def test_health(app_open):
    async def go():
        c = await _client(app_open)
        await c.start_server()
        r = await c.get("/health")
        assert r.status == 200
        assert (await r.json())["status"] == "ok"
        await c.close()
    asyncio.run(go())


def test_append_open_mode(app_open):
    async def go():
        c = await _client(app_open)
        await c.start_server()
        r = await c.post("/api/v1/block", json={"block_id": "b1"})
        assert r.status == 201
        data = await r.json()
        assert data["status"] == "ok"
        assert data["block_id"] == "b1"
        await c.close()
    asyncio.run(go())


def test_append_without_token_rejected(app_auth):
    async def go():
        c = await _client(app_auth)
        await c.start_server()
        r = await c.post("/api/v1/block", json={"block_id": "b1"})
        assert r.status == 401
        await c.close()
    asyncio.run(go())


def test_append_with_wrong_token_rejected(app_auth):
    async def go():
        c = await _client(app_auth)
        await c.start_server()
        r = await c.post(
            "/api/v1/block",
            json={"block_id": "b1"},
            headers={"Authorization": "Bearer wrong"},
        )
        assert r.status == 401
        await c.close()
    asyncio.run(go())


def test_append_with_correct_token_accepted(app_auth):
    async def go():
        c = await _client(app_auth)
        await c.start_server()
        r = await c.post(
            "/api/v1/block",
            json={"block_id": "b1"},
            headers={"Authorization": "Bearer secret123"},
        )
        assert r.status == 201
        await c.close()
    asyncio.run(go())


def test_get_block_after_append(app_open):
    async def go():
        c = await _client(app_open)
        await c.start_server()
        await c.post("/api/v1/block", json={"block_id": "b1", "x": 1})
        r = await c.get("/api/v1/block/b1")
        assert r.status == 200
        data = await r.json()
        assert data["block_id"] == "b1"
        assert data["cell_output"]["x"] == 1
        await c.close()
    asyncio.run(go())


def test_get_missing_block_returns_404(app_open):
    async def go():
        c = await _client(app_open)
        await c.start_server()
        r = await c.get("/api/v1/block/missing")
        assert r.status == 404
        await c.close()
    asyncio.run(go())


def test_verify_block_endpoint(app_open):
    async def go():
        c = await _client(app_open)
        await c.start_server()
        await c.post("/api/v1/block", json={"block_id": "b1"})
        r = await c.get("/api/v1/blocks/b1/verify")
        assert r.status == 200
        data = await r.json()
        assert data["ok"] is True
        await c.close()
    asyncio.run(go())


def test_verify_chain_endpoint(app_open):
    async def go():
        c = await _client(app_open)
        await c.start_server()
        await c.post("/api/v1/block", json={"block_id": "b1"})
        await c.post("/api/v1/block", json={"block_id": "b2"})
        r = await c.get("/api/v1/verify")
        assert r.status == 200
        data = await r.json()
        assert data["ok"] is True
        assert data["height"] == 2
        await c.close()
    asyncio.run(go())


def test_proof_endpoint(app_open):
    async def go():
        c = await _client(app_open)
        await c.start_server()
        await c.post("/api/v1/block", json={"block_id": "b1", "decision": "APPROVED"})
        r = await c.get("/api/v1/blocks/b1/proof")
        assert r.status == 200
        data = await r.json()
        assert data["block_id"] == "b1"
        assert "signature" in data
        assert "verification" in data
        await c.close()
    asyncio.run(go())


def test_proof_missing_returns_404(app_open):
    async def go():
        c = await _client(app_open)
        await c.start_server()
        r = await c.get("/api/v1/blocks/missing/proof")
        assert r.status == 404
        await c.close()
    asyncio.run(go())


def test_metrics_endpoint(app_open):
    async def go():
        c = await _client(app_open)
        await c.start_server()
        await c.post("/api/v1/block", json={"block_id": "b1"})
        r = await c.get("/metrics")
        assert r.status == 200
        text = await r.text()
        assert "qrap_lite_appends_total" in text
        assert "qrap_lite_blocks_total" in text
        await c.close()
    asyncio.run(go())


# --- Operator and classifier metrics ---

def test_operator_actions_metric_after_log_action(app_open, tmp_path):
    async def go():
        c = await _client(app_open)
        await c.start_server()
        await c.post("/api/v1/block", json={"type": "operator_action",
                                             "block_id": "op-1",
                                             "operator": "alice",
                                             "action": "investigate"})
        await c.post("/api/v1/block", json={"type": "operator_action",
                                             "block_id": "op-2",
                                             "operator": "alice",
                                             "action": "investigate"})
        await c.post("/api/v1/block", json={"type": "operator_action",
                                             "block_id": "op-3",
                                             "operator": "bob",
                                             "action": "escalate"})
        r = await c.get("/metrics")
        text = await r.text()
        assert 'qrap_lite_operator_actions_total{action="investigate",operator="alice"} 2.0' in text
        assert 'qrap_lite_operator_actions_total{action="escalate",operator="bob"} 1.0' in text
        await c.close()
    asyncio.run(go())


def test_classifier_metrics_from_report(app_open, tmp_path):
    report = tmp_path / "report.json"
    report.write_text(
        '{"generated_at": "2026-09-21T20:00:00+00:00", "signals": ['
        '{"rule_id": "R3", "severity": "WARNING"},'
        '{"rule_id": "R3", "severity": "WARNING"},'
        '{"rule_id": "R4", "severity": "WARNING"}]}'
    )
    # Recreate app with classifier_report pointing at the report
    from qrap_lite.server import create_app
    import os, tempfile
    tmp = tempfile.mkdtemp(prefix="clf_srv_")
    db = os.path.join(tmp, "test.db")
    app = create_app(db, api_key=None, classifier_report=str(report))

    async def go():
        c = await _client(app)
        await c.start_server()
        r = await c.get("/metrics")
        text = await r.text()
        assert 'qrap_lite_classifier_signals_total{rule_id="R3",severity="WARNING"} 2.0' in text
        assert 'qrap_lite_classifier_signals_total{rule_id="R4",severity="WARNING"} 1.0' in text
        assert 'qrap_lite_classifier_last_run_timestamp' in text
        await c.close()
    asyncio.run(go())
