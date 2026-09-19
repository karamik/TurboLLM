# qrap-lite — Architecture

Append-only ledger for provable auditing of TurboLLM decisions.
Free. No tokens, no staking, no fees, no wallets, no USDT.

This document describes the internal design of qrap-lite: its goals,
data model, hash chain, signature scheme, API contract, proof format,
threat model, and operational notes.

---

## 1. Design goals

- **Provable**: every record can be verified against tampering, both online
  and offline.
- **Append-only**: no API path deletes or mutates a stored block.
- **Self-contained**: a single proof package contains everything needed to
  verify a block without network access to the node.
- **Minimal**: SQLite + aiohttp. No external services, no consensus, no P2P.
- **Free**: no economic layer of any kind.

## 2. Non-goals

- Not a blockchain. No consensus, no mining, no gas.
- Not a cryptocurrency. No tokens, no wallets, no staking, no fees.
- Not a distributed system. Single node, single database.
- Not a message queue. Synchronous HTTP only.

---

## 3. Architecture

    ┌──────────────────────────┐
    │  agent_cell.py           │
    │  (Agent Supervisor)      │
    └────────────┬─────────────┘
                 │  POST /api/v1/block  (CellOutput, JSON)
                 ▼
    ┌──────────────────────────┐
    │  qrap-lite/server.py     │  aiohttp
    │  - auth (Bearer)         │
    │  - routing               │
    │  - Prometheus /metrics   │
    └────────────┬─────────────┘
                 │
                 ▼
    ┌──────────────────────────┐
    │  qrap-lite/ledger.py     │
    │  - hash chain            │
    │  - verify_chain          │
    │  - verify_block          │
    │  - get_proof             │
    └────────────┬─────────────┘
                 │
                 ▼
    ┌──────────────────────────┐
    │  qrap-lite/signer.py     │  wraps pq_signer.py
    │  - PQ key in SQLite      │
    │  - hybrid sign / verify  │
    └────────────┬─────────────┘
                 │
                 ▼
    ┌──────────────────────────┐
    │  SQLite: qrap_lite.db    │
    │  - meta (keypair)        │
    │  - blocks (ledger)       │
    └──────────────────────────┘

---

## 4. Data model

Two tables.

    CREATE TABLE meta (
        key   TEXT PRIMARY KEY,
        value TEXT
    );

    CREATE TABLE blocks (
        height      INTEGER PRIMARY KEY AUTOINCREMENT,
        block_id    TEXT UNIQUE NOT NULL,
        prev_hash   TEXT NOT NULL,
        block_hash  TEXT NOT NULL,
        cell_output TEXT NOT NULL,
        signature   TEXT NOT NULL,
        pubkey      TEXT NOT NULL,
        timestamp   TEXT NOT NULL
    );

    CREATE INDEX idx_block_id ON blocks(block_id);

`meta` stores the node PQ key pair (hex-encoded).
`blocks` stores the ledger itself, one row per block.

`height` is a monotonically increasing integer, assigned by SQLite on insert.
It is not used in the hash; only `prev_hash` links blocks.

---

## 5. Block format

The `cell_output` column stores a JSON object produced by the Agent Supervisor.
The minimum required field is `block_id`. Everything else is opaque to
qrap-lite. Typical fields include:

- block_id: string
- cell_id: string
- decision: APPROVED / REFLECTED / BLOCKED
- payload: metrics, activations hash, PoI, hardware attestation, PUF hash
- manifest: entropy manifest (gamma, nu, delta, mu_hash, tau_ms)
- poi_chain: list of hashes proving inspection steps

qrap-lite does not interpret cell_output. It treats it as an opaque blob
and hashes it canonically.

---

## 6. Hash chain

    block_hash = SHA256( prev_hash || canonical_json(cell_output) )

Where `canonical_json` is:

    json.dumps(obj, sort_keys=True, separators=(",", ":"))

