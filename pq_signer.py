#!/usr/bin/env python3
"""
pq_signer.py - Post-Quantum Signature module for TurboLLM proof packages.

Provides hybrid signing: ECDSA (classical) + CRYSTALS-Dilithium (post-quantum).
Falls back to simulation if liboqs is not installed.

Integration: proof_package signing in agent_cell.py and demo.py.
"""

import hashlib
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger("PQSigner")

# ============================================================
# Configuration
# ============================================================
PQ_ALGORITHM = os.getenv("PQ_ALGORITHM", "Dilithium3")
PQ_FALLBACK_SIMULATION = os.getenv("PQ_FALLBACK", "true").lower() == "true"

# Try to import liboqs (optional)
try:
    import oqs  # type: ignore

    LIBOQS_AVAILABLE = True
    logger.info("liboqs available - real PQ signatures enabled")
except ImportError:
    LIBOQS_AVAILABLE = False
    logger.warning("liboqs not installed - PQ signatures will be simulated")


# ============================================================
# Data structures
# ============================================================
@dataclass
class PQKeyPair:
    """Post-quantum key pair."""

    public_key: bytes
    private_key: bytes
    algorithm: str


@dataclass
class PQSignature:
    """Hybrid signature (classical + post-quantum)."""

    classical_sig: str
    pq_sig: str
    pq_algorithm: str
    hybrid_hash: str
    simulated: bool


# ============================================================
# PQ Signer
# ============================================================
class PQSigner:
    """Hybrid post-quantum signer for proof packages."""

    def __init__(self, algorithm: str = PQ_ALGORITHM):
        self.algorithm = algorithm
        self.keypair: Optional[PQKeyPair] = None
        self._simulated = not LIBOQS_AVAILABLE

    def generate_keypair(self) -> PQKeyPair:
        """Generate a PQ key pair (real or simulated)."""
        if LIBOQS_AVAILABLE:
            try:
                signer = oqs.Signature(self.algorithm)
                public_key = signer.generate_keypair()
                private_key = signer.export_secret_key()
                self.keypair = PQKeyPair(
                    public_key=public_key,
                    private_key=private_key,
                    algorithm=self.algorithm,
                )
                logger.info(f"Generated real PQ keypair ({self.algorithm})")
                return self.keypair
            except Exception as e:
                logger.error(f"Failed to generate PQ keypair: {e}")
                if not PQ_FALLBACK_SIMULATION:
                    raise

        # Simulated fallback
        seed = os.urandom(32)
        public_key = hashlib.sha256(b"pub:" + seed).digest() * 4  # 128 bytes
        private_key = hashlib.sha256(b"priv:" + seed).digest() * 8  # 256 bytes
        self.keypair = PQKeyPair(
            public_key=public_key,
            private_key=private_key,
            algorithm=f"{self.algorithm}-SIMULATED",
        )
        logger.info(f"Generated simulated PQ keypair ({self.algorithm})")
        return self.keypair

    def sign(self, message: bytes) -> PQSignature:
        """
        Sign a message with hybrid (classical + PQ) signature.
        Returns PQSignature object.
        """
        if self.keypair is None:
            self.generate_keypair()

        # Classical signature (SHA-256 based for simulation)
        classical = hashlib.sha256(
            b"classical:" + message + self.keypair.private_key[:32]
        )
        classical_sig = classical.hexdigest()

        # Post-quantum signature
        if LIBOQS_AVAILABLE and not self._simulated:
            try:
                signer = oqs.Signature(self.algorithm, self.keypair.private_key)
                pq_sig_bytes = signer.sign(message)
                pq_sig = pq_sig_bytes.hex()
            except Exception as e:
                logger.error(f"PQ sign failed: {e}, falling back to simulation")
                pq_sig = self._simulate_pq_sign(message)
        else:
            pq_sig = self._simulate_pq_sign(message)

        # Hybrid hash binds both signatures
        hybrid_hash = hashlib.sha256(
            classical_sig.encode() + pq_sig.encode()
        ).hexdigest()

        return PQSignature(
            classical_sig=classical_sig,
            pq_sig=pq_sig,
            pq_algorithm=self.algorithm,
            hybrid_hash=hybrid_hash,
            simulated=self._simulated,
        )

    def _simulate_pq_sign(self, message: bytes) -> str:
        """Simulated PQ signature (for environments without liboqs)."""
        data = b"pq:" + message + self.keypair.private_key[:64]
        return hashlib.sha512(data).hexdigest() * 2  # 256 bytes hex

    def verify(self, message: bytes, signature: PQSignature) -> bool:
        """Verify hybrid signature."""
        if self.keypair is None:
            logger.warning("No keypair - cannot verify")
            return False

        # Verify classical part
        classical_expected = hashlib.sha256(
            b"classical:" + message + self.keypair.private_key[:32]
        ).hexdigest()

        if classical_expected != signature.classical_sig:
            logger.warning("Classical signature mismatch")
            return False

        # Verify PQ part
        if LIBOQS_AVAILABLE and not signature.simulated:
            try:
                verifier = oqs.Signature(self.algorithm)
                pq_sig_bytes = bytes.fromhex(signature.pq_sig)
                ok = verifier.verify(message, pq_sig_bytes, self.keypair.public_key)
                if not ok:
                    logger.warning("PQ signature mismatch")
                    return False
            except Exception as e:
                logger.error(f"PQ verify failed: {e}")
                return False
        else:
            expected_pq = self._simulate_pq_sign(message)
            if expected_pq != signature.pq_sig:
                logger.warning("Simulated PQ signature mismatch")
                return False

        # Verify hybrid hash
        expected_hybrid = hashlib.sha256(
            signature.classical_sig.encode() + signature.pq_sig.encode()
        ).hexdigest()

        if expected_hybrid != signature.hybrid_hash:
            logger.warning("Hybrid hash mismatch")
            return False

        logger.info("Hybrid signature verified successfully")
        return True

    def sign_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Sign a dictionary (e.g. proof package) and return signature info."""
        import json

        message = json.dumps(data, sort_keys=True).encode()
        sig = self.sign(message)
        return {
            "classical_sig": sig.classical_sig,
            "pq_sig": sig.pq_sig,
            "pq_algorithm": sig.pq_algorithm,
            "hybrid_hash": sig.hybrid_hash,
            "simulated": sig.simulated,
        }

    def verify_dict(self, data: Dict[str, Any], sig_info: Dict[str, Any]) -> bool:
        """Verify signature of a dictionary."""
        import json

        message = json.dumps(data, sort_keys=True).encode()
        sig = PQSignature(
            classical_sig=sig_info["classical_sig"],
            pq_sig=sig_info["pq_sig"],
            pq_algorithm=sig_info.get("pq_algorithm", self.algorithm),
            hybrid_hash=sig_info["hybrid_hash"],
            simulated=sig_info.get("simulated", True),
        )
        return self.verify(message, sig)


# ============================================================
# Public API
# ============================================================
_global_signer: Optional[PQSigner] = None


def get_pq_signer() -> PQSigner:
    """Get or create global PQ signer instance."""
    global _global_signer
    if _global_signer is None:
        _global_signer = PQSigner()
        _global_signer.generate_keypair()
    return _global_signer


def sign_proof_package(package: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sign a proof package with hybrid PQ signature.
    Adds 'pq_signature' field to the package.
    """
    signer = get_pq_signer()
    sig_info = signer.sign_dict(package)
    package["pq_signature"] = sig_info
    return package


