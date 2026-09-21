

# 🚀 TurboLLM – Platform for Provable and Safe AI

Ultra-fast inference + internal activation-level control + decentralised verification + arbitration & voting.

Run models up to 70B on consumer GPUs with 100k+ token context, and get not just answers, but provable decisions certified by a distributed ledger.

License Python vLLM QRAP CI Hardware Attestation CI

## 🤯 The Problem – Why AI Remains a Black Box

❌ Long contexts kill memory (OOM) and speed.  
❌ No trust – models can hallucinate without explanation.  
❌ Manipulations – jailbreaks go unnoticed.  
❌ Decisions are not auditable – you cannot verify how an answer was produced.  
❌ Corporate disputes lack unbiased, verifiable arbitration.  
❌ Voting and governance are vulnerable to manipulation.

We solve all of this. Not just by speeding up inference, but by looking under the hood of the model and providing cryptographic proof of every decision.

## 💡 Our Solution – More Than Just an Engine

TurboLLM is an ecosystem of four integrated layers:

1. **Inference Core (open source)** – FP8, PagedAttention, Chunked Prefill, Speculative Decoding.  
2. **G‑Space Inspector** – real-time analysis of hidden activations with spectral and drift detection.  
3. **Agent Supervisor + QRAP** – self-healing agents, ledger-based decision verification, and Proof of Inspection (PoI).  
4. **Governance Suite** – arbitration, voting, and immutable company history.

