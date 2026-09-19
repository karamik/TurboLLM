#!/usr/bin/env python3
#QRAP_LITE_VERIFY_V1
"""Offline verifier for qrap-lite proof packages."""
import hashlib, json, sys

def _canon(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":")).encode()

def _sha(b):
    return hashlib.sha256(b).hexdigest()

def verify(p):
    checks = []
    expected = _sha(p["prev_hash"].encode() + _canon(p["cell_output"]))
    checks.append({"name": "block_hash", "ok": expected == p["block_hash"]})
    s = p["signature"]
    hybrid = hashlib.shake_256(s["classical_sig"].encode() + s["pq_sig"].encode()).hexdigest(32)
    checks.append({"name": "hybrid_hash", "ok": hybrid == s.get("hybrid_hash")})
    checks.append({"name": "signature_authenticity", "ok": None,
                   "note": "requires liboqs + real PQ mode"})
    return {"ok": all(c["ok"] is not False for c in checks), "checks": checks}

if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "-"
    data = json.load(sys.stdin if src == "-" else open(src))
    r = verify(data)
    print(json.dumps(r, indent=2))
    sys.exit(0 if r["ok"] else 1)
