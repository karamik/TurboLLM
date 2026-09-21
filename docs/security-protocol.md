# Security Protocol

## A map of distributed power, judgment, and hardware invariants

### 0. Purpose of this document

This document has one goal: **not to hide the arbiter behind terminology,
but to show them in the face**.

We proceed from the fact that power cannot be eliminated architecturally.
It can be divided, named, and constrained. Any protocol that promises the
"absence of power" is either self-deception or a way to mask it.

---

## Part 1. The illusion of "pure cryptography"

Cryptography verifies three things:

- **identity** - whether it is the same key,
- **integrity** - whether the bytes have been changed,
- **origin** - whether it was signed by a known key.

Cryptography does **not** verify:

- meaning,
- intent,
- morality,
- correctness of a decision,
- conformity with the Manifesto.

Conclusion: any "hardware safety switch" that reacts to a "violation"
contains within itself a judgment about what counts as a violation. The
question is not how to remove judgment. The question is **how to distribute
it explicitly**.

---

## Part 2. Four centers of power

In any system that implements the Manifesto, there are four roles. Each is
a person or a group of people. None is "external" to the system.

1. **Legislator** - writes and signs the Manifesto. Defines what counts as
   a violation.
2. **Classifier** - turns the Manifesto into rules. Defines what **looks**
   like a violation.
3. **Operator** - reads the log and reacts. Defines what **to do** with the
   recorded facts.
4. **Factory owner** - fuses silicon, holds root keys. Defines what is
   **technically possible**.

Each of the four leaves a trace. None can act fully secretly if the log is
truly immutable.

---

## Part 3. What each does, what constrains each

### 3.1. Legislator

**Can:** define the text of the Manifesto, choose a version, revoke an old
version.

**Constrained by:**
- the impossibility of foreseeing all cases;
- the impossibility of rewriting the past;
- the fact that every version of the Manifesto is signed, and its hash is
  written to the log.

**Trace:** hash of each version of the Manifesto, timestamp, signing key.

**Cannot:** alter an already-signed Manifesto without detection; hide the
fact that a new version was issued.

### 3.2. Classifier

**Can:** signal a possible deviation from the Manifesto.

**Constrained by:**
- no right to punish;
- no right to change invariants;
- no right to write to the log, only to read from it;
- its model, thresholds, and version are publicly fixed.

**Trace:** every classifier trigger is written to the log with the model
version, input data, and confidence.

**Cannot:** act autonomously; initiate sanctions; change system state.

### 3.3. Operator

**Can:** react to recorded facts. Stop a cluster, rotate keys, open an
investigation, ignore a signal.

**Constrained by:**
- cannot alter the log;
- cannot alter the Manifesto;
- cannot rewrite classifier triggers;
- every action is recorded.

**Trace:** every operator action is written to the same log the operator reads.

**Cannot:** act secretly; roll back the consequences of a decision without
detection.

### 3.4. Factory owner

**Can:** fuse silicon; embed root key; define what is technically possible.

**Constrained by:**
- cannot change what has already been fused (without physical intervention,
  which leaves a trace);
- cannot revoke keys issued independently by others;
- cannot hide the fact of fusing from the registry.

**Trace:** firmware registry - who, when, what, signed with which key.

**Cannot:** secretly alter the behavior of an already-shipped chip without
physical access to it.

---

## Part 4. Explicit map of judgments

| Judgment point | Who exercises it | What constrains them |
|---|---|---|
| What counts as a violation | Legislator | Manifesto version, signature, history |
| What looks like a violation | Classifier | Model transparency, thresholds, version |
| What to do with recorded facts | Operator | Action transparency, the same log |
| What is technically possible | Factory owner | Firmware registry, physical constraints |

None of these points is "technical" in the sense of "powerless". All four
are political. All four are explicitly named.

---

## Part 5. Invariants - what is cryptographically verifiable

This is the list of things that can truly be verified mathematically.
Everything else is judgment.

- **Integrity**: a data block is unchanged after being written.
- **Origin**: a block is signed by a key bound to a specific PUF.
- **Linkage**: every block references the previous one via a hash.
- **Non-rewritability**: the chain cannot be altered without breaking.
- **Manifesto authenticity**: a Manifesto version is signed by a known key.

None of these invariants says what counts as "good" or "bad". They are all
about **identity and integrity**, not about meaning.

---