## 🧠 Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                   External Request / Task                    │
│         (prompt, arbitration case, vote, etc.)              │
└────────────────────────┬─────────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────────┐
│   Agent Supervisor (agent_cell.py)                          │
│   - G‑Space analysis (hidden activations, spectral, drift)  │
│   - Decision: APPROVED / REFLECTED / BLOCKED                │
│   - Self‑healing (reflection on uncertainty)                │
│   - Proof of Inspection (PoI) generation                    │
└────────────────────────┬─────────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────────┐
│   TurboLLM Core (vLLM + FP8 + PagedAttention)               │
│   - Fast inference with 100k+ token context                 │
│   - Hidden states interception                               │
└────────────────────────┬─────────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────────┐
│   QRAP Ledger                                               │
│   - CellOutput recording (decision + metrics + PoI)         │
│   - Arbitration verdicts, votes, corporate history          │
│   - No tokens, no staking, no fees                          │
└──────────────────────────────────────────────────────────────┘
```

## ⚡ Key Features

### 1. Ultra‑Fast Inference on Long Contexts

- FP8 quantisation of weights and KV‑cache – 2× less memory.
- PagedAttention – eliminates fragmentation, linear scaling.
- Chunked Prefill – first token in milliseconds even on 100k tokens.
- Speculative Decoding – up to 2.5× faster generation.

### 2. G‑Space Inspector – Controlling the Model’s “Thoughts”

- Analyses hidden activations (neural representations) before token generation.
- Detects hallucinations, jailbreaks, manipulations at an early stage.
- Multi‑layer spectral analysis (FFT + entropy) catches subtle manipulation patterns.
- Cosine drift detection against adaptive reference vectors.
- Uses an ML classifier trained on synthetic and real data.
- Overhead < 5 ms per request.

### 3. Self‑Healing Agent Supervisor with Proof of Inspection (PoI)

- Decides: approve, block, or trigger reflection.
- Reflection – re‑prompts the model with a corrective instruction.
- Adaptive reference – updates the “clean” baseline after each approved request.
- Cryptographic Proof of Inspection – every decision is signed, proving that the G‑Space analysis actually occurred and wasn’t bypassed.
- Logs all actions and metrics to QRAP for auditing.

### 4. Governance Suite

- **Decentralised Arbitration** – submit disputes; the multi‑agent cluster with G‑Space analysis returns a verifiable verdict with rationale and confidence.
- **Tamper‑proof Voting** – votes are recorded on‑ledger, each vote is signed cryptographically. Anti‑spam is handled by rate limits and reputation, not fees.
- **Immutable Company History** – every arbitration, vote, and major decision becomes part of a permanent, auditable ledger.

### 5. Governance and Access (QRAP)

- On registration, users get a QRAP identity and cryptographic keypair.
- Voting rights on supervisor parameters (confidence thresholds, agent count) are assigned by role and reputation, not by tokens.
- API access is governed by policy and quotas.
- No tokens, no staking, no exchange, no pay‑per‑use.

### 6. Additional Modules (Optional)

| Module | What it does |
|--------|--------------|
| Smart Load Balancer | Adaptive routing across GPUs/nodes, eliminating hot spots. |
| Prompt Cache | Caches KV‑prefixes of frequent prompts – saves up to 70% compute. |
| Data Security & Filtering | Scans inputs/outputs for PII, secrets, injections. |
| Admin Dashboard | Web UI with usage graphs, audit logs, governance management, and spectral metrics visualisation. |
| Custom Authentication | SSO (OAuth2, LDAP), API key management. |
| G‑Space Inspector Pro | Advanced ML classifier with spectral and drift analysis, adaptive reference, and PoI. |

## 🔐 Hardware Attestation (TOTAL‑Neuro Integration)

Every request through the TurboLLM Agent is cryptographically bound to a physical chip via the TOTAL‑Neuro hardware attestation layer.

### How it works

Before processing any request, the agent queries the attached neuromorphic chip through the Linux driver:

1. **PUF ID retrieval** — the chip returns a unique 128-bit fingerprint derived from physical silicon variations.
2. **Security status check** — Active Shield, firmware signature, key unlock status, and zeroization flag are read.
3. **Attestation decision** — if any check fails, the request is blocked with HTTP 403.

### What gets verified

| Check | Meaning |
|-------|---------|
| `shield_ok` | Active Shield mesh is intact (no physical intrusion). |
| `chip_unlocked` | eFuse key matches — chip is authorized. |
| `signature_ok` | Firmware signature verified (ECDSA). |
| `attestation_ok` | PUF stability confirmed. |
| `zeroize_active` | If HIGH — chip is in emergency wipe mode, request blocked. |

### Hardware Attestation in the Agent

The `agent_cell.py` calls `hardware_attestation.py` automatically. If the chip fails authentication, the request is blocked with HTTP 403.

If the chip is unavailable (e.g. running in simulation mode), the agent falls back gracefully and logs the event.

### PUF hash in Proof of Inspection

Each decision includes a `puf_hash` — SHA-256 of the chip's PUF ID with a unique salt. This hash is added to the `poi_chain` and submitted to QRAP for immutable audit.

### Compliance and auditing

- Every decision is traceable to a specific chip (via PUF).
- Proof packages can be replayed and verified offline.
- Suitable for legal, medical, defence, and aerospace applications.

## 🔐 Post-Quantum Signatures

Every proof package is signed with hybrid post-quantum cryptography:

| Layer | Algorithm | Purpose |
|-------|-----------|---------|
| Classical | SHA-256 / ECDSA | Fast verification |
| Post-Quantum | CRYSTALS-Dilithium3 | Quantum-safe |
| Hybrid binding | SHAKE256 (Grover-resistant) | Both must match, 256-bit quantum security |

### Why hybrid?

- Today: ECDSA is secure.
- Post-quantum era: Shor breaks ECDSA, but Dilithium remains secure.
- Hybrid: attacker must break both.

### Graceful fallback

If `liboqs` is not installed, simulated mode is used. Production: `pip install liboqs-python`.

### Status

- 14 unit tests (sign, verify, tampering).
- Integrated into CI (`ci-attestation.yml`).

## 📊 Comparison with Alternatives

| Approach | Speed | Context | Security | Audit | Arbitration | Voting |
|----------|-------|---------|----------|-------|-------------|--------|
| Hugging Face | 🟡 | 🔴 | 🔴 | 🔴 | 🔴 | 🔴 |
| Plain vLLM | 🟢 | 🟢 | 🟡 | 🔴 | 🔴 | 🔴 |
| TensorRT‑LLM | 🟢 | 🟢 | 🔴 | 🔴 | 🔴 | 🔴 |
| TurboLLM + G‑Space + QRAP | 🟢 | 🟢 | 🟢 | 🟢 | 🟢 | 🟢 |

## 🚦 Quick Start

```bash
# Clone
git clone https://github.com/karamik/TurboLLM.git
cd TurboLLM

