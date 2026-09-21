#QRAP_LITE_METRICS_V1
"""Prometheus metrics for qrap-lite."""
import json
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


# --- Operator metrics (derived from ledger) ---

OPERATOR_ACTIONS = Gauge(
    "qrap_lite_operator_actions_total",
    "Operator actions recorded in the ledger",
    ["operator", "action"],
)

# --- Classifier metrics (derived from report file, optional) ---

CLASSIFIER_SIGNALS = Gauge(
    "qrap_lite_classifier_signals_total",
    "Classifier signals from the latest report",
    ["rule_id", "severity"],
)

CLASSIFIER_LAST_RUN = Gauge(
    "qrap_lite_classifier_last_run_timestamp",
    "Unix timestamp of the last classifier run (0 if never)",
)


def refresh_operator_metrics(ledger):
    """Count operator_action blocks by (operator, action)."""
    try:
        conn = ledger._conn()
        try:
            rows = conn.execute(
                "SELECT cell_output FROM blocks ORDER BY height ASC"
            ).fetchall()
        finally:
            conn.close()
        counts = {}
        for row in rows:
            try:
                cell = json.loads(row["cell_output"])
            except Exception:
                continue
            if cell.get("type") != "operator_action":
                continue
            key = (cell.get("operator", "?"), cell.get("action", "?"))
            counts[key] = counts.get(key, 0) + 1
        for (op, act), n in counts.items():
            OPERATOR_ACTIONS.labels(operator=op, action=act).set(n)
    except Exception:
        pass


def refresh_classifier_metrics(report_path):
    """Read a classifier report file and update signal gauges."""
    if not report_path:
        return
    try:
        with open(report_path, encoding="utf-8") as f:
            report = json.load(f)
    except Exception:
        return
    signals = report.get("signals", [])
    counts = {}
    for s in signals:
        key = (s.get("rule_id", "?"), s.get("severity", "?"))
        counts[key] = counts.get(key, 0) + 1
    for (rid, sev), n in counts.items():
        CLASSIFIER_SIGNALS.labels(rule_id=rid, severity=sev).set(n)
    gen = report.get("generated_at")
    if gen:
        try:
            from datetime import datetime as _dt
            t = _dt.fromisoformat(gen.replace("Z", "+00:00"))
            CLASSIFIER_LAST_RUN.set(t.timestamp())
        except Exception:
            pass
