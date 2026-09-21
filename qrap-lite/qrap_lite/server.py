#QRAP_LITE_SERVER_V7
"""qrap-lite HTTP server (aiohttp)."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
import logging
import os
import sqlite3
from pathlib import Path
from aiohttp import web
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .ledger import Ledger
from .signer import get_signer
from . import metrics

logger = logging.getLogger("qrap-lite.server")

_SCHEMA = """
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
"""


def _check_auth(request, api_key):
    if not api_key:
        return True
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return False
    return header[7:].strip() == api_key


def _auto_anchor_manifesto(ledger, db_path):
    """On first run, anchor ../docs/manifesto.md if the ledger is empty."""
    try:
        conn = ledger._conn()
        try:
            n = conn.execute("SELECT COUNT(*) AS n FROM blocks").fetchone()["n"]
        finally:
            conn.close()
        if n > 0:
            return None
        here = Path(db_path).resolve().parent
        candidates = [
            here / "docs" / "manifesto.md",
            here.parent / "docs" / "manifesto.md",
            here.parent.parent / "docs" / "manifesto.md",
        ]
        manifesto = None
        for c in candidates:
            if c.exists():
                manifesto = c
                break
        if manifesto is None:
            logger.info("manifesto not found, skipping auto-anchor")
            return None
        raw = manifesto.read_bytes()
        mh = hashlib.sha256(raw).hexdigest()
        cell = {
            "type": "manifesto",
            "block_id": "manifesto",
            "manifesto_hash": mh,
            "manifesto_path": str(manifesto),
            "manifesto_version": "1.0",
            "anchored_at": datetime.now(timezone.utc).isoformat(),
        }
        info = ledger.append(cell)
        logger.info("auto-anchored manifesto: %s", info["block_id"])
        return info
    except Exception as e:
        logger.warning("auto-anchor failed: %s", e)
        return None


def create_app(db_path, api_key=None, classifier_report=None):
    db_path = str(Path(db_path).resolve())
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    conn.commit()
    signer = get_signer(conn)
    conn.close()
    ledger = Ledger(db_path, signer)
    _auto_anchor_manifesto(ledger, db_path)

    async def handle_append(request):
        if not _check_auth(request, api_key):
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            cell_output = await request.json()
        except Exception as e:
            return web.json_response({"error": f"invalid JSON: {e}"}, status=400)
        try:
            with metrics.APPEND_DURATION.time():
                info = ledger.append(cell_output)
            metrics.APPENDS_TOTAL.inc()
            metrics.refresh_gauges(ledger, db_path)
        except Exception as e:
            logger.exception("append failed")
            return web.json_response({"error": str(e)}, status=500)
        return web.json_response({"status": "ok", **info}, status=201)

    async def handle_get(request):
        block_id = request.match_info["block_id"]
        block = ledger.get(block_id)
        if block is None:
            return web.json_response({"error": "not found"}, status=404)
        return web.json_response(block)

    async def handle_list(request):
        try:
            limit = int(request.query.get("limit", "20"))
        except ValueError:
            limit = 20
        limit = max(1, min(limit, 500))
        return web.json_response({"blocks": ledger.list(limit)})

    async def handle_proof(request):
        block_id = request.match_info["block_id"]
        proof = ledger.get_proof(block_id)
        if proof is None:
            return web.json_response({"error": "not found"}, status=404)
        return web.json_response(proof)

    async def handle_verify_chain(request):
        result = ledger.verify_chain()
        metrics.VERIFY_TOTAL.labels(scope="chain", result="ok" if result.get("ok") else "fail").inc()
        return web.json_response(result)

    async def handle_verify_block(request):
        block_id = request.match_info["block_id"]
        result = ledger.verify_block(block_id)
        if result is None:
            return web.json_response({"error": "not found"}, status=404)
        metrics.VERIFY_TOTAL.labels(scope="block", result="ok" if result.get("ok") else "fail").inc()
        return web.json_response(result)

    async def handle_manifesto(request):
        anchor = ledger.get_manifesto_anchor()
        if anchor is None:
            return web.json_response({"anchored": False}, status=404)
        result = {"anchored": True, **anchor}
        path = anchor.get("manifesto_path")
        if path and os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    current = hashlib.sha256(f.read()).hexdigest()
                result["manifesto_hash_current"] = current
                result["match"] = current == anchor.get("manifesto_hash")
            except Exception as e:
                result["manifesto_hash_current_error"] = str(e)
        return web.json_response(result)

    async def handle_metrics(request):
        metrics.refresh_gauges(ledger, db_path)
        metrics.refresh_operator_metrics(ledger)
        metrics.refresh_classifier_metrics(classifier_report)
        return web.Response(body=generate_latest(), content_type=CONTENT_TYPE_LATEST.split(";")[0], charset="utf-8")

    async def handle_health(request):
        metrics.refresh_gauges(ledger, db_path)
        metrics.refresh_operator_metrics(ledger)
        metrics.refresh_classifier_metrics(classifier_report)
        return web.json_response({"status": "ok"})

    app = web.Application()
    app.router.add_post("/api/v1/block", handle_append)
    app.router.add_get("/api/v1/block/{block_id}", handle_get)
    app.router.add_get("/api/v1/blocks", handle_list)
    app.router.add_get("/api/v1/blocks/{block_id}/verify", handle_verify_block)
    app.router.add_get("/api/v1/blocks/{block_id}/proof", handle_proof)
    app.router.add_get("/api/v1/verify", handle_verify_chain)
    app.router.add_get("/api/v1/manifesto", handle_manifesto)
    app.router.add_get("/metrics", handle_metrics)
    app.router.add_get("/health", handle_health)
    return app


def main():
    parser = argparse.ArgumentParser(description="qrap-lite append-only ledger")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=50051)
    parser.add_argument("--db", default="qrap_lite.db")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    api_key = os.getenv("QRAP_LITE_API_KEY", "").strip()
    classifier_report = os.getenv("QRAP_LITE_CLASSIFIER_REPORT", "").strip() or None
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    if classifier_report:
        logger.info("Classifier report path: %s", classifier_report)
    if api_key:
        logger.info("API key authentication is ENABLED for POST endpoints")
    else:
        logger.info("API key authentication is DISABLED (QRAP_LITE_API_KEY not set)")
    app = create_app(args.db, api_key=api_key or None, classifier_report=classifier_report)
    logger.info("qrap-lite starting on %s:%s (db=%s)", args.host, args.port, args.db)
    web.run_app(app, host=args.host, port=args.port)
