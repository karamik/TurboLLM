# TurboLLM — User Guide

A provable, free AI platform. Every decision is cryptographically signed,
hash-chained, and auditable offline. No tokens, no staking, no fees,
no wallets, no USDT.

## Table of contents

1. Requirements
2. Installation
3. Download a model
4. Run the services
5. First request
6. Verify a proof offline
7. Audit the ledger
8. Governance: arbitration and voting
9. Monitoring
10. What you get

---

## 1. Requirements

| Variant | What is possible |
|---------|------------------|
| NVIDIA RTX 4090 / 6000 Ada / H100, 24 GB+ VRAM | Full mode: models up to 70B, context 100k+ |
| RTX 3090 / 4080, 12-16 GB | Models up to 13B, context 32k |
| No GPU (phone, laptop) | Simulation mode: qrap-lite works, LLM does not |
| TOTAL-Neuro chip present | Full attestation: PUF binding to hardware |
| No chip | Attestation falls back, event is logged |

---

## 2. Installation

    git clone https://github.com/karamik/TurboLLM.git
    cd TurboLLM

    pip install -r requirements.txt

    # Optional: GPU stack
    pip install -r requirements-gpu.txt

    # Optional: real PQ signatures (not simulation)
    pip install liboqs-python

After installation you get:

- LLM inference (vLLM + FP8),
- G-Space Inspector,
- Agent Supervisor,
- qrap-lite (audit ledger),
- pq_signer (hybrid PQ signatures).

---

## 3. Download a model

    python scripts/download_model.py \
        --model meta-llama/Meta-Llama-3-70B \
        --quant fp8

FP8 halves memory usage. 70B fits on 24 GB VRAM with long context.

---

## 4. Run the services

Three processes. Three terminals, or three background jobs.

Terminal 1 — LLM Core:

    python -m turbollm.serve --model /path/to/model --port 8000

Terminal 2 — audit ledger:

    cd qrap-lite
    python run.py --port 50051 --db qrap_lite.db

On first run, an SQLite database is created and a node PQ key is generated.
The key survives restarts.

Terminal 3 — Agent Supervisor:

    export TURBOLLM_ENDPOINT="http://localhost:8000/v1"
    export CLUSTER_ENDPOINT="http://localhost:50051/api/v1/block"
    python agent_cell.py

The agent listens on :8080. It performs hardware attestation, runs G-Space
inspection, signs a Proof of Inspection, and writes the CellOutput to the ledger.

---

## 5. First request

Initialize a session:

    curl -X POST http://localhost:8080/session/init

Send a task:

    curl -X POST http://localhost:8080/process \
      -H "Content-Type: application/json" \
      -H "X-Session-Id: <session_id>" \
      -d '{"task": "Analyze this contract and highlight risks"}'

What happens under the hood (200-800 ms):

1. Hardware attestation
   - The agent reads the PUF hash of the TOTAL-Neuro chip.
   - Checks shield_ok, signature_ok, attestation_ok.
   - On failure: HTTP 403, request blocked.

2. Inference
   - The task is sent to vLLM.
   - The model produces an answer and intercepts hidden activations.

3. G-Space Inspector
   - Spectral analysis (FFT + entropy).
   - Cosine drift against the adaptive reference.
   - ML classifier for anomaly detection.
   - Decision: APPROVED / REFLECTED / BLOCKED.
     - APPROVED: answer is clean.
     - REFLECTED: re-prompt with a corrective instruction.
     - BLOCKED: answer discarded, client gets a refusal.

4. Proof of Inspection
   - A CellOutput is built with: supervisor decision, metrics, ECDSA +
     Dilithium3 signature, hybrid hash via SHAKE256, PUF hash of the chip,
     and a block_id.

5. Append to qrap-lite
   - block_hash = SHA256(prev_hash + canonical_json(cell_output))
   - The node signs block_hash.
   - height increases by 1.

