#QRAP_LITE_TEST_LEDGER_V1
"""Unit tests for the qrap-lite ledger."""
import os
import sqlite3
import tempfile

import pytest

from qrap_lite.ledger import GENESIS_HASH, Ledger, _compute_block_hash
from qrap_lite.signer import get_signer

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS blocks (
    height INTEGER PRIMARY KEY AUTOINCREMENT,
    block_id TEXT UNIQUE NOT NULL,
    prev_hash TEXT NOT NULL,
    block_hash TEXT NOT NULL,
    cell_output TEXT NOT NULL,
    signature TEXT NOT NULL,
    pubkey TEXT NOT NULL,
    timestamp TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_block_id ON blocks(block_id);
"""


@pytest.fixture
def ledger():
    tmp = tempfile.mkdtemp(prefix="qrap_lite_test_")
    db = os.path.join(tmp, "test.db")
    conn = sqlite3.connect(db)
    conn.executescript(_SCHEMA)
    conn.commit()
    signer = get_signer(conn)
    conn.close()
    return Ledger(db, signer)


def test_genesis_block_uses_genesis_hash(ledger):
    info = ledger.append({"block_id": "b1", "x": 1})
    assert info["prev_hash"] == GENESIS_HASH
    assert info["height"] == 1


def test_chain_link_between_blocks(ledger):
    i1 = ledger.append({"block_id": "b1"})
    i2 = ledger.append({"block_id": "b2"})
    assert i2["prev_hash"] == i1["block_hash"]


def test_verify_chain_returns_ok(ledger):
    ledger.append({"block_id": "b1"})
    ledger.append({"block_id": "b2"})
    r = ledger.verify_chain()
    assert r["ok"] is True
    assert r["height"] == 2


def test_tamper_detection_on_cell_output(ledger):
    ledger.append({"block_id": "b1", "decision": "APPROVED"})
    conn = sqlite3.connect(ledger.db_path)
    conn.execute(
        "UPDATE blocks SET cell_output=? WHERE height=1",
        ('{"block_id":"b1","decision":"HACKED"}',),
    )
    conn.commit()
    conn.close()
    r = ledger.verify_chain()
    assert r["ok"] is False
    assert r["height"] == 1
    assert "hash" in r["error"]


def test_verify_single_block_ok(ledger):
    ledger.append({"block_id": "b1"})
    r = ledger.verify_block("b1")
    assert r["ok"] is True
    assert r["block_id"] == "b1"
    assert r["height"] == 1


def test_verify_single_block_missing_returns_none(ledger):
    assert ledger.verify_block("nonexistent") is None


def test_proof_package_shape(ledger):
    ledger.append({"block_id": "b1", "decision": "APPROVED", "confidence": 0.9})
    p = ledger.get_proof("b1")
    assert p["block_id"] == "b1"
    assert p["height"] == 1
    assert "signature" in p
    assert "pubkey" in p
    assert "cell_output" in p
    assert "verification" in p
    assert p["verification"]["hash_formula"].startswith("block_hash = SHA256")
    assert p["verification"]["signed_message"]["block_hash"] == p["block_hash"]


def test_proof_missing_returns_none(ledger):
    assert ledger.get_proof("nope") is None


def test_get_missing_returns_none(ledger):
    assert ledger.get("nope") is None


def test_list_returns_recent_first(ledger):
    ledger.append({"block_id": "b1"})
    ledger.append({"block_id": "b2"})
    ledger.append({"block_id": "b3"})
    blocks = ledger.list(limit=10)
    assert [b["block_id"] for b in blocks] == ["b3", "b2", "b1"]


def test_compute_block_hash_is_deterministic():
    a = _compute_block_hash("0" * 64, {"a": 1, "b": 2})
    b = _compute_block_hash("0" * 64, {"b": 2, "a": 1})
    assert a == b


def test_compute_block_hash_changes_with_content():
    h1 = _compute_block_hash("0" * 64, {"a": 1})
    h2 = _compute_block_hash("0" * 64, {"a": 2})
    assert h1 != h2
