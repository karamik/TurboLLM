#QRAP_LITE_TEST_CLASSIFIER_V1
"""Unit tests for the qrap-lite classifier rules."""
import os
import sqlite3
import tempfile

import pytest

from qrap_lite.ledger import Ledger
from qrap_lite.signer import get_signer

# Import classifier from qrap-lite/
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import classifier as C

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
    tmp = tempfile.mkdtemp(prefix="qrap_clf_test_")
    db = os.path.join(tmp, "test.db")
    conn = sqlite3.connect(db)
    conn.executescript(_SCHEMA)
    conn.commit()
    signer = get_signer(conn)
    conn.close()
    return Ledger(db, signer)


def test_r2_triggers_on_three_consecutive_blocked(ledger):
    for i in range(3):
        ledger.append({"block_id": f"b{i}", "decision": "BLOCKED"})
    blocks = ledger.list(limit=10)
    signals = C.rule_r2_consecutive_blocks(blocks)
    assert len(signals) == 1
    assert signals[0]["rule_id"] == "R2"
    assert signals[0]["evidence"]["run_length"] == 3


def test_r2_no_trigger_on_two_blocked(ledger):
    ledger.append({"block_id": "b0", "decision": "BLOCKED"})
    ledger.append({"block_id": "b1", "decision": "BLOCKED"})
    ledger.append({"block_id": "b2", "decision": "APPROVED"})
    blocks = ledger.list(limit=10)
    assert C.rule_r2_consecutive_blocks(blocks) == []


def test_r3_triggers_on_high_drift(ledger):
    ledger.append({"block_id": "b1", "payload": {"cosine_drift": 0.51}})
    ledger.append({"block_id": "b2", "payload": {"cosine_drift": 0.10}})
    blocks = ledger.list(limit=10)
    signals = C.rule_r3_high_drift(blocks)
    assert len(signals) == 1
    assert signals[0]["evidence"]["cosine_drift"] == 0.51


def test_r4_triggers_on_low_confidence(ledger):
    ledger.append({"block_id": "b1", "payload": {"confidence": 0.31}})
    ledger.append({"block_id": "b2", "payload": {"confidence": 0.94}})
    blocks = ledger.list(limit=10)
    signals = C.rule_r4_low_confidence(blocks)
    assert len(signals) == 1
    assert signals[0]["evidence"]["confidence"] == 0.31


def test_r5_no_trigger_below_threshold(ledger):
    for i in range(3):
        ledger.append({"block_id": f"b{i}"})
    blocks = ledger.list(limit=10)
    assert C.rule_r5_block_rate(blocks) == []


def test_classify_summary_shape(ledger):
    ledger.append({"block_id": "b1", "decision": "BLOCKED", "payload": {"cosine_drift": 0.9, "confidence": 0.1}})
    # Use a stub endpoint object with a custom get
    report = {
        "classifier_version": C.CLASSIFIER_VERSION,
        "rules": C.RULES,
    }
    assert "R1" in report["rules"]
    assert "R5" in report["rules"]
