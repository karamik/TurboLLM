#QRAP_LITE_TEST_ANCHOR_V1
"""Subprocess tests for anchor_manifesto.py."""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
QRAP_LITE = HERE.parent
ROOT = QRAP_LITE.parent
ANCHOR = QRAP_LITE / "anchor_manifesto.py"
MANIFESTO = ROOT / "docs" / "manifesto.md"


def _run(args):
    return subprocess.run(
        [sys.executable, str(ANCHOR)] + args,
        cwd=str(QRAP_LITE),
        capture_output=True,
        text=True,
    )


def _tmp_db():
    tmp = tempfile.mkdtemp(prefix="anchor_test_")
    return os.path.join(tmp, "test.db")


def test_anchor_fresh_db():
    db = _tmp_db()
    r = _run(["--db", db, "--manifesto", str(MANIFESTO)])
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["anchored"] is True
    assert data["height"] == 1
    assert data["block_id"] == "manifesto"
    assert len(data["manifesto_hash"]) == 64
    assert len(data["block_hash"]) == 64


def test_anchor_missing_manifesto():
    db = _tmp_db()
    r = _run(["--db", db, "--manifesto", "/nonexistent/x.md"])
    assert r.returncode != 0


def test_anchor_nonempty_db_without_force():
    db = _tmp_db()
    r1 = _run(["--db", db, "--manifesto", str(MANIFESTO)])
    assert r1.returncode == 0
    r2 = _run(["--db", db, "--manifesto", str(MANIFESTO)])
    assert r2.returncode != 0


def test_anchor_nonempty_db_with_force():
    db = _tmp_db()
    _run(["--db", db, "--manifesto", str(MANIFESTO)])
    r2 = _run(["--db", db, "--manifesto", str(MANIFESTO), "--force"])
    assert r2.returncode == 0
    data = json.loads(r2.stdout)
    assert data["height"] == 1


def test_anchor_records_manifesto_hash_in_ledger():
    db = _tmp_db()
    r = _run(["--db", db, "--manifesto", str(MANIFESTO)])
    data = json.loads(r.stdout)
    conn = sqlite3.connect(db)
    row = conn.execute("SELECT cell_output FROM blocks WHERE height=1").fetchone()
    conn.close()
    cell = json.loads(row[0])
    assert cell["type"] == "manifesto"
    assert cell["block_id"] == "manifesto"
    assert cell["manifesto_hash"] == data["manifesto_hash"]
    assert cell["manifesto_hash"] == __import__("hashlib").sha256(MANIFESTO.read_bytes()).hexdigest()
