#QRAP_LITE_README_V6
# qrap-lite

A minimal append-only ledger for provable auditing of TurboLLM decisions.
Free. No tokens, no staking, no fees, no wallets, no USDT.

## What it is

qrap-lite is a small HTTP service that:

1. Accepts POST /api/v1/block with a JSON body (CellOutput from agent_cell.py).
2. Computes a hash chain: block_hash = SHA256(prev_hash || canonical_json(cell_output)).
3. Signs block_hash with a hybrid post-quantum signature via pq_signer.py
   (ECDSA + Dilithium3 + SHAKE256).
4. Stores the block in SQLite.
5. Exposes read and verify endpoints over HTTP.

## Why

Provable audit: every AI decision can be verified - that it happened, when,
with what confidence, which chip computed it (via puf_hash inside cell_output),
and that the record has not been modified since.

## Run

    cd qrap-lite
    python run.py --port 50051 --db qrap_lite.db

On the first run, an SQLite database is created and a node key is generated
and stored inside that same database. The key survives restarts.

## Authentication

By default the server runs open (no auth). To require a Bearer token on
POST endpoints, set the environment variable QRAP_LITE_API_KEY before start:

    export QRAP_LITE_API_KEY="change_me"
    python run.py --port 50051 --db qrap_lite.db

When the key is set:

- POST /api/v1/block requires the header:  Authorization: Bearer <key>
- All GET endpoints remain public (audit must be readable).

When the key is not set:

- All endpoints are open. Use only on localhost or behind a trusted proxy.

## API

| Method | Path                                | Auth | Description                                    |
|--------|-------------------------------------|------|------------------------------------------------|
| POST   | /api/v1/block                       | yes* | Accept CellOutput, sign it, append to ledger   |
| GET    | /api/v1/block/{block_id}            | no   | Return a block by block_id                     |
| GET    | /api/v1/blocks?limit=N              | no   | List the most recent blocks                    |
| GET    | /api/v1/blocks/{block_id}/verify    | no   | Verify a single block                          |
| GET    | /api/v1/blocks/{block_id}/proof     | no   | Export a full proof package for a block        |
| GET    | /api/v1/verify                      | no   | Verify the integrity of the entire hash chain  |
| GET    | /health                             | no   | Liveness probe                                 |
| GET    | /metrics                            | no   | Prometheus metrics                             |
| GET    | /api/v1/manifesto                   | no   | Manifesto anchor (hash + signature)            |

* Auth only when QRAP_LITE_API_KEY is set.

## Examples

    # Liveness
    curl http://localhost:50051/health

    # Append a block (open mode)
    curl -X POST http://localhost:50051/api/v1/block \
      -H "Content-Type: application/json" \
      -d '{"block_id":"b1","decision":"APPROVED","confidence":0.97}'

    # Append a block (with Bearer token)
    curl -X POST http://localhost:50051/api/v1/block \
      -H "Authorization: Bearer change_me" \
      -H "Content-Type: application/json" \
      -d '{"block_id":"b2","decision":"BLOCKED","confidence":0.42}'

    # Get a block
    curl http://localhost:50051/api/v1/block/b1

    # Verify a single block
    curl http://localhost:50051/api/v1/blocks/b1/verify

    # List recent blocks
    curl "http://localhost:50051/api/v1/blocks?limit=10"

    # Verify the whole chain
    curl http://localhost:50051/api/v1/verify

## Manifesto anchoring

The Manifesto (see `docs/manifesto.md`) can be anchored as the genesis
block of a fresh ledger. Its SHA-256 hash is written into the first block,
signed with the node PQ key, and becomes immutable.

    cd qrap-lite
    python3 anchor_manifesto.py --db qrap_lite.db --manifesto ../docs/manifesto.md

This resets a non-empty ledger unless it is already empty. Use `--force`
to overwrite an existing database.

After anchoring:

    curl http://localhost:50051/api/v1/manifesto

Returns the anchor block, the stored manifesto hash, and a live check
against the file on disk:

    {
      "anchored": true,
      "block_id": "manifesto",
      "height": 1,
      "manifesto_hash": "...",
      "manifesto_hash_current": "...",
      "match": true,
      "signature": { ... },
      "pubkey": "..."
    }

If `match` is false, the file `docs/manifesto.md` was changed after the
anchor was written. The ledger still proves what was originally anchored.

