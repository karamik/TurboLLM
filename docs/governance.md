# Governance

How the four centers of power in this system are connected, constrained,
and where each lives in code.

This document is a map. It does not add new rules. It shows how existing
pieces fit together.

---

## 1. Why this document exists

The Manifesto states what the system does not do to a human.
The Security Protocol states that power cannot be eliminated, only
distributed and made visible.

This document closes the loop: it shows, in one place, where each center
of power actually is, what document defines it, and which file implements it.

If any of these three get out of sync with each other, the system is not
governed - it is just described.

---

## 2. The four roles

### 2.1. Legislator

Defines what counts as a violation.

- **Document:** `docs/manifesto.md`
- **Code:** `qrap-lite/anchor_manifesto.py`
- **Trace:** the manifesto hash is written as the genesis block of
  `qrap-lite`. It is signed with the node's PQ key. It cannot be rewritten.
- **Automatic behavior:** on first server start, if the ledger is empty
  and `docs/manifesto.md` exists, the hash is anchored automatically.

**What they cannot do:** silently change the manifesto after it has been
anchored. The API `GET /api/v1/manifesto` recomputes the file hash and
reports `match: true/false`.

### 2.2. Classifier

Turns the manifesto into rules. Signals possible violations.

- **Document:** `docs/security-protocol.md` (Part 2)
- **Code:** `qrap-lite/classifier.py`
- **Trace:** every signal carries rule id, rule version, evidence, and
  rule confidence. The classifier does not write to the ledger.

**What they cannot do:** act. Punish. Modify the ledger. The classifier
is read-only by design.

### 2.3. Operator

Reads the log. Decides what to do with recorded facts.

- **Document:** `docs/security-protocol.md` (Part 3.3)
- **Code:** `qrap-lite/operator_cli.py`
- **Trace:** every operator action is recorded as a signed block in the
  same ledger the operator reads. There is no separate audit trail.

**What they cannot do:** act secretly. Roll back a decision without it
being visible. Change the manifesto.

### 2.4. Factory owner

Fuses silicon. Holds root keys.

- **Document:** `docs/firmware-registry.md`
- **Code:** `qrap-lite/verify_registry.py`
- **Trace:** every registry entry is signed. Every firmware hash and PUF
  hash can be verified offline against a root key list.

**What they cannot do:** alter an already-shipped chip without physical
access. Hide the fact of a firmware fusion.

---

## 3. How the four are connected

    Legislator                    Classifier                 Operator
    ──────────                    ──────────                 ────────
    manifesto.md   ────signs───►  classifier.py ───reads──►  operator_cli.py
         │                              │                          │
         │                              │                          │
         ▼                              ▼                          ▼
    ┌──────────────────────────────────────────────────────────────┐
    │                       qrap-lite ledger                        │
    │   append-only · hash chain · hybrid PQ signatures · offline   │
    └──────────────────────────────────────────────────────────────┘
                                        ▲
                                        │
    ┌───────────────────────────────────┴──────────────────────────┐
    │                     Factory owner                            │
    │   firmware registry · PUF binding · offline verification      │
    └──────────────────────────────────────────────────────────────┘

Every arrow is a signed artifact. Every artifact is verifiable offline.
No arrow can be erased without breaking the hash chain.

---

## 4. Where to look for what

| Question | Look at |
|----------|---------|
| What does the system promise not to do? | `docs/manifesto.md` |
| Why is power distributed this way? | `docs/security-protocol.md` |
| How is a chip's identity proved? | `docs/firmware-registry.md` |
| How do I use the system? | `docs/user-guide.md` |
| What is qrap-lite internally? | `docs/qrap-lite.md` |
| How do I anchor the manifesto? | `qrap-lite/anchor_manifesto.py` |
| How do I run the classifier? | `qrap-lite/classifier.py --help` |
| How do I record an operator action? | `qrap-lite/operator_cli.py --help` |
| How do I verify a registry offline? | `qrap-lite/verify_registry.py --help` |
| How do I verify a proof offline? | `qrap-lite/verify_proof.py --help` |

---

## 5. What this governance does NOT cover

- How to decide if a Manifesto is good.
- Who has the right to change it.
- What sanctions are permissible.
- How to reconcile freedom with catastrophic consequences.
- How to guarantee that the operator is honest.
- How to guarantee that the factory owner is not planting backdoors.

These are political questions. The protocol does not answer them.
It only makes them visible, and makes the trace of every decision
impossible to erase silently.

---

## 6. Minimal guarantees

If all four roles are implemented and every artifact is signed:

- The Manifesto cannot be changed without detection.
- Every classifier signal is recorded with its rule version.
- Every operator action is recorded as a signed block.
- Every chip can be traced to a registry entry.
- The entire chain can be verified offline.

This is not a guarantee of good behavior. It is a guarantee of
**visibility**. Nothing more, and nothing less.
