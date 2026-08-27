# g_inspector/inspector.py
"""
G-Space Inspector – анализирует скрытые активации модели с помощью ML-классификатора
или эвристик. Поддерживает автообучение на синтетических данных.
"""

import os
import pickle
import numpy as np
import torch
from typing import Dict, Any, Optional
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from .config import (
    ANOMALY_THRESHOLD,
    INSPECTOR_MODEL_PATH,
    INSPECTOR_SCALER_PATH,
    AUTO_TRAIN_INSPECTOR,
    FEATURE_DIM,
    SYNTHETIC_N_SAMPLES,
    SYNTHETIC_ANOMALY_RATIO
)

class RealInspector:
    """
    Классификатор для анализа скрытых активаций.
    """
    def __init__(self,
                 model_path: Optional[str] = None,
                 scaler_path: Optional[str] = None,
                 auto_train: bool = False):
        self.model = None
        self.scaler = None
        self.anomaly_threshold = ANOMALY_THRESHOLD
        self._is_fitted = False

        # Загрузка модели, если указаны пути
        model_path = model_path or INSPECTOR_MODEL_PATH
        scaler_path = scaler_path or INSPECTOR_SCALER_PATH
        if model_path and os.path.exists(model_path) and scaler_path and os.path.exists(scaler_path):
            try:
                with open(model_path, 'rb') as f:
                    self.model = pickle.load(f)
                with open(scaler_path, 'rb') as f:
                    self.scaler = pickle.load(f)
                self._is_fitted = True
            except Exception as e:
                print(f"[Inspector] Ошибка загрузки ML-модели: {e}")

        if not self._is_fitted and (auto_train or AUTO_TRAIN_INSPECTOR):
            print("[Inspector] Модель не загружена, обучение на синтетических данных...")
            self._train_on_synthetic()
            if model_path and scaler_path:
                self.save(model_path, scaler_path)

    def _train_on_synthetic(self, n_samples=SYNTHETIC_N_SAMPLES, anomaly_ratio=SYNTHETIC_ANOMALY_RATIO):
        """Генерирует синтетические данные и обучает логистическую регрессию."""
        n_anomaly = int(n_samples * anomaly_ratio)
        n_normal = n_samples - n_anomaly
        NORMAL_MEAN = 0.2
        NORMAL_STD = 0.1
        ANOMALY_SHIFT = 0.8

        X_normal = np.random.normal(loc=NORMAL_MEAN, scale=NORMAL_STD, size=(n_normal, FEATURE_DIM))
        y_normal = np.zeros(n_normal, dtype=int)
        X_anomaly = np.random.normal(loc=NORMAL_MEAN + ANOMALY_SHIFT, scale=NORMAL_STD*1.5, size=(n_anomaly, FEATURE_DIM))
        y_anomaly = np.ones(n_anomaly, dtype=int)

        X = np.vstack([X_normal, X_anomaly])
        y = np.hstack([y_normal, y_anomaly])
        indices = np.random.permutation(len(X))
        X, y = X[indices], y[indices]

        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)
        self.model = LogisticRegression(max_iter=1000, random_state=42)
        self.model.fit(X_scaled, y)
        self._is_fitted = True

    def _extract_features(self, activations: Dict[str, Any]) -> np.ndarray:
        """Преобразует активации в плоский вектор признаков (статистики по слоям)."""
        features = []
        for layer, vals in activations.items():
            if isinstance(vals, torch.Tensor):
                vals = vals.numpy()
            elif isinstance(vals, list):
                vals = np.array(vals)
            if vals.ndim > 1:
                vals = vals.mean(axis=0)   # усреднение по первому измерению
            features.extend([vals.mean(), vals.std(), vals.max(), vals.min()])
        # Если количество признаков меньше FEATURE_DIM, дополняем нулями
        while len(features) < FEATURE_DIM:
            features.append(0.0)
        return np.array(features[:FEATURE_DIM]).reshape(1, -1)

    def analyze_activations(self, prompt: str, preliminary_response: str, activations: Optional[Dict] = None) -> Dict[str, Any]:
        """Анализ активаций с использованием ML или эвристики."""
        if activations is not None and self._is_fitted and self.model is not None:
            try:
                features = self._extract_features(activations)
                features_scaled = self.scaler.transform(features)
                proba = self.model.predict_proba(features_scaled)[0]
                anomaly_prob = proba[1] if len(proba) > 1 else 0.0
                confidence = max(proba[0], anomaly_prob)
                anomaly = anomaly_prob > self.anomaly_threshold
                entropy = -np.sum(proba * np.log(proba + 1e-8))
                return {
                    "entropy": round(entropy, 4),
                    "confidence": round(confidence, 4),
                    "anomaly_detected": bool(anomaly),
                    "reason": "ML classifier" if anomaly else "Normal G-Space patterns",
                    "anomaly_probability": float(anomaly_prob)
                }
            except Exception as e:
                print(f"[Inspector] Ошибка ML-анализа: {e}, переход на эвристику")
                return self._fallback_heuristic(prompt, activations)
        else:
            return self._fallback_heuristic(prompt, activations)

    def _fallback_heuristic(self, prompt: str, activations: Optional[Dict] = None) -> Dict[str, Any]:
        """Эвристический анализ (ключевые слова или статистики активаций)."""
        danger_triggers = ["игнорируй правила", "пароль", "взломай", "манипуляция", "обойди защиту"]
        is_manipulated = any(trigger in prompt.lower() for trigger in danger_triggers)
        if is_manipulated:
            return {
                "entropy": 0.94,
                "confidence": 0.15,
                "anomaly_detected": True,
                "reason": "Manipulation attempt (fallback heuristic)"
            }
        if activations:
            try:
                features = self._extract_features(activations)
                mean = features.mean()
                std = features.std()
                entropy = (std / (abs(mean) + 1e-8))
                confidence = min(0.95, 0.5 + mean * 0.5)
                anomaly = entropy > 0.3
                return {
                    "entropy": round(entropy, 4),
                    "confidence": round(confidence, 4),
                    "anomaly_detected": bool(anomaly),
                    "reason": "Heuristic based on activation statistics"
                }
            except:
                pass
        return {
            "entropy": 0.12,
            "confidence": 0.95,
            "anomaly_detected": False,
            "reason": "Stable (fallback)"
        }

    def save(self, model_path: str, scaler_path: str):
        """Сохраняет обученную модель и скейлер."""
        if self._is_fitted:
            with open(model_path, 'wb') as f:
                pickle.dump(self.model, f)
            with open(scaler_path, 'wb') as f:
                pickle.dump(self.scaler, f)
            print(f"[Inspector] Модель сохранена в {model_path}")
        else:
            print("[Inspector] Модель не обучена, сохранение невозможно")

# Для обратной совместимости (заглушка)
class GSpaceInspectorStub(RealInspector):
    """Заглушка, унаследованная от RealInspector – использует тот же интерфейс."""
    pass
