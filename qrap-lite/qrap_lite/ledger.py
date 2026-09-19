#QRAP_LITE_LEDGER_V1
"""Append-only block ledger with a hash chain and PQ signatures."""
import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger("qrap-lite.ledger")

GENESIS_HASH = "0" * 64


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def _compute_block_hash(prev_hash, cell_output):
    h = hashlib.sha256()
    h.update(prev_hash.encode())
    h.update(_canonical(cell_output))
    return h.hexdigest()


class Ledger:
    def __init__(self, db_path, signer):
        self.db_path = db_path
        self.signer = signer
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            );
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
        """)
        conn.commit()
        conn.close()

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _last(self, conn):
        return conn.execute("SELECT * FROM blocks ORDER BY height DESC LIMIT 1").fetchone()

    def append(self, cell_output):
        conn = self._conn()
        try:
            last = self._last(conn)
            prev_hash = last["block_hash"] if last else GENESIS_HASH
            block_hash = _compute_block_hash(prev_hash, cell_output)
            sig_info = self.signer.sign_dict({"block_hash": block_hash})
            pubkey_hex = self.signer.keypair.public_key.hex()
            ts = datetime.now(timezone.utc).isoformat()
            block_id = cell_output.get("block_id") or hashlib.sha256(
                f"{block_hash}:{ts}".encode()
            ).hexdigest()[:16]
            cur = conn.execute(
                "INSERT INTO blocks (block_id, prev_hash, block_hash, cell_output, signature, pubkey, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (block_id, prev_hash, block_hash, json.dumps(cell_output, sort_keys=True), json.dumps(sig_info), pubkey_hex, ts),
            )
            conn.commit()
            height = cur.lastrowid
            logger.info("Block %s appended (height=%s)", block_id, height)
            return {"block_id": block_id, "prev_hash": prev_hash, "block_hash": block_hash, "height": height, "timestamp": ts}
        finally:
            conn.close()

    def get(self, block_id):
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM blocks WHERE block_id = ?", (block_id,)).fetchone()
            return self._row_to_dict(row) if row else None
        finally:
            conn.close()

    def list(self, limit=20):
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM blocks ORDER BY height DESC LIMIT ?", (limit,)).fetchall()
            return [self._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def verify_chain(self):
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM blocks ORDER BY height ASC").fetchall()
            prev = GENESIS_HASH
            for row in rows:
                cell_output = json.loads(row["cell_output"])
                expected = _compute_block_hash(prev, cell_output)
                if expected != row["block_hash"]:
                    return {"ok": False, "height": row["height"], "error": "hash mismatch"}
                sig_info = json.loads(row["signature"])
                if not self.signer.verify_dict({"block_hash": row["block_hash"]}, sig_info):
                    return {"ok": False, "height": row["height"], "error": "signature invalid"}
                prev = row["block_hash"]
            return {"ok": True, "height": len(rows)}
        finally:
            conn.close()

    def _row_to_dict(self, row):
        return {
            "height": row["height"],
            "block_id": row["block_id"],
            "prev_hash": row["prev_hash"],
            "block_hash": row["block_hash"],
            "cell_output": json.loads(row["cell_output"]),
            "signature": json.loads(row["signature"]),
            "pubkey": row["pubkey"],
            "timestamp": row["timestamp"],
        }
