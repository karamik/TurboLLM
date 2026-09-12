#!/usr/bin/env python3
import hashlib
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hardware_attestation import (  # noqa: E402
    HardwareAttestation,
)


class TestHardwareAttestation(unittest.TestCase):

    def setUp(self):
        self.att = HardwareAttestation(device_path="/dev/nonexistent_test_device")

    def test_device_not_available_returns_error(self):
        result = self.att.get_full_attestation()
        self.assertFalse(result["attestation_available"])
        self.assertFalse(result["attestation_ok"])
        self.assertIsNone(result["puf_id"])
        self.assertEqual(result["error"], "hardware_unavailable")
        self.assertIn("timestamp", result)

    def test_open_nonexistent_returns_false(self):
        result = self.att._open()
        self.assertFalse(result)
        self.assertIsNone(self.att.fd)

    @patch("os.open", return_value=99)
    @patch("fcntl.ioctl")
    def test_get_security_info_success(self, mock_ioctl, mock_open):
        puf_bytes = (
            (0x11111111).to_bytes(4, "little")
            + (0x22222222).to_bytes(4, "little")
            + (0x33333333).to_bytes(4, "little")
            + (0x44444444).to_bytes(4, "little")
        )
        flags = bytes([1, 1, 1, 1, 0])
        response = puf_bytes + flags + b"\x00\x00\x00"

        def fake_ioctl(fd, cmd, buf, mutate):
            buf[: len(response)] = response
            return 0

        mock_ioctl.side_effect = fake_ioctl
        result = self.att.get_security_info()
        self.assertIsNotNone(result)
        self.assertEqual(result["puf_id"], "0x44444444333333332222222211111111")
        self.assertTrue(result["shield_ok"])
        self.assertTrue(result["chip_unlocked"])
        self.assertTrue(result["signature_ok"])
        self.assertTrue(result["attestation_ok"])
        self.assertFalse(result["zeroize_active"])

    @patch("os.open", side_effect=FileNotFoundError)
    def test_get_security_info_unavailable(self, mock_open):
        result = self.att.get_security_info()
        self.assertIsNone(result)

    @patch.object(HardwareAttestation, "get_security_info")
    def test_full_attestation_ok(self, mock_get_info):
        mock_get_info.return_value = {
            "puf_id": "0xABCDEF0123456789",
            "shield_ok": True,
            "chip_unlocked": True,
            "signature_ok": True,
            "attestation_ok": True,
            "zeroize_active": False,
        }
        result = self.att.get_full_attestation()
        self.assertTrue(result["attestation_available"])
        self.assertTrue(result["attestation_ok"])
        self.assertEqual(result["puf_id"], "0xABCDEF0123456789")
        self.assertIsNone(result["error"])

    @patch.object(HardwareAttestation, "get_security_info")
    def test_full_attestation_zeroize_blocks(self, mock_get_info):
        mock_get_info.return_value = {
            "puf_id": "0xABCDEF0123456789",
            "shield_ok": True,
            "chip_unlocked": True,
            "signature_ok": True,
            "attestation_ok": True,
            "zeroize_active": True,
        }
        result = self.att.get_full_attestation()
        self.assertTrue(result["attestation_available"])
        self.assertFalse(result["attestation_ok"])
        self.assertTrue(result["zeroize_active"])

    @patch.object(HardwareAttestation, "get_security_info")
    def test_full_attestation_shield_fault_blocks(self, mock_get_info):
        mock_get_info.return_value = {
            "puf_id": "0xABCDEF0123456789",
            "shield_ok": False,
            "chip_unlocked": True,
            "signature_ok": True,
            "attestation_ok": True,
            "zeroize_active": False,
        }
        result = self.att.get_full_attestation()
        self.assertFalse(result["attestation_ok"])

    @patch.object(HardwareAttestation, "get_full_attestation")
    def test_cached_attestation(self, mock_full):
        mock_full.return_value = {
            "attestation_available": True,
            "attestation_ok": True,
            "puf_id": "0xTEST",
        }
        self.att.cache_ttl_sec = 100

        first = self.att.get_cached_attestation()
        second = self.att.get_cached_attestation()

        self.assertEqual(mock_full.call_count, 1)
        self.assertEqual(first["puf_id"], second["puf_id"])

    def test_hash_puf_for_proof(self):
        puf_id = "0xABCDEF0123456789"
        salt = "inference-001"

        result = HardwareAttestation.hash_puf_for_proof(puf_id, salt)

        expected = hashlib.sha256(f"{puf_id}:{salt}".encode()).hexdigest()
        self.assertEqual(result, expected)
        self.assertEqual(len(result), 64)

    def test_hash_puf_no_salt(self):
        puf_id = "0x123"
        result = HardwareAttestation.hash_puf_for_proof(puf_id)
        expected = hashlib.sha256(f"{puf_id}:".encode()).hexdigest()
        self.assertEqual(result, expected)

    def test_hash_puf_different_salts(self):
        puf_id = "0xABC"
        h1 = HardwareAttestation.hash_puf_for_proof(puf_id, "salt1")
        h2 = HardwareAttestation.hash_puf_for_proof(puf_id, "salt2")
        self.assertNotEqual(h1, h2)

    @patch("hardware_attestation.HardwareAttestation")
    def test_global_attestation_function(self, mock_class):
        mock_instance = MagicMock()
        mock_instance.get_cached_attestation.return_value = {
            "attestation_available": True,
            "attestation_ok": True,
            "puf_id": "0xGLOBALTEST",
        }
        mock_class.return_value = mock_instance

        import importlib

        import hardware_attestation

        importlib.reload(hardware_attestation)
        hardware_attestation.HardwareAttestation = mock_class

        result = hardware_attestation.get_hardware_attestation()
        self.assertTrue(result["attestation_available"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