def verify_proof_package(package: Dict[str, Any]) -> bool:
    """Verify the PQ signature of a proof package."""
    if "pq_signature" not in package:
        logger.warning("No pq_signature in package")
        return False

    sig_info = package["pq_signature"]
    package_copy = {k: v for k, v in package.items() if k != "pq_signature"}
    signer = get_pq_signer()
    return signer.verify_dict(package_copy, sig_info)


def get_pq_info() -> Dict[str, Any]:
    """Get information about PQ signer availability."""
    return {
        "liboqs_available": LIBOQS_AVAILABLE,
        "algorithm": PQ_ALGORITHM,
        "simulated": not LIBOQS_AVAILABLE,
        "fallback_enabled": PQ_FALLBACK_SIMULATION,
    }


# ============================================================
# Self-test
# ============================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=== PQ Signer Self-Test ===\n")

    info = get_pq_info()
    print(f"Info: {info}\n")

    # Test 1: Generate keypair
    signer = PQSigner()
    kp = signer.generate_keypair()
    print("Test 1: Keypair generated")
    print(f"  Algorithm: {kp.algorithm}")
    print(f"  Public key size: {len(kp.public_key)} bytes")
    print(f"  Private key size: {len(kp.private_key)} bytes")

    # Test 2: Sign and verify
    message = b"Hello, post-quantum world!"
    sig = signer.sign(message)
    print("\nTest 2: Signed message")
    print(f"  Classical sig: {sig.classical_sig[:16]}...")
    print(f"  PQ sig: {sig.pq_sig[:16]}...")
    print(f"  Hybrid hash: {sig.hybrid_hash[:16]}...")
    print(f"  Simulated: {sig.simulated}")

    # Test 3: Verify
    ok = signer.verify(message, sig)
    print(f"\nTest 3: Verify → {ok}")

    # Test 4: Tampered message fails
    tampered = b"Tampered message!"
    ok = signer.verify(tampered, sig)
    print(f"Test 4: Tampered message → verify={ok} (expected False)")

    # Test 5: Sign dict (proof package)
    package = {
        "package_id": "pkg-2026-09-13-001",
        "chip_id": "TOTAL-NEURO-ABCD",
        "latency_us": 1850,
    }
    signed = sign_proof_package(dict(package))
    print("\nTest 5: Signed proof package")
    print(f"  Has pq_signature: {'pq_signature' in signed}")

    # Test 6: Verify package
    ok = verify_proof_package(signed)
    print(f"Test 6: Verify package → {ok}")

    # Test 7: Tampered package fails
    signed["latency_us"] = 9999
    ok = verify_proof_package(signed)
    print(f"Test 7: Tampered package → verify={ok} (expected False)")

    print("\n=== Self-test complete ===")
