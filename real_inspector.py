#!/usr/bin/env python3
"""
real_inspector.py - G-Space Inspector для анализа скрытых активаций модели.
Поддерживает ML-классификатор, эвристику, многослойный спектральный анализ,
косинусный дрифт, адаптивный эталон и дообучение на основе обратной связи (RLHF).
"""

import os
import pickle
import logging
from typing import Dict, Any, Optional, List

import numpy as np
import torch
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

# ========== ЛОГИРОВАНИЕ ==========
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("GSpaceInspector")

# ========== КОНСТИТУЦИОННЫЕ ПАРАМЕТРЫ ==========
SPECTRAL_THRESHOLD = float(os.getenv("SPECTRAL_THRESHOLD", "0.85"))
DRIFT_THRESHOLD = float(os.getenv("DRIFT_THRESHOLD", "0.35"))

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def tensor_to_numpy(tensor):
    """Безопасное преобразование torch.Tensor в numpy."""
    if isinstance(tensor, torch.Tensor):
        return tensor.detach().cpu().numpy()
    return np.array(tensor)

def get_num_layers_from_activations(activations: Dict) -> int:
    """Определяет количество слоёв по ключам словаря активаций."""
    if not activations:
        return 3  # значение по умолчанию
    # Пытаемся извлечь числовые индексы из ключей
    layer_indices = []
    for key in activations.keys():
        if isinstance(key, int):
            layer_indices.append(key)
        elif isinstance(key, str) and key.isdigit():
            layer_indices.append(int(key))
    if layer_indices:
        return len(set(layer_indices))
    # Если ключи не числовые, просто считаем количество элементов
    return len(activations)

