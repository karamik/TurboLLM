"""
Advanced G-Space Inspector with:
- Immutable Anchor Vector (Golden Reference)
- Asymmetric correction (only towards anchor)
- Cryptographic isolation of weights (signature verification)
"""

import os
import hashlib
import json
import numpy as np
import torch
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend

from real_inspector import RealInspector  # базовый класс

class AdvancedGSpaceInspector(RealInspector):
    def __init__(self, model_path=None, scaler_path=None, auto_train=False,
                 anchor_file="golden_anchor.json", 
                 private_key_pem=None, public_key_pem=None):
        super().__init__(model_path, scaler_path, auto_train)
        
        # 1. Загрузка или создание неизменяемого якоря (Golden Reference)
        self.anchor_file = anchor_file
        self.anchor_vector = self._load_or_create_anchor()
        self.anchor_hash = hashlib.sha256(json.dumps(self.anchor_vector).encode()).hexdigest()
        
        # 2. Параметры асимметричной коррекции
        self.adaptation_rate = 0.05          # медленное обновление
        self.max_drift_to_anchor = 0.3       # порог дрейфа
        self.asymmetric_bias = 0.8           # 80% коррекции в сторону эталона
        
        # 3. Криптографическая подпись весов (если включено)
        self.private_key = None
        self.public_key = None
        if private_key_pem and public_key_pem:
            self.private_key = serialization.load_pem_private_key(
                private_key_pem.encode('utf-8'),
                password=None,
                backend=default_backend()
            )
            self.public_key = serialization.load_pem_public_key(
                public_key_pem.encode('utf-8'),
                backend=default_backend()
            )
        self.weight_signature = None
        self._sign_weights() if self.private_key else None
        
        # 4. Журнал дрейфа для аудита
        self.drift_history = []
        self.anomaly_triggers = 0
        
    def _load_or_create_anchor(self):
        """Загружает якорь из файла или создаёт новый (эталон при инициализации)."""
        if os.path.exists(self.anchor_file):
            with open(self.anchor_file, 'r') as f:
                return json.load(f)
        else:
            # Генерация случайного эталона (в реальности – на основе чистых данных)
            anchor = {
                "spectral_entropy": 0.5,
                "layer_means": [0.2, 0.15, 0.18],
                "layer_stds": [0.05, 0.04, 0.06],
                "cosine_ref": [0.99, 0.98, 0.97]
            }
            with open(self.anchor_file, 'w') as f:
                json.dump(anchor, f)
            return anchor
    
    def _sign_weights(self):
        """Подписывает веса инспектора (сохраняет подпись)."""
        if not self.private_key:
            return
        # Сериализуем модель (веса) в строку
        if self.model is not None:
            model_bytes = json.dumps(self.model.get_params()).encode()
            signature = self.private_key.sign(
                model_bytes,
                ec.ECDSA(hashes.SHA256())
            )
            self.weight_signature = signature.hex()
    
    def verify_weight_signature(self, model_params) -> bool:
        """Проверяет подпись весов при загрузке или OTA-обновлении."""
        if not self.public_key or not self.weight_signature:
            return True  # если подпись не используется
        model_bytes = json.dumps(model_params).encode()
        try:
            self.public_key.verify(
                bytes.fromhex(self.weight_signature),
                model_bytes,
                ec.ECDSA(hashes.SHA256())
            )
            return True
        except Exception:
            return False
    
    def asymmetric_correction(self, current_vector, anchor_vector):
        """
        Асимметричная коррекция: обновление только в сторону эталона.
        Возвращает скорректированный вектор.
        """
        diff = np.array(current_vector) - np.array(anchor_vector)
        # Разрешаем только уменьшение отклонения (движение к эталону)
        correction = np.where(diff > 0, -diff * self.asymmetric_bias, 0)
        # Также ограничиваем величину коррекции
        max_correction = 0.1 * np.array(anchor_vector)  # не более 10% от эталона
        correction = np.clip(correction, -max_correction, max_correction)
        return (np.array(current_vector) + correction).tolist()
    
    def update_reference_vector(self, prompt_type: str, activations: dict, 
                                force: bool = False):
        """
        Обновляет адаптивный эталон с асимметричной коррекцией и проверкой дрейфа.
        """
        if prompt_type not in self.reference_vectors:
            self.set_reference_vector(prompt_type, activations)
            return
        
        # Извлекаем текущий адаптивный эталон
        ref = self.reference_vectors[prompt_type]
        # Преобразуем в списки для удобства
        current_vec = []
        anchor_vec = []
        for layer in sorted(ref.keys()):
            if layer in self.anchor_vector:
                current_vec.extend(ref[layer].flatten().tolist())
                anchor_vec.extend(self.anchor_vector[layer])
        
        # Проверка дрейфа относительно якоря
        drift = np.linalg.norm(np.array(current_vec) - np.array(anchor_vec))
        self.drift_history.append(drift)
        if drift > self.max_drift_to_anchor:
            # Дрейф превышен – сброс к якорю (иммунная реакция)
            self.anomaly_triggers += 1
            for layer in ref.keys():
                if layer in self.anchor_vector:
                    ref[layer] = torch.tensor(self.anchor_vector[layer], dtype=torch.float32)
            return
        
        # Асимметричная коррекция (только в сторону эталона)
        corrected_vec = self.asymmetric_correction(current_vec, anchor_vec)
        # Обновляем адаптивный эталон
        idx = 0
        for layer in sorted(ref.keys()):
            if layer in self.anchor_vector:
                size = ref[layer].numel()
                new_vals = torch.tensor(corrected_vec[idx:idx+size], dtype=torch.float32)
                ref[layer] = new_vals.view(ref[layer].shape)
                idx += size
    
    def analyze_advanced(self, prompt, preliminary_response, activations,
                         reference_type="default", skip_update=False):
        """
        Проводит анализ с проверкой дрейфа и защитой от отравления.
        """
        # Выполняем базовый анализ
        base_result = super().analyze_advanced(prompt, preliminary_response, activations, reference_type)
        
        # Если активации не переданы, возвращаем базовый результат
        if not activations:
            return base_result
        
        # Проверяем подпись весов (если используется)
        if self.private_key and not self.verify_weight_signature(self.model.get_params()):
            base_result["anomaly_detected"] = True
            base_result["confidence"] = 0.0
            base_result["reason"] = "Weight signature verification failed"
            return base_result
        
        # Обновляем адаптивный эталон с защитой от дрейфа
        if not skip_update:
            self.update_reference_vector(reference_type, activations)
        
        # Добавляем метрики дрейфа и якоря
        base_result["drift_to_anchor"] = self.drift_history[-1] if self.drift_history else 0.0
        base_result["anchor_hash"] = self.anchor_hash
        base_result["anomaly_triggers"] = self.anomaly_triggers
        
        return base_result

    def reset_to_anchor(self):
        """Принудительный сброс всех адаптивных эталонов к якорю (режим повышенной безопасности)."""
        for prompt_type in self.reference_vectors.keys():
            for layer in self.reference_vectors[prompt_type].keys():
                if layer in self.anchor_vector:
                    self.reference_vectors[prompt_type][layer] = torch.tensor(self.anchor_vector[layer], dtype=torch.float32)
        self.anomaly_triggers = 0
        self.drift_history = []
        return {"status": "reset_to_anchor", "anchor_hash": self.anchor_hash}
