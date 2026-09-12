#!/usr/bin/env python3
"""hardware_attestation.py – аттестация чипа TOTAL-Neuro через драйвер."""

import os
import time
import fcntl
import struct
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

logger = logging.getLogger("HardwareAttestation")

NEURO_SEC_IOC_MAGIC = ord('S')

def _IOC(dir_, type_, nr, size):
    return (dir_ << 30) | (size << 16) | (type_ << 8) | nr

_IOC_READ = 2
_IOC_WRITE = 1

NEURO_GET_PUF_ID       = _IOC(_IOC_READ, NEURO_SEC_IOC_MAGIC, 1, 16)
NEURO_GET_ATTESTATION  = _IOC(_IOC_READ, NEURO_SEC_IOC_MAGIC, 2, 1)
NEURO_GET_SIGNATURE    = _IOC(_IOC_READ, NEURO_SEC_IOC_MAGIC, 3, 1)
NEURO_GET_SECURITY_ALL = _IOC(_IOC_READ, NEURO_SEC_IOC_MAGIC, 4, 24)
NEURO_TRIGGER_ATTEST   = _IOC(0, NEURO_SEC_IOC_MAGIC, 5, 0)
NEURO_VERIFY_FIRMWARE  = _IOC(_IOC_READ | _IOC_WRITE, NEURO_SEC_IOC_MAGIC, 6, 16)

DEVICE_PATH = os.getenv("NEURO_DEVICE", "/dev/total_neuro")


class HardwareAttestation:
    def __init__(self, device_path: str = DEVICE_PATH):
        self.device_path = device_path
        self.fd: Optional[int] = None
        self._last_attestation: Optional[Dict[str, Any]] = None
        self._last_attestation_time: float = 0
        self.cache_ttl_sec = int(os.getenv("ATTESTATION_CACHE_TTL", "5"))

    def _open(self) -> bool:
        if self.fd is not None:
            return True
        try:
            self.fd = os.open(self.device_path, os.O_RDWR)
            logger.info(f"Device opened: {self.device_path}")
            return True
        except Exception as e:
            logger.warning(f"Cannot open {self.device_path}: {e}")
            self.fd = None
            return False

    def _ioctl(self, cmd: int, arg: bytes) -> Optional[bytes]:
        if not self._open():
            return None
        try:
            buf = bytearray(arg)
            fcntl.ioctl(self.fd, cmd, buf, True)
            return bytes(buf)
        except OSError as e:
            logger.warning(f"ioctl 0x{cmd:08X} failed: {e}")
            return None

    def get_security_info(self) -> Optional[Dict[str, Any]]:
        result = self._ioctl(NEURO_GET_SECURITY_ALL, bytes(24))
        if result is None:
            return None
        id_lo, id_mid1, id_mid2, id_hi = struct.unpack("<IIII", result[0:16])
        shield_ok, unlocked, sig_ok, attest_ok, zeroize = struct.unpack("<BBBBB", result[16:21])
        puf_hex = f"0x{id_hi:08X}{id_mid2:08X}{id_mid1:08X}{id_lo:08X}"
        return {
            "puf_id": puf_hex,
            "shield_ok": bool(shield_ok),
            "chip_unlocked": bool(unlocked),
            "signature_ok": bool(sig_ok),
            "attestation_ok": bool(attest_ok),
            "zeroize_active": bool(zeroize),
        }

    def get_full_attestation(self) -> Dict[str, Any]:
        timestamp = datetime.now(timezone.utc).isoformat()
        sec_info = self.get_security_info()
        if sec_info is None:
            return {
                "attestation_available": False,
                "attestation_ok": False,
                "signature_ok": False,
                "shield_ok": False,
                "chip_unlocked": False,
                "zeroize_active": False,
                "puf_id": None,
                "timestamp": timestamp,
                "error": "hardware_unavailable",
            }
        attestation_ok = (
            sec_info["attestation_ok"] and sec_info["shield_ok"]
            and sec_info["chip_unlocked"] and not sec_info["zeroize_active"]
        )
        return {
            "attestation_available": True,
            "attestation_ok": attestation_ok,
            "signature_ok": sec_info["signature_ok"],
            "shield_ok": sec_info["shield_ok"],
            "chip_unlocked": sec_info["chip_unlocked"],
            "zeroize_active": sec_info["zeroize_active"],
            "puf_id": sec_info["puf_id"],
            "timestamp": timestamp,
            "error": None,
        }

    def get_cached_attestation(self) -> Dict[str, Any]:
        now = time.time()
        if (self._last_attestation is not None
                and now - self._last_attestation_time < self.cache_ttl_sec):
            return self._last_attestation
        att = self.get_full_attestation()
        self._last_attestation = att
        self._last_attestation_time = now
        return att

    @staticmethod
    def hash_puf_for_proof(puf_id: str, salt: str = "") -> str:
        data = f"{puf_id}:{salt}".encode()
        return hashlib.sha256(data).hexdigest()


_global_attestation: Optional[HardwareAttestation] = None


def get_hardware_attestation() -> Dict[str, Any]:
    global _global_attestation
    if _global_attestation is None:
        _global_attestation = HardwareAttestation()
    return _global_attestation.get_cached_attestation()


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(HardwareAttestation().get_full_attestation(), indent=2))
