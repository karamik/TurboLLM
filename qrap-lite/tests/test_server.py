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