For the first block, `prev_hash` is the genesis hash:

    0000...0000  (64 zeros)

This makes every block cryptographically bound to its predecessor:
changing any block breaks the link to all subsequent blocks.

---

## 7. Signature scheme

Signatures are hybrid post-quantum, provided by pq_signer.py.

| Layer | Algorithm | Purpose |
|-------|-----------|---------|
| Classical | SHA-256 / ECDSA | Fast verification |
| Post-quantum | CRYSTALS-Dilithium3 | Quantum-safe |
| Hybrid binding | SHAKE256 (Grover-resistant) | Both must match |

The signed message is:

    {"block_hash": "<hex>"}

The signature object stored in the `signature` column contains:

- classical_sig: hex string
- pq_sig: hex string
- pq_algorithm: "Dilithium3"
- hybrid_hash: SHAKE256(classical_sig || pq_sig), 32 bytes hex
- simulated: boolean (true when liboqs is not installed)

If `liboqs` is not available, the signer falls back to a deterministic
simulation. Signatures in simulation mode are NOT cryptographically secure.
This is reported in every proof package under `verification.simulated`.

---

## 8. Verification levels

qrap-lite supports three levels of verification:

### 8.1 Chain verification

    GET /api/v1/verify

Iterates from genesis to the last block, recomputing every block_hash
and re-verifying every signature. Returns the first inconsistency found.

    {"ok": true, "height": 1247}

or

    {"ok": false, "height": 512, "error": "hash mismatch"}

### 8.2 Single block verification

    GET /api/v1/blocks/{block_id}/verify

Checks only one block: recomputes its hash, checks its prev_hash linkage
against the predecessor, and verifies its signature.

    {"ok": true, "block_id": "b1", "height": 1}

### 8.3 Offline verification

    GET /api/v1/blocks/{block_id}/proof > proof.json
    python3 qrap-lite/verify_proof.py proof.json

The proof package is self-contained. It includes the block, the signature,
the public key, and the hash formula. Anyone can run the verifier without
network access to the node.

The offline verifier reports three checks:

| Check | What it means |
|-------|---------------|
| block_hash | Recomputes SHA256(prev_hash + canonical_json(cell_output)) |
| hybrid_hash | Recomputes SHAKE256(classical_sig + pq_sig) |
| signature_authenticity | null when running in simulated mode |

---

## 9. API contract

All POST endpoints accept `application/json`.
All GET endpoints return `application/json`, except `/metrics`, which returns
Prometheus text exposition format.

| Method | Path | Auth | Success | Errors |
|--------|------|------|---------|--------|
| POST | /api/v1/block | yes* | 201 | 400, 401, 500 |
| GET | /api/v1/block/{block_id} | no | 200 | 404 |
| GET | /api/v1/blocks?limit=N | no | 200 | - |
| GET | /api/v1/blocks/{block_id}/verify | no | 200 | 404 |
| GET | /api/v1/blocks/{block_id}/proof | no | 200 | 404 |
| GET | /api/v1/verify | no | 200 | - |
| GET | /metrics | no | 200 | - |
| GET | /health | no | 200 | - |

* Auth is required only when the environment variable `QRAP_LITE_API_KEY`
is set. In that case, POST requests must carry:

    Authorization: Bearer <key>

GET endpoints remain public in all cases. The rationale: audit must be
readable by anyone, but only authorized clients may append.

---

## 10. Proof package format

    {
      "block_id": "b1",
      "height": 1,
      "prev_hash": "0000...0000",
      "block_hash": "1253a4ce...",
      "cell_output": { ... },
      "signature": {
        "classical_sig": "...",
        "pq_sig": "...",
        "pq_algorithm": "Dilithium3",
        "hybrid_hash": "...",
        "simulated": true
      },
      "pubkey": "6fb32f9d...",
      "timestamp": "2026-09-19T19:58:00+00:00",
      "verification": {
        "algorithm": "Dilithium3",
        "simulated": true,
        "signed_message": {"block_hash": "1253a4ce..."},
        "hash_formula": "block_hash = SHA256(prev_hash + canonical_json(cell_output))",
        "canonical_json": "json.dumps(obj, sort_keys=True, separators=(',', ':'))",
        "steps": [ ... ]
      }
    }

