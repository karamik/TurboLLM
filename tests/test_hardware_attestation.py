mkdir -p ~/TurboLLM/tests && cat > ~/TurboLLM/tests/test_hardware_attestation.py << 'XENDX'
#!/usr/bin/env python3
"""
Unit tests for hardware_attestation.py
Run: python -m pytest tests/test_hardware_attestation.py -v
"""

import os
import sys
import hashlib
import unittest
from unittest.mock import patch, MagicMock

# Добавляем путь к модулю
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hardware_attestation import (
    HardwareAttestation,
    get_hardware_attestation,
    NEURO_GET_SECURITY_ALL,
)


class TestHardwareAttestation(unittest.TestCase):

    def setUp(self):
        """Создаём экземпляр для каждого теста."""
        self.att = HardwareAttestation(device_path="/dev/nonexistent_test_device")

    # ------------------------------------------------------------
    # Тесты на обработку отсутствующего устройства
    # ------------------------------------------------------------
    def test_device_not_available_returns_error(self):
        """Если устройство не существует — аттестация недоступна."""
        result = self.att.get_full_attestation()
        self.assertFalse(result["attestation_available"])
        self.assertFalse(result["attestation_ok"])
        self.assertIsNone(result["puf_id"])
        self.assertEqual(result["error"], "hardware_unavailable")
        self.assertIn("timestamp", result)

    # ------------------------------------------------------------
    # Тесты на _open()
    # ------------------------------------------------------------
    def test_open_nonexistent_returns_false(self):
        """_open должен вернуть False для несуществующего файла."""
        result = self.att._open()
        self.assertFalse(result)
        self.assertIsNone(self.att.fd)

    # ------------------------------------------------------------
    # Тесты на _ioctl с mock-объектами
    # ------------------------------------------------------------
    @patch("os.open", return_value=99)
    @patch("fcntl.ioctl")
    def test_get_security_info_success(self, mock_ioctl, mock_open):
        """Успешное чтение security info."""
        # Готовим ответ: 16 байт PUF ID + 5 байт флагов
        puf_bytes = (0x11111111).to_bytes(4, "little") + \
                    (0x22222222).to_bytes(4, "little") + \
                    (0x33333333).to_bytes(4, "little") + \
                    (0x44444444).to_bytes(4, "little")
        flags = bytes([1, 1, 1, 1, 0])  # shield, unlocked, sig, attest, zeroize
        response = puf_bytes + flags + b"\x00\x00\x00"

        def fake_ioctl(fd, cmd, buf, mutate):
            buf[:len(response)] = response
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
        """Если устройство недоступно — get_security_info возвращает None."""
        result = self.att.get_security_info()
        self.assertIsNone(result)

    # ------------------------------------------------------------
    # Тесты на get_full_attestation с mock-данными
    # ------------------------------------------------------------
    @patch.object(HardwareAttestation, "get_security_info")
    def test_full_attestation_ok(self, mock_get_info):
        """Полная аттестация при всех OK-флагах."""
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
        """Если zeroize_active=True — аттестация не проходит."""
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
        """Если shield_ok=False — аттестация не проходит."""
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

    # ------------------------------------------------------------
    # Тесты на кэширование
    # ------------------------------------------------------------
    @patch.object(HardwareAttestation, "get_full_attestation")
    def test_cached_attestation(self, mock_full):
        """Кэш возвращает тот же объект в течение TTL."""
        mock_full.return_value = {
            "attestation_available": True,
            "attestation_ok": True,
            "puf_id": "0xTEST",
        }
        self.att.cache_ttl_sec = 100

        first = self.att.get_cached_attestation()
        second = self.att.get_cached_attestation()

        # get_full_attestation должен вызваться только один раз
        self.assertEqual(mock_full.call_count, 1)
        self.assertEqual(first["puf_id"], second["puf_id"])

    # ------------------------------------------------------------
    # Тесты на хеширование PUF
    # ------------------------------------------------------------
    def test_hash_puf_for_proof(self):
        """Проверка корректности SHA-256 хеша PUF."""
        puf_id = "0xABCDEF0123456789"
        salt = "inference-001"

        result = HardwareAttestation.hash_puf_for_proof(puf_id, salt)

        expected = hashlib.sha256(f"{puf_id}:{salt}".encode()).hexdigest()
        self.assertEqual(result, expected)
        self.assertEqual(len(result), 64)

    def test_hash_puf_no_salt(self):
        """Хеш без соли тоже работает."""
        puf_id = "0x123"
        result = HardwareAttestation.hash_puf_for_proof(puf_id)
        expected = hashlib.sha256(f"{puf_id}:".encode()).hexdigest()
        self.assertEqual(result, expected)

    def test_hash_puf_different_salts(self):
        """Разные соли дают разные хеши."""
        puf_id = "0xABC"
        h1 = HardwareAttestation.hash_puf_for_proof(puf_id, "salt1")
        h2 = HardwareAttestation.hash_puf_for_proof(puf_id, "salt2")
        self.assertNotEqual(h1, h2)

    # ------------------------------------------------------------
    # Тесты на глобальную функцию
    # ------------------------------------------------------------
    @patch("hardware_attestation.HardwareAttestation")
    def test_global_attestation_function(self, mock_class):
        """Глобальная функция get_hardware_attestation() возвращает данные."""
        mock_instance = MagicMock()
        mock_instance.get_cached_attestation.return_value = {
            "attestation_available": True,
            "attestation_ok": True,
            "puf_id": "0xGLOBALTEST",
        }
        mock_class.return_value = mock_instance

        # Импорт заново, чтобы сбросить глобальное состояние
        import importlib
        import hardware_attestation
        importlib.reload(hardware_attestation)
        hardware_attestation.HardwareAttestation = mock_class

        result = hardware_attestation.get_hardware_attestation()
        self.assertTrue(result["attestation_available"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
XENDX
