# g_inspector/real_inspector.py
import os
import pickle
import numpy as np
import torch
from typing import Dict, Any, Optional, List
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

class RealInspector:
    def __init__(self,
                 model_path: Optional[str] = None,
                 scaler_path: Optional[str] = None,
                 auto_train: bool = False):
        self.model = None
        self.scaler = None
        self.anomaly_threshold = 0.6
        self._is_fitted = False

        # Попытка загрузить существующие модели
        if model_path and os.path.exists(model_path) and scaler_path and os.path.exists(scaler_path):
            with open(model_path, 'rb') as f:
                self.model = pickle.load(f)
            with open(scaler_path, 'rb') as f:
                self.scaler = pickle.load(f)
            self._is_fitted = True
            print(f"[Inspector] Загружена модель из {model_path}")
        elif auto_train:
            print("[Inspector] Модель не найдена, обучение на синтетических данных...")
            self._train_on_synthetic()
            # Сохраняем обученную модель в текущую директорию
            if model_path and scaler_path:
                with open(model_path, 'wb') as f:
                    pickle.dump(self.model, f)
                with open(scaler_path, 'wb') as f:
                    pickle.dump(self.scaler, f)
                print(f"[Inspector] Модель сохранена в {model_path}")
        else:
            print("[Inspector] Модель не загружена, работа в эвристическом режиме.")

    def _train_on_synthetic(self, n_samples=5000, anomaly_ratio=0.25):
        """Генерирует синтетические данные и обучает логистическую регрессию."""
        # Используем ту же логику, что и в train_inspector.py
        FEATURE_DIM = 12
        NORMAL_MEAN = 0.2
        NORMAL_STD = 0.1
        ANOMALY_SHIFT = 0.8

        n_anomaly = int(n_samples * anomaly_ratio)
        n_normal = n_samples - n_anomaly

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
        """Преобразует активации в плоский вектор признаков (4 статистики на слой)."""
        features = []
        for layer, vals in activations.items():
            if isinstance(vals, torch.Tensor):
                vals = vals.numpy()
            elif isinstance(vals, list):
                vals = np.array(vals)
            if vals.ndim > 1:
                vals = vals.mean(axis=0)  # усреднение по последнему измерению
            # Добавляем статистики
            features.extend([vals.mean(), vals.std(), vals.max(), vals.min()])
        return np.array(features).reshape(1, -1)

    def analyze_activations(self, prompt: str, preliminary_response: str, activations: Optional[Dict] = None) -> Dict[str, Any]:
        """Анализ с использованием ML-классификатора, либо эвристика."""
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
        """Запасная эвристика (по тексту или статистикам)."""
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
            print("[Inspector] Модель не обучена, сохранение невозможно.")