# Install dependencies
pip install -r requirements.txt

# Download a model (e.g., Llama‑3‑70B in FP8)
python scripts/download_model.py --model meta-llama/Meta-Llama-3-70B --quant fp8

# Start the server with G‑Space Inspector
python -m turbollm.serve --model /path/to/model --port 8000

# In another terminal – launch the agent supervisor
export TURBOLLM_ENDPOINT="http://localhost:8000/v1"
export CLUSTER_ENDPOINT="http://<qrap-ip>:<port>/api/v1/block"
python agent_cell.py
```

### Use the API

- Regular prompt: `POST /process`
- Streaming prompt: `POST /stream`
- Arbitration: `POST /arbitrate` (structured case)
- Vote: `POST /vote`

Example arbitration request:

```bash
curl -X POST http://localhost:8080/arbitrate \
  -H "Content-Type: application/json" \
  -H "X-Session-Id: your_session_id" \
  -d '{
    "case_id": "case_001",
    "company_id": "acme",
    "title": "Contract dispute",
    "description": "...",
    "parties": ["Party A", "Party B"],
    "arguments": {"Party A": "...", "Party B": "..."},
    "evidence": ["link1", "link2"]
  }'
```

## 🖥️ Hardware Requirements

- GPU: NVIDIA Ada Lovelace (RTX 4090, RTX 6000 Ada), Hopper (H100), or newer.
- VRAM: 24 GB+ recommended for 70B models with long contexts.
- CUDA: 11.8+.

## 📦 Deployment (Docker / Kubernetes)

```bash
docker-compose -f docker-compose.yml -f docker-compose.override.yml up -d
```

Ready‑to‑use Helm charts for Kubernetes are in `deploy/helm`.

## 📈 Monitoring & Alerts

- Prometheus metrics: latency (TTFT, TPOT), KV‑cache usage, request queue, spectral anomalies, cosine drift.
- Grafana dashboards with G‑Space visualisations, spectral metrics, and supervisor status.
- Alerts in Telegram/Slack when cache >90%, queue grows, or spectral anomalies exceed threshold.

## 🔒 Audit Ledger (qrap-lite)

Free, append-only ledger for provable auditing of AI decisions.
Every CellOutput is hash-chained and PQ-signed. No tokens, no fees, no wallets.

- Service: `qrap-lite/` — SQLite + aiohttp + hybrid PQ signatures.
- Docs: [qrap-lite/README.md](qrap-lite/README.md)
- API: `POST /api/v1/block`, `GET /api/v1/block/{id}`, `GET /api/v1/blocks/{id}/verify`, `GET /api/v1/blocks/{id}/proof`, `GET /api/v1/verify`
- Optional Bearer auth via `QRAP_LITE_API_KEY`.
- Integration: `export CLUSTER_ENDPOINT="http://localhost:50051/api/v1/block"`

## 🏛️ Governance roles

Four explicit roles, each with a trace in the same append-only ledger.
See `docs/security-protocol.md` for the reasoning.

| Role | Document | Code |
|------|----------|------|
| **Legislator** | [docs/manifesto.md](docs/manifesto.md) | `qrap-lite/anchor_manifesto.py` (auto-anchored on first run) |
| **Classifier** | [docs/security-protocol.md](docs/security-protocol.md) | `qrap-lite/classifier.py` |
| **Operator** | [docs/security-protocol.md](docs/security-protocol.md) | `qrap-lite/operator_cli.py` |
| **Factory owner** | [docs/firmware-registry.md](docs/firmware-registry.md) | `qrap-lite/verify_registry.py` |

None of these roles is "external" to the system. None is powerless.
Each is named, constrained, and leaves a cryptographic trace.

## 📬 Contact & Support

For technical support and integration questions:

👉 @tec_support_bot (Telegram)

## 📄 License

MIT © TurboLLM Team
