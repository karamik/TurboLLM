#QRAP_LITE_SIGNER_V1
"""pq_signer wrapper for qrap-lite."""
import json
import sqlite3
import sys
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pq_signer import PQSigner, PQKeyPair, get_pq_signer  # noqa: E402


def _load(conn):
    row = conn.execute("SELECT value FROM meta WHERE key='node_keypair'").fetchone()
    if not row:
        return None
    d = json.loads(row[0])
    return PQKeyPair(bytes.fromhex(d["public_key"]), bytes.fromhex(d["private_key"]), d["algorithm"])


def _save(conn, kp):
    payload = json.dumps({"public_key": kp.public_key.hex(), "private_key": kp.private_key.hex(), "algorithm": kp.algorithm})
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('node_keypair', ?)", (payload,))
    conn.commit()


def get_signer(conn):
    signer = get_pq_signer()
    kp = _load(conn)
    if kp is None:
        _save(conn, signer.keypair)
    else:
        signer.keypair = kp
    return signer