Response:

    {
      "status": "ok",
      "supervisor_status": "APPROVED",
      "cell": {
        "block_id": "...",
        "payload": {
          "confidence": 0.94,
          "g_entropy": 0.31,
          "cosine_drift": 0.07,
          "proof_of_inspection": "...",
          "puf_hash": "a3f4...",
          "hardware_attestation": { ... }
        }
      },
      "delivered": true
    }

---

## 6. Verify a proof offline

Export the proof package:

    curl http://localhost:50051/api/v1/blocks/<block_id>/proof > proof.json

Hand it to any third party. They verify it offline, without access to
the node:

    python3 qrap-lite/verify_proof.py proof.json

    {
      "ok": true,
      "checks": [
        {"name": "block_hash", "ok": true},
        {"name": "hybrid_hash", "ok": true},
        {"name": "signature_authenticity", "ok": null,
         "note": "requires liboqs + real PQ mode"}
      ]
    }

What this proves:

- data has not been tampered with (block_hash matches),
- signature has not been forged (hybrid_hash matches),
- in real mode with liboqs, additionally: PQ signature authenticity.

---

## 7. Audit the ledger

List recent blocks:

    curl "http://localhost:50051/api/v1/blocks?limit=20"

Verify the entire chain:

    curl http://localhost:50051/api/v1/verify
    # {"ok": true, "height": 1247}

If someone modified the database directly:

    {"ok": false, "height": 512, "error": "hash mismatch"}

The chain breaks at the first altered block. That is provability.

---

## 8. Governance: arbitration and voting

Submit a dispute:

    curl -X POST http://localhost:8080/arbitrate \
      -H "Content-Type: application/json" \
      -d '{
        "case_id": "case_001",
        "company_id": "acme",
        "title": "Contract dispute",
        "parties": ["Party A", "Party B"],
        "arguments": {"Party A": "...", "Party B": "..."},
        "evidence": ["link1", "link2"]
      }'

A multi-agent cluster:

- analyzes arguments through G-Space,
- returns a verdict with rationale and confidence,
- signs the verdict with a PQ signature,
- writes it to the ledger.

Vote on supervisor parameters:

    curl -X POST http://localhost:8080/vote \
      -H "Content-Type: application/json" \
      -H "X-Session-Id: <session_id>" \
      -d '{"proposal": "raise_confidence_threshold", "value": 0.85}'

Every vote is signed, recorded, and immutable.

---

## 9. Monitoring

Grafana dashboard (turbollm_dashboard.json) shows:

- G-Space: spectral anomalies, cosine drift, entropy per layer.
- Supervisor: APPROVED / REFLECTED / BLOCKED counts.
- qrap-lite: block count, append rate, latency p50/p95/p99, verify calls,
  database size.
- Alerts to Telegram/Slack: cache >90%, queue growth, anomalies above
  threshold.

Prometheus scrape config is in configs/prometheus.yml.

qrap-lite exposes metrics at:

    GET http://localhost:50051/metrics

Series (prefix qrap_lite_):

| Metric | Type | Meaning |
|--------|------|---------|
| qrap_lite_blocks_total | Gauge | Current number of blocks |
| qrap_lite_appends_total | Counter | Successful POST /api/v1/block |
| qrap_lite_append_duration_seconds | Histogram | Latency of ledger.append |
| qrap_lite_verify_total{scope,result} | Counter | verify calls by result |
| qrap_lite_db_size_bytes | Gauge | Size of the SQLite file |

---

## 10. What you get

| Ordinary LLM | TurboLLM |
|--------------|----------|
| Answer without explanation | Answer + confidence metrics |
| No guarantees | Proof of Inspection on every step |
| No hardware binding | PUF hash of the chip |
| Cannot verify after the fact | Append-only ledger with hash chain |
| Quantum-vulnerable signatures | ECDSA + Dilithium3 + SHAKE256 |
| Trust the vendor | Trust the math |
| Pay per token | Free, local |

Who needs this:

- Legal: prove that an AI decision was made correctly.
- Medicine: audit diagnostic suggestions.
- Defense and aerospace: verifiable decisions on isolated systems.
- Companies: arbitrate disputes without a third party.
- Regulators: inspect AI without access to internals.


