#QRAP_LITE_METRICS_V1
"""Prometheus metrics for qrap-lite."""
import os
from prometheus_client import Counter, Gauge, Histogram

BLOCKS_TOTAL = Gauge(
    "qrap_lite_blocks_total",
    "Current number of blocks in the ledger",
)

APPENDS_TOTAL = Counter(
    "qrap_lite_appends_total",
    "Total successful appends via POST /api/v1/block",
)

APPEND_DURATION = Histogram(
    "qrap_lite_append_duration_seconds",
    "Latency of ledger.append in seconds",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)

VERIFY_TOTAL = Counter(
    "qrap_lite_verify_total",
    "Verify calls by scope and result",
    ["scope", "result"],
)

DB_SIZE_BYTES = Gauge(
    "qrap_lite_db_size_bytes",
    "Size of the SQLite ledger file in bytes",
)


def refresh_gauges(ledger, db_path):
    try:
        conn = ledger._conn()
        try:
            row = conn.execute("SELECT COUNT(*) AS n FROM blocks").fetchone()
            BLOCKS_TOTAL.set(row["n"] if row else 0)
        finally:
            conn.close()
    except Exception:
        pass
    try:
        DB_SIZE_BYTES.set(os.path.getsize(db_path))
    except Exception:
        pass
