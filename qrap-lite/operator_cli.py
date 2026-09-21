#!/usr/bin/env python3
#QRAP_LITE_OPERATOR_V1
"""Operator CLI for qrap-lite.

Subcommands:

    status        Show chain height, verify result, DB size.
    blocks        List recent blocks.
    classify      Run the classifier and print the report.
    log-action    Record an operator action as a signed block in the ledger.

The operator's actions become part of the same append-only ledger the
operator reads. There is no separate audit trail, and there is no way to
record an action that leaves no trace.

Usage examples:

    python3 operator_cli.py --db qrap_lite.db status
    python3 operator_cli.py --db qrap_lite.db blocks --limit 10
    python3 operator_cli.py --db qrap_lite.db classify --endpoint http://localhost:50051
    python3 operator_cli.py --db qrap_lite.db log-action \\
        --operator alice --action investigate --target b42 --note "high drift"
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from qrap_lite.ledger import Ledger
from qrap_lite.signer import get_signer
from classifier import classify as run_classifier


def open_ledger(db_path):
    if not os.path.exists(db_path):
        print(f"ledger not found: {db_path}", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    signer = get_signer(conn)
    conn.close()
    return Ledger(db_path, signer)


def cmd_status(args):
    ledger = open_ledger(args.db)
    blocks = ledger.list(limit=1)
    chain = ledger.verify_chain()
    db_size = os.path.getsize(args.db)
    print(json.dumps({
        "db": args.db,
        "db_size_bytes": db_size,
        "last_block": blocks[0]["block_id"] if blocks else None,
        "chain": chain,
    }, indent=2))


def cmd_blocks(args):
    ledger = open_ledger(args.db)
    blocks = ledger.list(limit=args.limit)
    for b in blocks:
        cell = b.get("cell_output", {})
        print(f"{b['height']:>6}  {b['timestamp']}  {b['block_id']:<24}  "
              f"decision={cell.get('decision', '-')}")


def cmd_classify(args):
    try:
        report = run_classifier(args.endpoint, args.limit)
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(2)
    text = json.dumps(report, indent=2)
    if args.out == "-":
        print(text)
    else:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"report written to {args.out}")


def cmd_log_action(args):
    ledger = open_ledger(args.db)
    cell = {
        "type": "operator_action",
        "block_id": f"op-{int(datetime.now(timezone.utc).timestamp() * 1000)}",
        "operator": args.operator,
        "action": args.action,
        "target": args.target,
        "note": args.note or "",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    info = ledger.append(cell)
    print(json.dumps({
        "recorded": True,
        "block_id": info["block_id"],
        "height": info["height"],
        "block_hash": info["block_hash"],
    }, indent=2))


def main():
    p = argparse.ArgumentParser(description="qrap-lite operator CLI")
    p.add_argument("--db", default="qrap_lite.db")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("status")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("blocks")
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_blocks)

    sp = sub.add_parser("classify")
    sp.add_argument("--endpoint", default="http://localhost:50051")
    sp.add_argument("--limit", type=int, default=500)
    sp.add_argument("--out", default="-")
    sp.set_defaults(func=cmd_classify)

    sp = sub.add_parser("log-action")
    sp.add_argument("--operator", required=True)
    sp.add_argument("--action", required=True,
                    choices=["investigate", "ignore", "stop_cluster",
                             "rotate_keys", "escalate", "note"])
    sp.add_argument("--target", default="")
    sp.add_argument("--note", default="")
    sp.set_defaults(func=cmd_log_action)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