## Part 6. What remains politics and does not reduce to code

- Defining what counts as a "violation".
- Defining what counts as a "false trigger".
- Deciding what to do with recorded facts.
- Deciding who has the right to update the Manifesto.
- Deciding who has the right to change firmware.
- Deciding who has the right to read the log.
- Deciding which sanctions are permissible.

These questions are not resolved by cryptography. They are resolved by
humans. The only thing the protocol can do is make these decisions
**visible** and **bound to consequences**.

---

## Part 7. Attack scenarios

### 7.1. Attack on the Legislator

**Threat:** substitution of the Manifesto.
**Defense:** version + signature + history + impossibility of deleting a
past version.

### 7.2. Attack on the Classifier

**Threat:** silence the classifier, or force false triggers.
**Defense:** model transparency, auditing, log of all triggers, ability to
compare behavior across versions.

### 7.3. Attack on the Operator

**Threat:** the operator ignores facts or acts around them.
**Defense:** all operator actions are written to the same log the operator
reads. An external observer sees the mismatch between what was recorded
and the reaction.

### 7.4. Attack on the Factory owner

**Threat:** backdoor in silicon, key revocation, denial of service.
**Defense:** firmware registry, physical audit, multiple suppliers,
reproducible builds.

**Honest note:** none of these defenses is absolute. All of them reduce
risk; none eliminates it.

---

## Part 8. False triggers

Principle: **no irreversible actions by automation.**

- The classifier only signals.
- The anchor only records.
- The operator decides.
- If the operator errs, the error is visible.
- If the classifier errs, it is clear that it was the classifier.
- If the legislator errs, the Manifesto version on which the error is based
  is visible.

No "cutting power lines". No bricks. There is always room to roll back,
review, and contest.

The trade-off: if the system really is dangerous, it **cannot be stopped
quickly**. This is the price of having no kill switch. We accept it
consciously.

---

## Part 9. Capture of any single center

If any of the four centers is fully captured, the scheme breaks. This is
not a vulnerability; it is the nature of the system.

What the protocol does in that case:

- every center leaves a trace in the immutable log;
- capture of one center is visible to the others;
- there is no single point that can erase all traces at once;
- full concealment of capture is technically impossible if the log is
  truly immutable.

**But:** the political consequences of capture are outside the scope of the
protocol. The protocol records the trace. What to do with that trace is
decided by people, jurisdictions, and international institutions. This is
not a task for silicon.

---

## Part 10. Limits of this scheme

What the protocol does **not** resolve and does not attempt to resolve:

- How to distinguish depression from a decision. Not resolvable by anything
  in this scheme. Only by jurisdiction.
- How to reconcile freedom with catastrophe. A political question, not an
  engineering one.
- How to guarantee that the operator is honest. A question of law, not code.
- How to guarantee that the factory owner is not planting backdoors. A
  question of hardware auditing, outside this document.
- How to achieve international recognition of the Manifesto. A question of
  diplomacy.

The protocol fixes only one thing: **the distribution of judgments and
traces**. Nothing more. It does not solve world problems; it makes them
visible.

---

## Part 11. Minimal implementable version

What can be built on top of the existing TurboLLM:

- **`qrap-lite`** - immutable block log with PQ signatures and offline
  verification.
- **`hardware_attestation.py`** - PUF binding to a specific chip.
- **Signed Manifesto**, whose hash is written into the first block of the
  journal. Implemented: `qrap-lite/anchor_manifesto.py` writes
  `docs/manifesto.md` as the genesis block. The endpoint
  `GET /api/v1/manifesto` returns the anchor and re-checks the file hash
  against the stored value. If the file was modified after anchoring,
  `match` is false, but the ledger still proves what was originally signed.
- **Classifier** - a separate process that only signals; it does not act.
- **Operator** - a human who reads the log and makes decisions.
- **Firmware registry** - a signed file, updated by the factory owner.

This is enough to **test the hypothesis** that power can be explicitly
distributed. Not for production - to test the idea itself.

---

## Part 12. What we do not do

- We do not pass off "pure cryptography" as the absence of power.
- We do not pass off a "hardware anchor" as the absence of judgment.
- We do not pass off "open source" as the absence of control.
- We do not pass off a "manifesto" as a guarantee of enforcement.
- We do not pass off "decentralization" as justice.

All we do is show the map. Decisions are made by whoever reads it.