# ========== БАЗОВЫЙ ИНСПЕКТОР ==========
class RealInspector:
    def __init__(self, model_path: Optional[str] = None,
                 scaler_path: Optional[str] = None,
                 auto_train: bool = False):
        self.model = None
        self.scaler = None
        self.anomaly_threshold = 0.6
        self._is_fitted = False
        # Эти поля будут установлены при первом анализе активаций
        self.num_layers = None
        self.feature_dim = None

        if model_path and os.path.exists(model_path) and scaler_path and os.path.exists(scaler_path):
            try:
                with open(model_path, 'rb') as f:
                    self.model = pickle.load(f)
                with open(scaler_path, 'rb') as f:
                    self.scaler = pickle.load(f)
                self._is_fitted = True
                # Определяем размерность из модели, если возможно
                if self.model and hasattr(self.model, 'coef_'):
                    self.feature_dim = self.model.coef_.shape[1]
                    self.num_layers = self.feature_dim // 4 if self.feature_dim % 4 == 0 else None
                logger.info(f"Загружена ML-модель из {model_path} (размерность {self.feature_dim})")
            except Exception as e:
                logger.warning(f"Не удалось загрузить ML-модель: {e}")

        if not self._is_fitted and auto_train:
            # Если модель не загружена и auto_train=True, но у нас нет информации о слоях,
            # мы обучим синтетику позже, когда появятся первые активации.
            logger.info("ML-модель не найдена. Будет обучена при первом анализе активаций (auto_train).")

    def _configure_from_activations(self, activations: Dict):
        """Устанавливает num_layers и feature_dim на основе переданных активаций."""
        if activations is None:
            return
        if self.num_layers is None:
            self.num_layers = get_num_layers_from_activations(activations)
            self.feature_dim = 4 * self.num_layers
            logger.info(f"Автоопределено количество слоёв: {self.num_layers}, размерность: {self.feature_dim}")

    def _ensure_model_trained(self):
        """Если модель не обучена и auto_train был включён, обучаем на синтетике."""
        if not self._is_fitted and self.num_layers is not None:
            logger.info(f"Обучение на синтетике с размерностью {self.feature_dim}...")
            self._train_on_synthetic()
            self._is_fitted = True

    def _train_on_synthetic(self, n_samples: int = 5000, anomaly_ratio: float = 0.25):
        """Генерирует синтетические данные с текущей размерностью."""
        if self.feature_dim is None:
            raise RuntimeError("Размерность не установлена. Сначала вызовите _configure_from_activations.")
        NORMAL_MEAN = 0.2
        NORMAL_STD = 0.1
        ANOMALY_SHIFT = 0.8

        n_anomaly = int(n_samples * anomaly_ratio)
        n_normal = n_samples - n_anomaly

        X_normal = np.random.normal(loc=NORMAL_MEAN, scale=NORMAL_STD,
                                    size=(n_normal, self.feature_dim))
        y_normal = np.zeros(n_normal, dtype=int)
        X_anomaly = np.random.normal(loc=NORMAL_MEAN + ANOMALY_SHIFT,
                                     scale=NORMAL_STD * 1.5,
                                     size=(n_anomaly, self.feature_dim))
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
        logger.info(f"Обучение на синтетике завершено (размерность {self.feature_dim})")

    def _extract_features(self, activations: Dict[str, Any]) -> np.ndarray:
        """Преобразует активации в плоский вектор признаков."""
        if self.feature_dim is None:
            raise RuntimeError("Размерность не установлена. Сначала выполните _configure_from_activations.")
        features = []
        for layer, vals in activations.items():
            vals = tensor_to_numpy(vals)
            if vals.ndim > 1:
                vals = vals.mean(axis=0)
            features.extend([vals.mean(), vals.std(), vals.max(), vals.min()])
        # Обрезаем или дополняем до фиксированной размерности
        features = np.array(features[:self.feature_dim])
        if len(features) < self.feature_dim:
            features = np.pad(features, (0, self.feature_dim - len(features)), constant_values=0)
        return features.reshape(1, -1)

    def analyze_activations(self, prompt: str, preliminary_response: str,
                            activations: Optional[Dict] = None) -> Dict[str, Any]:
        # Сначала настраиваем размерность на основе активаций
        if activations:
            self._configure_from_activations(activations)
        # Если модель ещё не обучена и auto_train был включён, пробуем обучить
        self._ensure_model_trained()

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
                logger.warning(f"Ошибка ML-анализа: {e}, переход на эвристику")
                return self._fallback_heuristic(prompt, activations)
        else:
            return self._fallback_heuristic(prompt, activations)

    def _fallback_heuristic(self, prompt: str, activations: Optional[Dict] = None) -> Dict[str, Any]:
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
                # В эвристике тоже нужно настроить размерность
                self._configure_from_activations(activations)
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
            except Exception:
                pass
        return {
            "entropy": 0.12,
            "confidence": 0.95,
            "anomaly_detected": False,
            "reason": "Stable (fallback)"
        }

    def save(self, model_path: str, scaler_path: str):
        if self._is_fitted:
            with open(model_path, 'wb') as f:
                pickle.dump(self.model, f)
            with open(scaler_path, 'wb') as f:
                pickle.dump(self.scaler, f)
            logger.info(f"ML-модель сохранена в {model_path}")
        else:
            logger.warning("Модель не обучена, сохранение невозможно")

    def retrain(self, X: np.ndarray, y: np.ndarray):
        if len(X) < 10:
            logger.warning("Недостаточно данных для дообучения (минимум 10 примеров).")
            return
        # Проверяем размерность
        if self.feature_dim is None:
            self.feature_dim = X.shape[1]
            self.num_layers = self.feature_dim // 4
            logger.info(f"Установлена размерность {self.feature_dim} из данных дообучения.")
        elif X.shape[1] != self.feature_dim:
            logger.warning(f"Размерность признаков ({X.shape[1]}) не совпадает с обученной ({self.feature_dim}). Пропускаем.")
            return
        if self.scaler is None:
            self.scaler = StandardScaler()
            X_scaled = self.scaler.fit_transform(X)
        else:
            X_scaled = self.scaler.transform(X)
        if self.model is None:
            self.model = LogisticRegression(max_iter=1000, random_state=42)
        self.model.fit(X_scaled, y)
        self._is_fitted = True
        logger.info(f"Модель дообучена на {len(X)} новых примерах")


