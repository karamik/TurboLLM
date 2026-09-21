#!/usr/bin/env python3
#QRAP_LITE_ANCHOR_V1
"""Anchor docs/manifesto.md as the first block of a fresh qrap-lite ledger.

Usage:
    python anchor_manifesto.py --db qrap_lite.db --manifesto ../docs/manifesto.md
"""
import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from qrap_lite.ledger import Ledger
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


def main():
    p = argparse.ArgumentParser(description="Anchor a manifesto as the genesis block")
    p.add_argument("--db", default="qrap_lite.db")
    p.add_argument("--manifesto", default="../docs/manifesto.md")
    p.add_argument("--force", action="store_true", help="overwrite existing DB")
    args = p.parse_args()

    if not os.path.exists(args.manifesto):
        print(f"manifesto not found: {args.manifesto}", file=sys.stderr)
        sys.exit(1)

    if args.force and os.path.exists(args.db):
        os.remove(args.db)
        print(f"removed existing {args.db}", file=sys.stderr)

    conn = sqlite3.connect(args.db)
    conn.executescript(_SCHEMA)
    conn.commit()

    existing = conn.execute("SELECT COUNT(*) FROM blocks").fetchone()[0]
    if existing > 0:
        print(f"ledger is not empty ({existing} blocks). Use --force to reset.", file=sys.stderr)
        sys.exit(1)

    signer = get_signer(conn)
    conn.close()
    ledger = Ledger(args.db, signer)

    with open(args.manifesto, "rb") as f:
        raw = f.read()
    manifesto_hash = hashlib.sha256(raw).hexdigest()

    cell = {
        "type": "manifesto",
        "block_id": "manifesto",
        "manifesto_hash": manifesto_hash,
        "manifesto_path": str(Path(args.manifesto).resolve()),
        "manifesto_version": "1.0",
        "anchored_at": datetime.now(timezone.utc).isoformat(),
    }

    info = ledger.append(cell)
    print(json.dumps({
        "anchored": True,
        "block_id": info["block_id"],
        "height": info["height"],
        "block_hash": info["block_hash"],
        "manifesto_hash": manifesto_hash,
        "manifesto_path": cell["manifesto_path"],
    }, indent=2))


if __name__ == "__main__":
    main()
