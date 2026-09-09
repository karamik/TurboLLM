#!/usr/bin/env python3
"""
gspace_anchor_protection.py – защита G-Space от отравления и дрейфа

Расширяет инспектор:
- Immutable Anchor Vector (золотой стандарт)
- Асимметричная коррекция (обновление только в безопасных пределах)
- Криптографическая изоляция весов (проверка подписи модели)
"""

import hashlib
import logging
import numpy as np
import torch
from typing import Dict, Optional, Any
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger("GSpaceAnchorProtection")

class AnchorProtectionMixin:
    """Миксин для добавления защиты на основе якоря к классу инспектора."""

    def __init__(self, anchor_drift_limit=0.1, anchor_update_limit=0.02, model_signature=""):
        self.anchor_drift_limit = anchor_drift_limit
        self.anchor_update_limit = anchor_update_limit
        self.model_signature = model_signature
        self.anchor_vector = None
        self.anchor_initialized = False

    def set_anchor(self, anchor_features: np.ndarray):
        """Устанавливает неизменяемый якорь (золотой стандарт)."""
        self.anchor_vector = anchor_features.flatten()
        self.anchor_initialized = True
        logger.info("Immutable anchor vector set.")

    def compute_drift_from_anchor(self, features: np.ndarray) -> float:
        """Вычисляет косинусное расстояние от текущих фич до якоря."""
        if not self.anchor_initialized:
            return 0.0
        anchor = self.anchor_vector.flatten()
        feat = features.flatten()
        dot = np.dot(feat, anchor)
        norm_f = np.linalg.norm(feat) + 1e-8
        norm_a = np.linalg.norm(anchor) + 1e-8
        cos_sim = dot / (norm_f * norm_a)
        drift = 1.0 - cos_sim
        return drift

    def can_update_anchor(self, new_features: np.ndarray) -> bool:
        """Проверяет, разрешено ли обновление якоря (асимметричная коррекция)."""
        if not self.anchor_initialized:
            return True
        drift = self.compute_drift_from_anchor(new_features)
        if drift > self.anchor_drift_limit:
            logger.warning(f"Drift {drift:.3f} > limit {self.anchor_drift_limit}. Update blocked.")
            return False
        return drift < self.anchor_update_limit

    def update_anchor(self, new_features: np.ndarray, force=False):
        """Обновляет якорь с проверкой допустимости."""
        if self.anchor_initialized and not force:
            if not self.can_update_anchor(new_features):
                return False
        if self.anchor_initialized:
            # Плавное обновление
            self.anchor_vector = 0.95 * self.anchor_vector + 0.05 * new_features.flatten()
        else:
            self.anchor_vector = new_features.flatten()
            self.anchor_initialized = True
        logger.info("Anchor updated successfully.")
        return True

    def verify_model_signature(self, model_path: str) -> bool:
        """Проверяет криптографическую подпись модели (изоляция весов)."""
        if not self.model_signature:
            logger.warning("Model signature not provided, skipping verification")
            return True
        try:
            with open(model_path, 'rb') as f:
                content = f.read()
                calc_hash = hashlib.sha256(content).hexdigest()
                # В реальном проекте используется асимметричная проверка
                return calc_hash == self.model_signature
        except Exception as e:
            logger.error(f"Signature verification error: {e}")
            return False

# Пример использования (можно вставить в agent_cell.py):
# class AdvancedGSpaceInspector(RealInspector, AnchorProtectionMixin):
#     def __init__(self, ...):
#         RealInspector.__init__(self, ...)
#         AnchorProtectionMixin.__init__(self, anchor_drift_limit=0.1, ...)
#         # ...
#
#     def analyze_activations(self, ...):
#         # вызываем базовый анализ, затем проверяем дрейф и корректируем результат
#         base_result = super().analyze_activations(...)
#         if self.anchor_initialized and self._extract_features(...) is not None:
#             drift = self.compute_drift_from_anchor(features)
#             base_result["drift_from_anchor"] = drift
#             if drift > self.anchor_drift_limit:
#                 base_result["anomaly_detected"] = True
#                 base_result["confidence"] = max(0.0, base_result["confidence"] - 0.3)
#                 base_result["reason"] = "Anchor drift detected!"
#         return base_result
