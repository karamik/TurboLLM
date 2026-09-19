#QRAP_LITE_SERVER_V1
"""qrap-lite HTTP server (aiohttp)."""
import argparse
import logging
import sqlite3
from pathlib import Path
from aiohttp import web

from .ledger import Ledger
from .signer import get_signer

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


def create_app(db_path):
    db_path = str(Path(db_path).resolve())
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    conn.commit()
    signer = get_signer(conn)
    conn.close()
    ledger = Ledger(db_path, signer)

    async def handle_append(request):
        try:
            cell_output = await request.json()
        except Exception as e:
            return web.json_response({"error": f"invalid JSON: {e}"}, status=400)
        try:
            info = ledger.append(cell_output)
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

    async def handle_verify(request):
        return web.json_response(ledger.verify_chain())

    async def handle_health(request):
        return web.json_response({"status": "ok"})

    app = web.Application()
    app.router.add_post("/api/v1/block", handle_append)
    app.router.add_get("/api/v1/block/{block_id}", handle_get)
    app.router.add_get("/api/v1/blocks", handle_list)
    app.router.add_get("/api/v1/verify", handle_verify)
    app.router.add_get("/health", handle_health)
    return app


def main():
    parser = argparse.ArgumentParser(description="qrap-lite append-only ledger")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=50051)
    parser.add_argument("--db", default="qrap_lite.db")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    app = create_app(args.db)
    logger.info("qrap-lite starting on %s:%s (db=%s)", args.host, args.port, args.db)
    web.run_app(app, host=args.host, port=args.port)
