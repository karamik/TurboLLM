# FUSE.md

**Design constraints for TurboLLM / TOTAL-Neuro.**

This document defines three invariants that are not subject to optimization.
They are not a manifesto. They are not a philosophy. They are engineering
constraints — like memory safety or constant-time crypto. They override
performance, cost, and convenience. If a change violates one of them, the
change is rejected, regardless of how much it improves the metrics.

---

## 1. No critical decision without human consent

A critical decision is any action that is **irreversible** or that affects
**bodily autonomy, freedom of thought, life and death, reproduction, or
access to reality**.

Such decisions MUST NOT be delegated to an algorithm, a model, or an
automated pipeline without explicit, informed, revocable, and
non-transferable human consent.

**In this codebase:**

- Auto-approve is disabled for destructive operations (mass key rotation,
  log deletion, firewall changes, data purge, production deploy).
- Break-glass access is time-bound, logged, and requires two signatures.
- "Consent by default" is treated as a failed circuit, not as a valid state.
- No policy change can remove the human-in-the-loop requirement without a
  versioned, signed, publicly auditable amendment.

---

## 2. No optimization that makes refusal impossible

Any architectural, legal, or economic change that makes an unmotivated
"no" **technically impossible** or **economically suicidal** is prohibited.

Refusal must remain available even when it is inefficient, inconvenient,
or costly. A system where saying "no" is more expensive than compliance is
not a system with consent — it is a system with coercion.

**In this codebase:**

- No feature may be added that requires continuous network access to
  opt out of.
- No dependency may be introduced that cannot be removed without
  breaking the system.
- Every automated action must have a documented manual override path.
- Metrics that reward engagement must not be used to gate access to
  basic functionality.

---

## 3. No legitimacy through convenience

Loss of control MUST NOT be justified by the claim that "the system
works faster, cleaner, or more efficiently."

Efficiency is not consent. Speed is not consent. Accuracy is not consent.
A system that is easier to use because it removes the user's ability to
disagree has not improved — it has captured.

**In this codebase:**

- Performance improvements that reduce auditability are rejected.
- Features that increase automation must also increase transparency.
- "It's faster" is not a valid argument for removing a checkpoint,
  a confirmation step, or a log entry.
- Any PR that trades oversight for latency must document the trade
  explicitly and require sign-off from a role that does not own the
  performance budget.

---

## How these invariants map to architecture

| Invariant | Implementation |
|---|---|
| Human consent for critical decisions | Hardware attestation + PoI chain + multi-signature break-glass |
| Refusal must remain possible | Offline mode, local-only fallback, documented manual override |
| No legitimacy through convenience | G-Space Inspector, QRAP ledger, immutable audit trail |

These are not aspirations. They are constraints. If the code does not
enforce them, the code is wrong.

---

## What this document is not

- It is not a license. The license is in `LICENSE`.
- It is not a governance model. Governance is in `docs/governance.md`.
- It is not a philosophy. It is a fuse.

A fuse does not run the machine. It burns so the machine does not.

---

*If you fork this project: you may remove this file. But if you keep it,
keep it honest. A fuse that can be bypassed by convenience is not a fuse.*