The package is fully self-describing. Verification does not require the
original node, its database, or any external service.

---

## 11. Threat model

### Defended against

| Threat | Defense |
|--------|---------|
| Tampering with stored data | Hash chain breaks at the altered block |
| Forging a signature | Hybrid PQ signature (ECDSA + Dilithium3 + SHAKE256) |
| Reordering blocks | prev_hash chain prevents insertion out of order |
| Silent deletion of a block | Chain breaks: successor's prev_hash becomes invalid |
| Unauthorized appends | Bearer token on POST when QRAP_LITE_API_KEY is set |
| Impersonating the node | pubkey is embedded in every block and proof |

### Not defended against

| Threat | Why |
|--------|-----|
| Full database rewrite from genesis | Single node: attacker with disk access can produce a new valid chain |
| Loss of the node PQ key | Key is stored in SQLite; backup is the operator's responsibility |
| DoS on the HTTP endpoint | No rate limiting today; use a reverse proxy |
| Replay of a valid proof against a different context | Proofs are tied to block_hash, not to any session |

If you need stronger guarantees against full rewrite, replicate the ledger
to a second node and compare chains periodically. This is out of scope
for qrap-lite itself.

---

## 12. Operational notes

### Key storage

The node PQ key pair is generated on first run and stored in the `meta`
table, hex-encoded. It survives restarts. Backups of qrap_lite.db back up
the key as well.

### Database backup

SQLite supports online backup via `VACUUM INTO`. Example:

    sqlite3 qrap_lite.db "VACUUM INTO 'backup.db'"

Or simply copy the file when the server is idle.

### Performance

Append latency on a phone (Termux, ARM64): ~10 ms per block.
Throughput is bounded by SQLite single-writer semantics. For high rates,
batch appends or use WAL mode.

### Logging

Structured logs on stdout. Levels: DEBUG, INFO, WARNING, ERROR.
Set via `--log-level`.

### Metrics

Prometheus format at GET /metrics. Series prefixed with `qrap_lite_`:

| Metric | Type |
|--------|------|
| qrap_lite_blocks_total | Gauge |
| qrap_lite_appends_total | Counter |
| qrap_lite_append_duration_seconds | Histogram |
| qrap_lite_verify_total{scope,result} | Counter |
| qrap_lite_db_size_bytes | Gauge |

---

## 13. Testing

Tests live in `qrap-lite/tests/`.

    cd qrap-lite
    python3 -m pytest tests/ -v

Coverage:

- Ledger: genesis block, chain linkage, tamper detection, per-block verify,
  proof package shape, missing-block handling, hash determinism.
- Server: all endpoints, Bearer auth (missing / wrong / correct token),
  open mode, 404 paths, metrics output.

Current status: 24 tests, all passing.

---

## 14. Extensions

Deliberately not implemented. Possible future work:

- Multi-node replication with chain comparison.
- Optional external anchoring (publish a daily Merkle root somewhere).
- Rate limiting / per-client quotas.
- gRPC transport in addition to HTTP.
- Compression of large cell_output payloads.

None of these are required for the core guarantee: append-only,
tamper-evident, offline-verifiable audit.

---

## 15. Design invariants

These must hold at all times. Any change that violates them is not a
compatible change.

- `height` is strictly increasing by 1 per appended block.
- For every block N > 1, `prev_hash(N) == block_hash(N-1)`.
- For every block, `block_hash == SHA256(prev_hash + canonical_json(cell_output))`.
- For every block, the stored signature verifies against `{"block_hash": block_hash}`.
- Blocks are never updated or deleted through the API.
- The genesis prev_hash is 64 zero characters.
