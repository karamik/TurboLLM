# Firmware Registry

## Format, signatures, and offline verification of hardware identities

### 0. Purpose

The Firmware Registry is the visible trace of the Factory owner - one of
the four centers of power described in the Security Protocol. Its job is
to make the following facts checkable:

- which chip exists,
- what firmware is fused into it,
- who signed that firmware,
- when it was signed,
- by which root key.

It does not make chips trustworthy. It makes chips **accountable**.

---

## 1. What the Registry is not

The Registry is not:

- a certificate authority,
- a firmware distribution channel,
- a revocation authority,
- a security guarantee.

It is a signed, append-only record. Nothing more. Anyone who reads it must
still decide how much trust to place in the signers.

---

## 2. Identity of a chip

A chip's identity is derived from its **PUF** - a unique 128-bit fingerprint
produced by physical silicon variation. The PUF is read by the chip itself
via the Linux driver and is not writable, not copyable, and not derivable
from firmware.

The Registry never stores the raw PUF. It stores:

    puf_hash = SHA-256( PUF || salt )

where the salt is unique per registry entry. This prevents the Registry
itself from becoming a database of chip identities that could be correlated
across contexts.

---

## 3. Registry entry format

Each entry is a JSON object with these fields:

    {
      "chip_id":       "hex-64",
      "puf_hash":      "hex-64",
      "vendor":        "string",
      "model":         "string",
      "firmware_hash": "hex-64",
      "firmware_url":  "string | null",
      "fused_at":      "ISO-8601 timestamp",
      "signed_by":     "hex-64",
      "signature": {
        "classical_sig": "hex",
        "pq_sig":        "hex",
        "pq_algorithm":  "Dilithium3",
        "hybrid_hash":   "hex-32",
        "simulated":     false
      }
    }

Notes on fields:

- `chip_id` is a stable identifier assigned by the vendor. It is **not**
  the PUF. Two chips from the same vendor must have different `chip_id`.
- `puf_hash` binds the entry to a physical chip. It is created by the
  vendor at fuse time and cannot be recreated without physical access.
- `firmware_hash` is SHA-256 of the exact firmware image that was fused.
- `firmware_url` is optional; if present, it points to a reproducible build.
- `signed_by` is the public key of the vendor. It must be registered in the
  root key list (see Part 5).
- `signature` is a hybrid PQ signature over the canonical JSON of all other
  fields (see Part 4).

---

## 4. Canonical form and signature

To compute the signature, the entry is stripped of its `signature` field
and serialized as:

    json.dumps(entry_without_signature, sort_keys=True, separators=(",", ":"))

The resulting bytes are signed with the vendor's hybrid PQ key via
`pq_signer.py`. The signed message is the canonical JSON itself, not a
hash of it - so the verifier can recompute everything from the entry alone.

---

## 5. Root key list

The Registry recognizes a small set of root keys. Each root key corresponds
to a vendor. The list itself is a signed file:

    {
      "version": 1,
      "updated_at": "ISO-8601",
      "keys": [
        {"vendor": "string", "pubkey": "hex", "since": "ISO-8601", "revoked_at": null},
        ...
      ],
      "signed_by": "hex-64",
      "signature": { ... }
    }

The root key list is distributed alongside the Registry. It is not fetched
from the network at verification time. Changing it requires re-signing by
a quorum (threshold specified by the operators of the Registry; outside the
scope of this document).

---

## 6. Verification (offline)

A verifier needs three things:

1. The Registry entry for the chip in question.
2. The root key list.
3. The public key of the vendor (from the root key list).

The verification steps are:

1. Recompute `canonical_json(entry_without_signature)`.
2. Verify `signature` against `signed_by` using `pq_signer.verify`.
3. Check that `signed_by` appears in the root key list and is not revoked.
4. Confirm that `firmware_hash` matches the firmware hash reported by the
   chip during hardware attestation.
5. Confirm that `puf_hash` matches the PUF hash reported by the chip during
   hardware attestation.

If all five steps pass, the chip is **accounted for**. It is not
"trusted". It is simply consistent with what the Registry says about it.

A reference implementation lives in `qrap-lite/verify_proof.py` for the
proof packages; the same pattern applies here.

---

## 7. What this Registry guarantees

- The entry was signed by a key that appears in the root key list.
- The key was not revoked at the time of verification.
- The entry has not been altered since it was signed.
- The chip's PUF matches the entry.
- The chip's firmware matches the entry.

## 8. What this Registry does NOT guarantee

- That the vendor is honest.
- That the firmware contains no backdoors.
- That the root key list itself is trustworthy.
- That the PUF cannot be extracted with physical access.
- That the chip behaves as the firmware claims.
- That the firmware_hash corresponds to a publicly auditable build.

All of these are outside the scope of a registry. They require physical
audit, legal jurisdiction, reproducible builds, and multiple independent
suppliers. The Registry only makes the **claim** auditable.

---

## 9. Revocation

Revocation is a change of the root key list: setting `revoked_at` for a
given key. Revocation affects **future verifications**, not past ones.

Revocation is not retroactive because the Registry cannot rewrite history.
If a vendor is compromised today, entries signed yesterday remain valid
with respect to their signature - but a verifier that learns of the
revocation can choose to reject them going forward.

This asymmetry is intentional. It matches the append-only model of
`qrap-lite` and the Security Protocol.

---

## 10. Storage and distribution

The Registry is stored as:

- a single JSON Lines file (`registry.jsonl`), one entry per line,
- a root key list (`root_keys.json`),
- both signed.

Distribution is out of scope. Possible channels:

- Git repository (immutable history provides its own audit).
- Static file served over HTTPS.
- Physical media shipped with the chips.

`qrap-lite` can hold the Registry's hash-chained history if desired, by
appending one block per registry update. This is optional.

---

## 11. Attack scenarios

### 11.1. Forged entry

**Threat:** an attacker adds a fake chip to the Registry.
**Defense:** the entry must be signed by a key in the root key list. Adding
an entry requires the vendor's private key.

### 11.2. Substituted firmware

**Threat:** the chip reports a firmware hash that does not match the
Registry.
**Defense:** hardware attestation compares the reported hash against the
entry. A mismatch blocks the request.

### 11.3. Compromised vendor key

**Threat:** a vendor's signing key leaks.
**Defense:** root key revocation. Entries signed before revocation remain
verifiable but can be marked as untrusted at the operator's discretion.

### 11.4. Compromised root key list

**Threat:** the root key list itself is modified.
**Defense:** the list is signed. Verifiers must have a trusted copy of the
list from an out-of-band channel. This is the weakest link in the chain,
and we acknowledge it.

---

## 12. Minimal implementation

The Registry can be implemented as:

- a plain text file (`registry.jsonl`) in a Git repository,
- a small Python tool to append entries and verify them offline,
- reuse of `pq_signer.py` for signing and verification.

No database, no service, no network protocol is required for the Registry
itself. Distribution and root key management are policy decisions, not
engineering ones.

---

## 13. Closing note

The Registry is a record of **what was fused, by whom, and when**. It does
not make hardware safe. It makes hardware accountable.

Accountability is not a technical property. It is a property of a system in
which traces are visible and cannot be erased by the actor who produced
them. The Registry is one piece of that property, alongside `qrap-lite` and
hardware attestation.

Beyond that, everything is a decision made by humans - and left, unverified
by anyone else.
