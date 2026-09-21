#!/usr/bin/env python3
#QRAP_LITE_VERIFY_REGISTRY_V2
"""Offline verifier for the firmware registry.

Usage:
    python3 verify_registry.py --demo ./demo
    python3 verify_registry.py --registry registry.jsonl --root-keys root_keys.json \
        --sim-keypair sim_keypair.json
    python3 verify_registry.py --registry registry.jsonl --root-keys root_keys.json \
        --sim-keypair sim_keypair.json \
        --chip-id <hex> --puf-hash <hex> --firmware-hash <hex>

Note on simulation mode:
    Without liboqs installed, pq_signer uses a shared-secret MAC for the
    classical part. Cross-process verification therefore requires the same
    keypair. The --sim-keypair flag loads it from a file. In real PQ mode
    (liboqs installed), no keypair file is required.
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pq_signer import PQKeyPair, get_pq_signer  # noqa: E402


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def _verify_dict(d, sig):
    return get_pq_signer().verify_dict(d, sig)


def _sign_dict(d):
    return get_pq_signer().sign_dict(d)


def save_sim_keypair(path):
    signer = get_pq_signer()
    kp = signer.keypair
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "public_key": kp.public_key.hex(),
            "private_key": kp.private_key.hex(),
            "algorithm": kp.algorithm,
        }, f, indent=2)


def load_sim_keypair(path):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    signer = get_pq_signer()
    signer.keypair = PQKeyPair(
        public_key=bytes.fromhex(d["public_key"]),
        private_key=bytes.fromhex(d["private_key"]),
        algorithm=d["algorithm"],
    )


def verify_entry(entry, root_keys):
    checks = []

    entry_no_sig = {k: v for k, v in entry.items() if k != "signature"}
    sig = entry.get("signature", {})
    try:
        sig_ok = bool(_verify_dict(entry_no_sig, sig))
    except Exception:
        sig_ok = False
    checks.append({"name": "entry_signature", "ok": sig_ok})

    signed_by = entry.get("signed_by")
    matching_key = None
    for k in root_keys.get("keys", []):
        if k.get("pubkey") == signed_by:
            matching_key = k
            break
    in_list = matching_key is not None
    checks.append({"name": "key_in_root_list", "ok": in_list})

    if in_list:
        revoked = matching_key.get("revoked_at") is not None
        checks.append({"name": "key_not_revoked", "ok": not revoked})

    ok = all(c["ok"] is not False for c in checks)
    return {"ok": ok, "checks": checks}


def verify_registry(entries, root_keys, chip_id=None, puf_hash=None, firmware_hash=None):
    results = []
    for entry in entries:
        if chip_id and entry.get("chip_id") != chip_id:
            continue
        r = verify_entry(entry, root_keys)
        r["chip_id"] = entry.get("chip_id")
        r["firmware_hash"] = entry.get("firmware_hash")

        if puf_hash is not None:
            m = entry.get("puf_hash") == puf_hash
            r["checks"].append({"name": "puf_hash_matches", "ok": m})
            r["ok"] = r["ok"] and m

        if firmware_hash is not None:
            m = entry.get("firmware_hash") == firmware_hash
            r["checks"].append({"name": "firmware_hash_matches", "ok": m})
            r["ok"] = r["ok"] and m

        results.append(r)

    overall = all(r["ok"] for r in results) if results else False
    return {"ok": overall, "count": len(results), "entries": results}


def load_registry(path):
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def load_root_keys(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def make_demo(out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    signer = get_pq_signer()
    pubkey = signer.keypair.public_key.hex()
    now = datetime.now(timezone.utc).isoformat()

    root_keys = {
        "version": 1,
        "updated_at": now,
        "keys": [{"vendor": "demo-vendor", "pubkey": pubkey, "since": now, "revoked_at": None}],
        "signed_by": pubkey,
    }
    root_keys["signature"] = _sign_dict({k: v for k, v in root_keys.items() if k != "signature"})
    with open(out / "root_keys.json", "w", encoding="utf-8") as f:
        json.dump(root_keys, f, indent=2)

    entry = {
        "chip_id": "demo-chip-001",
        "puf_hash": hashlib.sha256(b"demo-puf").hexdigest(),
        "vendor": "demo-vendor",
        "model": "demo-model",
        "firmware_hash": hashlib.sha256(b"demo-firmware").hexdigest(),
        "firmware_url": None,
        "fused_at": now,
        "signed_by": pubkey,
    }
    entry["signature"] = _sign_dict(entry)
    with open(out / "registry.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    sim_path = out / "sim_keypair.json"
    save_sim_keypair(sim_path)

    return {
        "dir": str(out),
        "root_keys": str(out / "root_keys.json"),
        "registry": str(out / "registry.jsonl"),
        "sim_keypair": str(sim_path),
        "pubkey": pubkey,
        "chip_id": entry["chip_id"],
        "puf_hash": entry["puf_hash"],
        "firmware_hash": entry["firmware_hash"],
    }


def main():
    p = argparse.ArgumentParser(description="Offline verifier for the firmware registry")
    p.add_argument("--registry")
    p.add_argument("--root-keys")
    p.add_argument("--sim-keypair", help="keypair file for simulation mode (cross-process)")
    p.add_argument("--chip-id")
    p.add_argument("--puf-hash")
    p.add_argument("--firmware-hash")
    p.add_argument("--demo", metavar="DIR", help="write a demo registry to DIR and exit")
    args = p.parse_args()

    if args.demo:
        info = make_demo(args.demo)
        print(json.dumps(info, indent=2))
        return

    if not args.registry or not args.root_keys:
        p.error("--registry and --root-keys are required (or use --demo)")

    if args.sim_keypair:
        load_sim_keypair(args.sim_keypair)

    entries = load_registry(args.registry)
    root_keys = load_root_keys(args.root_keys)
    result = verify_registry(
        entries, root_keys,
        chip_id=args.chip_id,
        puf_hash=args.puf_hash,
        firmware_hash=args.firmware_hash,
    )
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
