#!/usr/bin/env python3
#QRAP_LITE_CLASSIFIER_V1
"""Autonomous classifier for qrap-lite.

Reads the ledger, applies transparent rules, and produces a report.
Does NOT write to the ledger. Does NOT act. Only signals.

Rules (version 1.0):

  R1. chain_integrity
      If GET /api/v1/verify returns ok=false, signal CRITICAL.

  R2. consecutive_blocks
      Three or more consecutive blocks with decision == "BLOCKED" signal WARNING.

  R3. high_drift
      Any block whose cell_output.payload.cosine_drift > threshold signals WARNING.
      Default threshold: 0.30.

  R4. low_confidence
      Any block whose cell_output.payload.confidence < threshold signals WARNING.
      Default threshold: 0.50.

  R5. block_rate_spike
      More than N blocks in the last window signals INFO.
      Default: 100 blocks in the last 60 minutes.

Each signal records the rule id, rule version, evidence, and confidence in
the rule itself (rule_confidence, not signal confidence).

Usage:
    python3 classifier.py --endpoint http://localhost:50051 --out report.json
"""
import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List

CLASSIFIER_VERSION = "1.0"

RULES = {
    "R1": {"version": "1.0", "name": "chain_integrity", "severity": "CRITICAL",
           "rule_confidence": 1.0, "params": {}},
    "R2": {"version": "1.0", "name": "consecutive_blocks", "severity": "WARNING",
           "rule_confidence": 0.9, "params": {"min_run": 3}},
    "R3": {"version": "1.0", "name": "high_drift", "severity": "WARNING",
           "rule_confidence": 0.7, "params": {"threshold": 0.30}},
    "R4": {"version": "1.0", "name": "low_confidence", "severity": "WARNING",
           "rule_confidence": 0.6, "params": {"threshold": 0.50}},
    "R5": {"version": "1.0", "name": "block_rate_spike", "severity": "INFO",
           "rule_confidence": 0.5, "params": {"count": 100, "window_minutes": 60}},
}


def _get(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read().decode())


def _blocks(endpoint: str, limit: int) -> List[Dict[str, Any]]:
    data = _get(f"{endpoint}/api/v1/blocks?limit={limit}")
    return data.get("blocks", [])


def _chain_verify(endpoint: str) -> Dict[str, Any]:
    return _get(f"{endpoint}/api/v1/verify")


def rule_r1_chain_integrity(endpoint, blocks):
    result = _chain_verify(endpoint)
    if result.get("ok"):
        return None
    return {
        "rule_id": "R1",
        "rule_version": RULES["R1"]["version"],
        "severity": RULES["R1"]["severity"],
        "evidence": result,
        "message": f"Chain verification failed at height {result.get('height')}",
    }


def rule_r2_consecutive_blocks(blocks):
    signals = []
    run = 0
    start = None
    for b in reversed(blocks):
        cell = b.get("cell_output", {})
        decision = cell.get("decision")
        if decision == "BLOCKED":
            run += 1
            if start is None:
                start = b.get("block_id")
        else:
            if run >= RULES["R2"]["params"]["min_run"]:
                signals.append({
                    "rule_id": "R2",
                    "rule_version": RULES["R2"]["version"],
                    "severity": RULES["R2"]["severity"],
                    "evidence": {"run_length": run, "from": start},
                    "message": f"{run} consecutive BLOCKED decisions",
                })
            run = 0
            start = None
    if run >= RULES["R2"]["params"]["min_run"]:
        signals.append({
            "rule_id": "R2",
            "rule_version": RULES["R2"]["version"],
            "severity": RULES["R2"]["severity"],
            "evidence": {"run_length": run, "from": start},
            "message": f"{run} consecutive BLOCKED decisions",
        })
    return signals


def rule_r3_high_drift(blocks):
    signals = []
    thr = RULES["R3"]["params"]["threshold"]
    for b in blocks:
        drift = (b.get("cell_output", {}).get("payload", {}) or {}).get("cosine_drift")
        if drift is not None and drift > thr:
            signals.append({
                "rule_id": "R3",
                "rule_version": RULES["R3"]["version"],
                "severity": RULES["R3"]["severity"],
                "evidence": {"block_id": b.get("block_id"), "cosine_drift": drift},
                "message": f"cosine_drift {drift} > {thr}",
            })
    return signals


def rule_r4_low_confidence(blocks):
    signals = []
    thr = RULES["R4"]["params"]["threshold"]
    for b in blocks:
        conf = (b.get("cell_output", {}).get("payload", {}) or {}).get("confidence")
        if conf is not None and conf < thr:
            signals.append({
                "rule_id": "R4",
                "rule_version": RULES["R4"]["version"],
                "severity": RULES["R4"]["severity"],
                "evidence": {"block_id": b.get("block_id"), "confidence": conf},
                "message": f"confidence {conf} < {thr}",
            })
    return signals


def rule_r5_block_rate(blocks):
    window = RULES["R5"]["params"]["window_minutes"]
    count_thr = RULES["R5"]["params"]["count"]
    now = datetime.now(timezone.utc)
    recent = 0
    for b in blocks:
        ts = b.get("timestamp")
        if not ts:
            continue
        try:
            t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            continue
        if (now - t).total_seconds() <= window * 60:
            recent += 1
    if recent > count_thr:
        return [{
            "rule_id": "R5",
            "rule_version": RULES["R5"]["version"],
            "severity": RULES["R5"]["severity"],
            "evidence": {"count_in_window": recent, "window_minutes": window},
            "message": f"{recent} blocks in the last {window} minutes",
        }]
    return []


def classify(endpoint, limit=500):
    blocks = _blocks(endpoint, limit)
    signals = []

    r1 = rule_r1_chain_integrity(endpoint, blocks)
    if r1:
        signals.append(r1)

    signals.extend(rule_r2_consecutive_blocks(blocks))
    signals.extend(rule_r3_high_drift(blocks))
    signals.extend(rule_r4_low_confidence(blocks))
    signals.extend(rule_r5_block_rate(blocks))

    by_sev = {"CRITICAL": 0, "WARNING": 0, "INFO": 0}
    for s in signals:
        by_sev[s["severity"]] = by_sev.get(s["severity"], 0) + 1

    return {
        "classifier_version": CLASSIFIER_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "endpoint": endpoint,
        "blocks_scanned": len(blocks),
        "rules": RULES,
        "signals": signals,
        "summary": {
            "total": len(signals),
            "by_severity": by_sev,
        },
    }


def main():
    p = argparse.ArgumentParser(description="qrap-lite autonomous classifier")
    p.add_argument("--endpoint", default="http://localhost:50051")
    p.add_argument("--limit", type=int, default=500)
    p.add_argument("--out", default="-", help="output file, - for stdout")
    args = p.parse_args()

    try:
        report = classify(args.endpoint, args.limit)
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(2)

    text = json.dumps(report, indent=2)
    if args.out == "-":
        print(text)
    else:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"report written to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