## Classifier and operator

Two separate roles, deliberately kept apart.

### Classifier

Reads the ledger, applies transparent rules, produces a report.
Does not write to the ledger. Does not act. Only signals.

    cd qrap-lite
    python3 classifier.py --endpoint http://localhost:50051 --out report.json

Rules (version 1.0):

| Rule | Severity | Triggers when |
|------|----------|---------------|
| R1 chain_integrity | CRITICAL | verify returns ok=false |
| R2 consecutive_blocks | WARNING | 3+ consecutive BLOCKED decisions |
| R3 high_drift | WARNING | cosine_drift > 0.30 |
| R4 low_confidence | WARNING | confidence < 0.50 |
| R5 block_rate_spike | INFO | >100 blocks in last 60 minutes |

Each signal records rule id, rule version, evidence, and rule_confidence
(the confidence in the rule itself, not in the signal).

### Operator

Reads the ledger, runs the classifier, and records actions.

    cd qrap-lite
    python3 operator_cli.py --db qrap_lite.db status
    python3 operator_cli.py --db qrap_lite.db blocks --limit 20
    python3 operator_cli.py --db qrap_lite.db classify --endpoint http://localhost:50051
    python3 operator_cli.py --db qrap_lite.db log-action \
        --operator alice --action investigate --target b42 --note "high drift"

Every operator action is recorded as a signed block in the same ledger the
operator reads. There is no separate audit trail. There is no way to record
an action that leaves no trace.

See `docs/security-protocol.md` for the reasoning behind this split.

## Prometheus metrics

GET /metrics exposes the following series (prefix qrap_lite_):

| Metric | Type | Meaning |
|--------|------|---------|
| qrap_lite_blocks_total | Gauge | Current number of blocks in the ledger |
| qrap_lite_appends_total | Counter | Successful POST /api/v1/block calls |
| qrap_lite_append_duration_seconds | Histogram | Latency of ledger.append |
| qrap_lite_verify_total{scope,result} | Counter | verify calls (chain or block) by result |
| qrap_lite_db_size_bytes | Gauge | Size of the SQLite ledger file |

Scrape config for Prometheus:

    scrape_configs:
      - job_name: qrap-lite
        static_configs:
          - targets: ["localhost:50051"]

## Offline verification

Every block can be exported as a self-contained proof package:

    curl http://localhost:50051/api/v1/blocks/b1/proof > proof.json
    python3 qrap-lite/verify_proof.py proof.json

The verifier checks:

- block_hash: SHA256(prev_hash + canonical_json(cell_output)) matches.
- hybrid_hash: SHAKE256(classical_sig + pq_sig) matches.
- signature authenticity: requires liboqs in real PQ mode; reported as
  null when running in simulated mode.

The proof package contains everything needed to verify the block without
network access to the node. Anyone can hold it, re-run the checks offline,
and confirm the record has not been altered since it was appended.

## Database schema

    CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE blocks (
        height INTEGER PRIMARY KEY AUTOINCREMENT,
        block_id TEXT UNIQUE NOT NULL,
        prev_hash TEXT NOT NULL,
        block_hash TEXT NOT NULL,
        cell_output TEXT NOT NULL,
        signature TEXT NOT NULL,
        pubkey TEXT NOT NULL,
        timestamp TEXT NOT NULL
    );

## Guarantees

- Append-only: blocks are never deleted or modified through the API.
- Hash chain: modifying any block breaks verify for it and all following blocks.
- PQ signature: forgery requires breaking both ECDSA and Dilithium3 simultaneously.
- Persistent key: the node key lives in the database and survives restarts.
- Tamper detection: GET /api/v1/verify returns
  {"ok": false, "height": N, "error": "..."} if the chain has been altered.
- Per-block verification: GET /api/v1/blocks/{id}/verify checks the block,
  its prev_hash linkage, and its signature without scanning the whole chain.

## Integration with TurboLLM

In agent_cell.py:

    export CLUSTER_ENDPOINT="http://localhost:50051/api/v1/block"
    export CLUSTER_API_KEY="change_me"   # only if QRAP_LITE_API_KEY is set

## Limitations

- No consensus: single node, single database.
- No P2P: HTTP only.
- No decentralization: this is a ledger, not a blockchain network.
- Multi-node replication is out of scope.

This is intentional: the goal is provable audit, not a crypto network.
