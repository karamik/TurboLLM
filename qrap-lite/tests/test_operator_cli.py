#QRAP_LITE_TEST_OPERATOR_V1
"""Subprocess tests for operator_cli.py."""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
QRAP_LITE = HERE.parent
OPERATOR = QRAP_LITE / "operator_cli.py"

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


def _run(args):
    return subprocess.run(
        [sys.executable, str(OPERATOR)] + args,
        cwd=str(QRAP_LITE),
        capture_output=True,
        text=True,
    )


def _fresh_db():
    tmp = tempfile.mkdtemp(prefix="op_test_")
    db = os.path.join(tmp, "test.db")
    conn = sqlite3.connect(db)
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()
    return db


def test_status_on_empty_db():
    db = _fresh_db()
    r = _run(["--db", db, "status"])
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["chain"]["ok"] is True
    assert data["chain"]["height"] == 0
    assert data["last_block"] is None


def test_missing_db_fails():
    r = _run(["--db", "/nonexistent/x.db", "status"])
    assert r.returncode != 0


def test_blocks_empty():
    db = _fresh_db()
    r = _run(["--db", db, "blocks"])
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_log_action_basic():
    db = _fresh_db()
    r = _run(["--db", db, "log-action", "--operator", "alice",
              "--action", "investigate", "--target", "b1", "--note", "hi"])
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["recorded"] is True
    assert data["height"] == 1
    assert data["block_id"].startswith("op-")


def test_log_action_persists_fields():
    db = _fresh_db()
    _run(["--db", db, "log-action", "--operator", "bob",
          "--action", "escalate", "--target", "b42", "--note", "urgent"])
    conn = sqlite3.connect(db)
    row = conn.execute("SELECT cell_output FROM blocks WHERE height=1").fetchone()
    conn.close()
    cell = json.loads(row[0])
    assert cell["type"] == "operator_action"
    assert cell["operator"] == "bob"
    assert cell["action"] == "escalate"
    assert cell["target"] == "b42"
    assert cell["note"] == "urgent"


def test_log_action_all_types():
    db = _fresh_db()
    for action in ["investigate", "ignore", "stop_cluster", "rotate_keys", "escalate", "note"]:
        r = _run(["--db", db, "log-action", "--operator", "alice", "--action", action])
        assert r.returncode == 0, "action %s failed: %s" % (action, r.stderr)


def test_log_action_invalid_type_rejected():
    db = _fresh_db()
    r = _run(["--db", db, "log-action", "--operator", "alice", "--action", "bogus"])
    assert r.returncode != 0


def test_chain_verifies_after_actions():
    db = _fresh_db()
    _run(["--db", db, "log-action", "--operator", "alice", "--action", "note"])
    _run(["--db", db, "log-action", "--operator", "alice", "--action", "note"])
    r = _run(["--db", db, "status"])
    data = json.loads(r.stdout)
    assert data["chain"]["ok"] is True
    assert data["chain"]["height"] == 2


def test_blocks_lists_recorded_actions():
    db = _fresh_db()
    _run(["--db", db, "log-action", "--operator", "alice", "--action", "note"])
    _run(["--db", db, "log-action", "--operator", "bob", "--action", "escalate"])
    r = _run(["--db", db, "blocks", "--limit", "10"])
    assert r.returncode == 0
    out = r.stdout
    assert "op-" in out or "operator_action" in out or len(out.strip().splitlines()) == 2