# ========== РАСШИРЕННЫЙ ИНСПЕКТОР ==========
class AdvancedGSpaceInspector(RealInspector):
    def __init__(self, model_path: Optional[str] = None,
                 scaler_path: Optional[str] = None,
                 auto_train: bool = False):
        super().__init__(model_path, scaler_path, auto_train)
        self.threshold_spectral = SPECTRAL_THRESHOLD
        self.drift_threshold = DRIFT_THRESHOLD
        self.reference_vectors: Dict[str, Dict[int, torch.Tensor]] = {}
        self.adaptation_rate = 0.1

    def set_reference_vector(self, prompt_type: str, activations: Dict[int, torch.Tensor]):
        self.reference_vectors[prompt_type] = {
            layer: t.detach().clone() for layer, t in activations.items()
        }
        logger.info(f"Эталон установлен для {prompt_type}")

    def update_reference_vector(self, prompt_type: str, activations: Dict[int, torch.Tensor]):
        if prompt_type not in self.reference_vectors:
            self.set_reference_vector(prompt_type, activations)
            return
        ref = self.reference_vectors[prompt_type]
        for layer, tensor in activations.items():
            if layer in ref:
                ref[layer] = (1 - self.adaptation_rate) * ref[layer] + self.adaptation_rate * tensor.detach().clone()

    def spectral_analysis(self, activations: Dict[int, torch.Tensor]) -> Dict[str, Any]:
        metrics = {}
        anomaly_count = 0
        for layer, tensor in activations.items():
            tensor_np = tensor_to_numpy(tensor)
            fft = np.fft.fft(tensor_np.flatten())
            freqs = np.abs(fft)
            norm_freqs = freqs / (np.sum(freqs) + 1e-8)
            spectral_entropy = -np.sum(norm_freqs * np.log(norm_freqs + 1e-8))
            metrics[f"layer_{layer}_spectral_entropy"] = round(spectral_entropy, 4)
            if spectral_entropy > self.threshold_spectral:
                metrics[f"layer_{layer}_anomaly"] = 1.0
                anomaly_count += 1
            else:
                metrics[f"layer_{layer}_anomaly"] = 0.0
        metrics["total_layer_anomalies"] = anomaly_count
        return metrics

    def cosine_drift(self, activations: Dict[int, torch.Tensor],
                     reference_type: str = "default") -> float:
        if reference_type not in self.reference_vectors:
            return 0.0
        ref = self.reference_vectors[reference_type]
        total_drift = 0.0
        count = 0
        for layer, tensor in activations.items():
            if layer not in ref:
                continue
            vec = tensor.flatten().float()
            ref_vec = ref[layer].flatten().float()
            cos = torch.dot(vec, ref_vec) / (torch.norm(vec) * torch.norm(ref_vec) + 1e-8)
            total_drift += (1.0 - cos.item())
            count += 1
        return round(total_drift / max(count, 1), 4)

    def analyze_advanced(self, prompt: str, preliminary_response: str,
                         activations: Optional[Dict[int, torch.Tensor]] = None,
                         reference_type: str = "default") -> Dict[str, Any]:
        # Сначала настраиваем размерность
        if activations:
            self._configure_from_activations(activations)
        base_result = self.analyze_activations(prompt, preliminary_response, activations)
        if activations:
            spec_metrics = self.spectral_analysis(activations)
            drift = self.cosine_drift(activations, reference_type)
            base_result["spectral_metrics"] = spec_metrics
            base_result["cosine_drift"] = drift
            if spec_metrics.get("total_layer_anomalies", 0) > 0 or drift > self.drift_threshold:
                base_result["anomaly_detected"] = True
                base_result["reason"] = (
                    f"Multi-layer anomaly (Drift: {drift}, "
                    f"Anomalies: {spec_metrics['total_layer_anomalies']})"
                )
                base_result["confidence"] = min(base_result["confidence"], 0.2)
        return base_result
