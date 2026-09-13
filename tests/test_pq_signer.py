#!/usr/bin/env python3
"""Unit tests for pq_signer.py"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pq_signer import (  # noqa: E402
    PQSignature,
    PQSigner,
    get_pq_info,
    get_pq_signer,
    sign_proof_package,
    verify_proof_package,
)


class TestPQSigner(unittest.TestCase):

    def setUp(self):
        self.signer = PQSigner()
        self.signer.generate_keypair()

    def test_generate_keypair(self):
        kp = self.signer.keypair
        self.assertIsNotNone(kp)
        self.assertGreater(len(kp.public_key), 0)
        self.assertGreater(len(kp.private_key), 0)
        self.assertIn("Dilithium", kp.algorithm)

    def test_sign_message(self):
        message = b"Test message"
        sig = self.signer.sign(message)
        self.assertIsInstance(sig, PQSignature)
        self.assertGreater(len(sig.classical_sig), 0)
        self.assertGreater(len(sig.pq_sig), 0)
        self.assertGreater(len(sig.hybrid_hash), 0)

    def test_verify_valid_signature(self):
        message = b"Valid message"
        sig = self.signer.sign(message)
        self.assertTrue(self.signer.verify(message, sig))

    def test_verify_tampered_message(self):
        message = b"Original"
        sig = self.signer.sign(message)
        self.assertFalse(self.signer.verify(b"Tampered", sig))

    def test_verify_tampered_signature(self):
        message = b"Test"
        sig = self.signer.sign(message)
        sig.classical_sig = "0" * len(sig.classical_sig)
        self.assertFalse(self.signer.verify(message, sig))

    def test_hybrid_hash_binding(self):
        message = b"Test binding"
        sig = self.signer.sign(message)
        # Tampering with pq_sig should invalidate hybrid_hash
        sig.pq_sig = "f" * len(sig.pq_sig)
        self.assertFalse(self.signer.verify(message, sig))


class TestDictSigning(unittest.TestCase):

    def setUp(self):
        self.signer = PQSigner()
        self.signer.generate_keypair()

    def test_sign_dict(self):
        data = {"key": "value", "number": 42}
        sig_info = self.signer.sign_dict(data)
        self.assertIn("classical_sig", sig_info)
        self.assertIn("pq_sig", sig_info)
        self.assertIn("hybrid_hash", sig_info)

    def test_verify_dict(self):
        data = {"key": "value", "number": 42}
        sig_info = self.signer.sign_dict(data)
        self.assertTrue(self.signer.verify_dict(data, sig_info))

    def test_verify_dict_tampered(self):
        data = {"key": "value"}
        sig_info = self.signer.sign_dict(data)
        data["key"] = "tampered"
        self.assertFalse(self.signer.verify_dict(data, sig_info))


class TestGlobalAPI(unittest.TestCase):

    def test_get_pq_signer_singleton(self):
        s1 = get_pq_signer()
        s2 = get_pq_signer()
        self.assertIs(s1, s2)

    def test_sign_proof_package(self):
        package = {"package_id": "test-123", "latency": 100}
        signed = sign_proof_package(dict(package))
        self.assertIn("pq_signature", signed)
        self.assertTrue(verify_proof_package(signed))

    def test_verify_tampered_package(self):
        package = {"package_id": "test-456", "latency": 200}
        signed = sign_proof_package(dict(package))
        signed["latency"] = 999
        self.assertFalse(verify_proof_package(signed))

    def test_verify_unsigned_package(self):
        package = {"package_id": "test-789"}
        self.assertFalse(verify_proof_package(package))

    def test_get_pq_info(self):
        info = get_pq_info()
        self.assertIn("liboqs_available", info)
        self.assertIn("algorithm", info)
        self.assertIn("simulated", info)


if __name__ == "__main__":
    unittest.main(verbosity=2)
