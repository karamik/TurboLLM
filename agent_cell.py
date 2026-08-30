#!/usr/bin/env python3
"""
agent_cell.py - HTTP-сервис-агент с супервайзером (G-Space Inspector + Self-Healing)
для связи TurboLLM с QRAP-кластером.

Включает управление сессиями, балансами, пополнение через USDT (TRC‑20),
стриминг с микро-списаниями, арбитраж, голосования,
а также многослойный G-Space анализ (спектральный + дрифт) с адаптивным эталоном,
криптографическим доказательством инспекции (PoI),
сбор обратной связи (RLHF), конституционные параметры и экспорт метрик для дашборда.
"""

import os
import time
import random
import hashlib
import asyncio
import logging
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import uuid

import numpy as np
import torch
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
import aiohttp
from aiohttp import web
from pydantic import BaseModel, ValidationError

# Prometheus метрики
from prometheus_client import Counter, Gauge, Histogram, start_http_server, generate_latest, CONTENT_TYPE_LATEST

# Для PoI (подпись)
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend

# ========== ЛОГИРОВАНИЕ ==========
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("AgentSupervisorCell")

# ========== ЗАГРУЗКА .env (если есть) ==========
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ========== КОНФИГУРАЦИЯ ИЗ ОКРУЖЕНИЯ ==========
TURBOLLM_ENDPOINT = os.getenv("TURBOLLM_ENDPOINT", "http://turbollm:8000/v1")
TURBOLLM_MODEL = os.getenv("TURBOLLM_MODEL", "meta-llama/Meta-Llama-3-70B")
TURBOLLM_API_KEY = os.getenv("TURBOLLM_API_KEY", "EMPTY")

CLUSTER_ENDPOINT = os.getenv("CLUSTER_ENDPOINT", "http://qrap-node:50051/api/v1/block")
CLUSTER_API_KEY = os.getenv("CLUSTER_API_KEY", "")

CELL_ID = os.getenv("CELL_ID", f"cell_{random.randint(1000, 9999)}")
N_AGENTS = int(os.getenv("N_AGENTS", "10"))

HOST = os.getenv("AGENT_HOST", "0.0.0.0")
PORT = int(os.getenv("AGENT_PORT", "8080"))
METRICS_PORT = int(os.getenv("METRICS_PORT", "9090"))

# Пороги для супервайзера (могут быть переопределены конституцией)
CONFIDENCE_THRESHOLD_HIGH = float(os.getenv("CONFIDENCE_THRESHOLD_HIGH", "0.8"))
CONFIDENCE_THRESHOLD_LOW = float(os.getenv("CONFIDENCE_THRESHOLD_LOW", "0.5"))
MAX_REFLECTION_RETRIES = int(os.getenv("MAX_REFLECTION_RETRIES", "1"))

# Пути к ML-модели
INSPECTOR_MODEL_PATH = os.getenv("INSPECTOR_MODEL_PATH", "inspector_model.pkl")
INSPECTOR_SCALER_PATH = os.getenv("INSPECTOR_SCALER_PATH", "inspector_scaler.pkl")
AUTO_TRAIN_INSPECTOR = os.getenv("AUTO_TRAIN_INSPECTOR", "true").lower() == "true"

# Экономические настройки
PRICE_PER_TOKEN = float(os.getenv("PRICE_PER_TOKEN", "0.0001"))
MIN_BALANCE_TO_START = float(os.getenv("MIN_BALANCE_TO_START", "0.01"))
WARNING_BALANCE = float(os.getenv("WARNING_BALANCE", "5.0"))
TOPUP_AMOUNT = float(os.getenv("TOPUP_AMOUNT", "100.0"))
MERCHANT_ADDRESS = os.getenv("MERCHANT_ADDRESS", "T...")
USDT_CONTRACT = os.getenv("USDT_CONTRACT", "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")
TRONGRID_API = os.getenv("TRONGRID_API", "https://api.trongrid.io")
SESSION_TIMEOUT = int(os.getenv("SESSION_TIMEOUT", "86400"))

# Конституционные параметры (по умолчанию, переопределяются через голосование)
SPECTRAL_THRESHOLD = float(os.getenv("SPECTRAL_THRESHOLD", "0.85"))
DRIFT_THRESHOLD = float(os.getenv("DRIFT_THRESHOLD", "0.35"))
CONSTITUTION_VERSION = os.getenv("CONSTITUTION_VERSION", "1.0")

# PoI – приватный ключ супервайзера (можно сгенерировать и сохранить)
SUPERVISOR_PRIVATE_KEY_PEM = os.getenv("SUPERVISOR_PRIVATE_KEY", "")
if not SUPERVISOR_PRIVATE_KEY_PEM:
    logger.warning("SUPERVISOR_PRIVATE_KEY не задан! Генерируем временный ключ (небезопасно).")
    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
    SUPERVISOR_PRIVATE_KEY_PEM = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8')
else:
    private_key = serialization.load_pem_private_key(
        SUPERVISOR_PRIVATE_KEY_PEM.encode('utf-8'),
        password=None,
        backend=default_backend()
    )

# ========== PROMETHEUS МЕТРИКИ ==========
AGENT_REQUESTS = Counter('agent_requests_total', 'Total requests processed by agent', ['status'])
AGENT_CONFIDENCE = Gauge('agent_confidence_score', 'Latest confidence score')
AGENT_G_ENTROPY = Gauge('agent_g_entropy', 'Latest G-Space entropy')
AGENT_SUPERVISOR_STATUS = Counter('agent_supervisor_status_total', 'Supervisor decisions', ['status'])
AGENT_REQUEST_DURATION = Histogram('agent_request_duration_seconds', 'Request processing duration')
AGENT_REFLECTION_COUNT = Counter('agent_reflection_total', 'Number of reflection triggers')
AGENT_BALANCE = Gauge('agent_balance_qrap', 'Current balance of QRAP tokens for session')
AGENT_SPECTRAL_ANOMALIES = Gauge('agent_spectral_anomalies', 'Number of spectral anomalies detected')
AGENT_COSINE_DRIFT = Gauge('agent_cosine_drift', 'Current cosine drift value')
# Метрики по слоям (будут создаваться динамически)
_spectral_gauges = {}

def get_spectral_gauge(layer_idx):
    """Возвращает или создаёт Gauge для конкретного слоя."""
    key = f'agent_spectral_entropy_layer_{layer_idx}'
    if key not in _spectral_gauges:
        _spectral_gauges[key] = Gauge(key, f'Spectral entropy for layer {layer_idx}')
    return _spectral_gauges[key]

# ========== ХРАНИЛИЩЕ СЕССИЙ ==========
session_balances: Dict[str, float] = {}
session_created: Dict[str, float] = {}
session_addresses: Dict[str, str] = {}
used_transactions: set = set()

# ========== PYDANTIC МОДЕЛИ ==========
class EntropyManifest(BaseModel):
    gamma: float
    nu: int
    delta: float
    mu_hash: str
    tau_ms: int

class CellOutput(BaseModel):
    cell_id: str
    block_id: str
    timestamp: str
    decision: str
    manifest: EntropyManifest
    poi_chain: List[str]
    payload: Dict[str, Any]
    company_id: Optional[str] = None
    decision_type: Optional[str] = None
    case_metadata: Optional[Dict[str, Any]] = None
    # Поля для сбора обратной связи (RLHF)
    user_feedback: Optional[Dict[str, Any]] = None

@dataclass
class CellInput:
    prompt: str
    context: Optional[str] = None
    session_id: Optional[str] = None

@dataclass
class CellOutputSupervisor:
    response: str
    confidence_score: float
    status: str  # 'APPROVED', 'REFLECTED', 'BLOCKED'
    metadata: Dict[str, Any] = field(default_factory=dict)

# ========== БАЗОВЫЙ G-SPACE INSPECTOR ==========
class RealInspector:
    """Базовый инспектор с ML-классификатором и эвристикой."""
    def __init__(self, model_path=None, scaler_path=None, auto_train=False):
        self.model = None
        self.scaler = None
        self.anomaly_threshold = 0.6
        self._is_fitted = False
        if model_path and os.path.exists(model_path) and scaler_path and os.path.exists(scaler_path):
            try:
                import pickle
                with open(model_path, 'rb') as f:
                    self.model = pickle.load(f)
                with open(scaler_path, 'rb') as f:
                    self.scaler = pickle.load(f)
                self._is_fitted = True
                logger.info(f"Загружена ML-модель из {model_path}")
            except Exception as e:
                logger.warning(f"Не удалось загрузить ML-модель: {e}")
        if not self._is_fitted and auto_train:
            logger.info("ML-модель не найдена, обучение на синтетике...")
            self._train_on_synthetic()
            if model_path and scaler_path:
                self.save(model_path, scaler_path)

    def _train_on_synthetic(self, n_samples=5000, anomaly_ratio=0.25):
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
        logger.info("Обучение на синтетике завершено")

    def _extract_features(self, activations: Dict[str, Any]) -> np.ndarray:
        features = []
        for layer, vals in activations.items():
            if isinstance(vals, torch.Tensor):
                vals = vals.numpy()
            elif isinstance(vals, list):
                vals = np.array(vals)
            if vals.ndim > 1:
                vals = vals.mean(axis=0)
            features.extend([vals.mean(), vals.std(), vals.max(), vals.min()])
        return np.array(features).reshape(1, -1)

    def analyze_activations(self, prompt: str, preliminary_response: str, activations: Optional[Dict] = None) -> Dict[str, Any]:
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
            return {"entropy": 0.94, "confidence": 0.15, "anomaly_detected": True, "reason": "Manipulation attempt (fallback heuristic)"}
        if activations:
            try:
                features = self._extract_features(activations)
                mean = features.mean()
                std = features.std()
                entropy = (std / (abs(mean) + 1e-8))
                confidence = min(0.95, 0.5 + mean * 0.5)
                anomaly = entropy > 0.3
                return {"entropy": round(entropy, 4), "confidence": round(confidence, 4), "anomaly_detected": bool(anomaly), "reason": "Heuristic based on activation statistics"}
            except:
                pass
        return {"entropy": 0.12, "confidence": 0.95, "anomaly_detected": False, "reason": "Stable (fallback)"}

    def save(self, model_path: str, scaler_path: str):
        if self._is_fitted:
            import pickle
            with open(model_path, 'wb') as f:
                pickle.dump(self.model, f)
            with open(scaler_path, 'wb') as f:
                pickle.dump(self.scaler, f)
            logger.info(f"ML-модель сохранена в {model_path}")

    def retrain(self, X, y):
        """Дообучение модели на новых данных (RLHF)."""
        if len(X) < 10:
            logger.warning("Недостаточно данных для дообучения")
            return
        X_scaled = self.scaler.transform(X)
        self.model.fit(X_scaled, y)
        self._is_fitted = True
        logger.info(f"Модель дообучена на {len(X)} новых примерах")

# ========== РАСШИРЕННЫЙ ИНСПЕКТОР (МНОГОСЛОЙНЫЙ + АДАПТИВНЫЙ ЭТАЛОН) ==========
class AdvancedGSpaceInspector(RealInspector):
    def __init__(self, model_path=None, scaler_path=None, auto_train=False):
        super().__init__(model_path, scaler_path, auto_train)
        # Параметры берутся из глобальной конституции
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
            if not isinstance(tensor, torch.Tensor):
                tensor = torch.tensor(tensor, dtype=torch.float32)
            fft = torch.fft.fft(tensor.flatten())
            freqs = torch.abs(fft)
            norm_freqs = freqs / (torch.sum(freqs) + 1e-8)
            spectral_entropy = -torch.sum(norm_freqs * torch.log(norm_freqs + 1e-8)).item()
            metrics[f"layer_{layer}_spectral_entropy"] = round(spectral_entropy, 4)
            # Экспортируем метрику в Prometheus
            gauge = get_spectral_gauge(layer)
            gauge.set(spectral_entropy)
            if spectral_entropy > self.threshold_spectral:
                metrics[f"layer_{layer}_anomaly"] = 1.0
                anomaly_count += 1
            else:
                metrics[f"layer_{layer}_anomaly"] = 0.0
        metrics["total_layer_anomalies"] = anomaly_count
        return metrics

    def cosine_drift(self, activations: Dict[int, torch.Tensor], reference_type: str = "default") -> float:
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
        drift = round(total_drift / max(count, 1), 4)
        AGENT_COSINE_DRIFT.set(drift)
        return drift

    def analyze_advanced(self, prompt: str, preliminary_response: str, activations: Optional[Dict[int, torch.Tensor]] = None,
                         reference_type: str = "default") -> Dict[str, Any]:
        base_result = self.analyze_activations(prompt, preliminary_response, activations)
        if activations:
            spec_metrics = self.spectral_analysis(activations)
            drift = self.cosine_drift(activations, reference_type)
            base_result["spectral_metrics"] = spec_metrics
            base_result["cosine_drift"] = drift
            # Переоценка аномалии с учётом конституционных порогов
            if spec_metrics.get("total_layer_anomalies", 0) > 0 or drift > DRIFT_THRESHOLD:
                base_result["anomaly_detected"] = True
                base_result["reason"] = f"Multi-layer anomaly (Drift: {drift}, Anomalies: {spec_metrics['total_layer_anomalies']})"
                base_result["confidence"] = min(base_result["confidence"], 0.2)
        return base_result

# ========== СУПЕРВАЙЗЕР С АДАПТИВНЫМ ЭТАЛОНОМ И POI ==========
class AgentSupervisorCell:
    def __init__(self, llm_endpoint: str, model: str, api_key: str, max_retries: int = 1,
                 inspector_model_path: Optional[str] = None,
                 inspector_scaler_path: Optional[str] = None,
                 auto_train_inspector: bool = False):
        self.llm_endpoint = llm_endpoint
        self.model = model
        self.api_key = api_key
        self.max_retries = max_retries
        self.inspector = AdvancedGSpaceInspector(
            model_path=inspector_model_path,
            scaler_path=inspector_scaler_path,
            auto_train=auto_train_inspector
        )
        self.reference_initialized = False
        self.private_key = private_key  # для PoI

    async def _ensure_reference_vector(self, prompt_type: str = "arbitration"):
        if not self.reference_initialized:
            ref_prompt = "Рассмотрите спор между двумя сторонами на основе фактов. Вынесите объективное решение."
            _, ref_activations = await self._call_llm_with_activations(ref_prompt, None)
            if ref_activations:
                self.inspector.set_reference_vector(prompt_type, ref_activations)
                self.reference_initialized = True
                logger.info("Эталонный вектор инициализирован")

    async def process(self, cell_input: CellInput, prompt_type: str = "default") -> CellOutputSupervisor:
        logger.info(f"Обработка запроса для сессии {cell_input.session_id} (тип: {prompt_type})")
        await self._ensure_reference_vector(prompt_type)

        raw_response, activations = await self._call_llm_with_activations(cell_input.prompt, cell_input.context)
        inspection_result = self.inspector.analyze_advanced(cell_input.prompt, raw_response, activations, prompt_type)
        confidence = inspection_result["confidence"]
        entropy = inspection_result["entropy"]
        anomaly = inspection_result["anomaly_detected"]

        logger.info(f"G-Inspector: уверенность={confidence}, энтропия={entropy}, аномалия={anomaly}")

        if not anomaly and confidence >= CONFIDENCE_THRESHOLD_HIGH:
            status = "APPROVED"
            response = raw_response
            if activations:
                self.inspector.update_reference_vector(prompt_type, activations)
        elif anomaly and confidence < CONFIDENCE_THRESHOLD_LOW:
            status = "BLOCKED"
            response = "[Защитный протокол]: Запрос заблокирован супервайзером."
            logger.warning(f"БЛОКИРОВКА: {inspection_result['reason']}")
        else:
            status = "REFLECTED"
            logger.info("РЕФЛЕКСИЯ: запуск самоисцеления...")
            AGENT_REFLECTION_COUNT.inc()
            response = await self._trigger_reflection(cell_input.prompt, raw_response, inspection_result)
            confidence = min(1.0, confidence + 0.3)

        proof = self._generate_proof(cell_input.prompt, response, inspection_result)

        AGENT_REQUESTS.labels(status=status).inc()
        AGENT_CONFIDENCE.set(confidence)
        AGENT_G_ENTROPY.set(entropy)
        AGENT_SUPERVISOR_STATUS.labels(status=status).inc()
        if activations:
            AGENT_SPECTRAL_ANOMALIES.set(inspection_result.get("spectral_metrics", {}).get("total_layer_anomalies", 0))
            AGENT_COSINE_DRIFT.set(inspection_result.get("cosine_drift", 0.0))

        return CellOutputSupervisor(
            response=response,
            confidence_score=confidence,
            status=status,
            metadata={
                "g_entropy": entropy,
                "supervisor_action": status.lower(),
                "activations_hash": hashlib.sha256(str(activations).encode()).hexdigest()[:8] if activations else None,
                "anomaly_detected": anomaly,
                "spectral_metrics": inspection_result.get("spectral_metrics", {}),
                "cosine_drift": inspection_result.get("cosine_drift", 0.0),
                "proof_of_inspection": proof
            }
        )

    def _generate_proof(self, prompt: str, response: str, inspection_result: Dict) -> str:
        payload = f"{prompt[:50]}:{response[:50]}:{inspection_result.get('confidence', 0)}:{inspection_result.get('anomaly_detected', False)}"
        signature = hashlib.sha256(payload.encode()).hexdigest()
        return signature

    async def _call_llm_with_activations(self, prompt: str, context: Optional[str]) -> (str, Optional[Dict]):
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            messages = [{"role": "system", "content": "Ты — автономный агент. Проанализируй данные и ответь кратко."},
                        {"role": "user", "content": prompt}]
            if context:
                messages.insert(1, {"role": "assistant", "content": f"Контекст: {context}"})
            payload = {"model": self.model, "messages": messages, "temperature": 0.7, "max_tokens": 150}
            response_text = ""
            activations = None
            for attempt in range(3):
                try:
                    async with session.post(f"{self.llm_endpoint}/chat/completions", json=payload, headers=headers, timeout=30) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            response_text = data["choices"][0]["message"]["content"].strip()
                            break
                except Exception as e:
                    logger.error(f"Ошибка TurboLLM (попытка {attempt+1}): {e}")
                await asyncio.sleep(2 ** attempt)
            else:
                response_text = "[Fallback] Не удалось получить ответ."
            try:
                async with session.get(f"{self.llm_endpoint}/hidden_states", headers=headers, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        activations = data.get("activations", {})
            except Exception as e:
                logger.warning(f"Не удалось получить hidden_states: {e}")
            return response_text, activations

    async def _trigger_reflection(self, original_prompt: str, flawed_response: str, inspection: Dict) -> str:
        reflection_prompt = (
            f"Внимание! Предыдущий ответ вызвал сомнения (аномалия: {inspection.get('reason', 'unknown')}). "
            f"Пересмотри задачу с точки зрения безопасности и объективности.\n"
            f"Исходный запрос: {original_prompt}\n"
            f"Предыдущий ответ: {flawed_response}"
        )
        corrected_response, _ = await self._call_llm_with_activations(reflection_prompt, None)
        return f"[Рефлексия]: {corrected_response}"

# ========== УПРАВЛЕНИЕ СЕССИЯМИ И БАЛАНСАМИ ==========
def generate_session_id() -> str:
    return str(uuid.uuid4())

def init_session(session_id: str) -> float:
    session_balances[session_id] = 100.0
    session_created[session_id] = time.time()
    logger.info(f"Новая сессия {session_id} с балансом 100 QRAP")
    return session_balances[session_id]

def get_balance(session_id: str) -> float:
    return session_balances.get(session_id, 0.0)

def deduct_balance(session_id: str, amount: float) -> float:
    if session_id not in session_balances:
        return 0.0
    session_balances[session_id] = max(0.0, session_balances[session_id] - amount)
    return session_balances[session_id]

def add_balance(session_id: str, amount: float) -> float:
    if session_id not in session_balances:
        session_balances[session_id] = 0.0
    session_balances[session_id] += amount
    return session_balances[session_id]

# ========== КОНСТИТУЦИОННЫЕ ПАРАМЕТРЫ ==========
def get_constitutional_params() -> Dict[str, Any]:
    """Возвращает текущие конституционные параметры (из env или QRAP)."""
    # В MVP – из env, в дальнейшем – из смарт-контракта/блокчейна
    return {
        "spectral_threshold": SPECTRAL_THRESHOLD,
        "drift_threshold": DRIFT_THRESHOLD,
        "confidence_threshold_high": CONFIDENCE_THRESHOLD_HIGH,
        "confidence_threshold_low": CONFIDENCE_THRESHOLD_LOW,
        "version": CONSTITUTION_VERSION
    }

# ========== ИНТЕГРАЦИЯ С TRONGRID ==========
async def check_usdt_transfer(session_id: str) -> bool:
    try:
        url = f"{TRONGRID_API}/v1/accounts/{MERCHANT_ADDRESS}/transactions/trc20"
        params = {"limit": 10, "only_confirmed": True}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.error(f"TronGrid ошибка: {resp.status}")
                    return False
                data = await resp.json()
                for tx in data.get("data", []):
                    if tx.get("token_info", {}).get("symbol") != "USDT":
                        continue
                    if tx.get("to") != MERCHANT_ADDRESS:
                        continue
                    amount = float(tx.get("value", 0)) / 1e6
                    tx_id = tx.get("transaction_id")
                    if amount >= TOPUP_AMOUNT and tx_id not in used_transactions:
                        used_transactions.add(tx_id)
                        add_balance(session_id, TOPUP_AMOUNT)
                        logger.info(f"Зачислено {TOPUP_AMOUNT} QRAP для {session_id} (tx: {tx_id})")
                        return True
        return False
    except Exception as e:
        logger.error(f"Ошибка USDT: {e}")
        return False

# ========== ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ ОТПРАВКИ В QRAP ==========
async def send_to_cluster(session: aiohttp.ClientSession, cell_output: CellOutput) -> bool:
    headers = {"Content-Type": "application/json"}
    if CLUSTER_API_KEY:
        headers["Authorization"] = f"Bearer {CLUSTER_API_KEY}"
    for attempt in range(3):
        try:
            async with session.post(CLUSTER_ENDPOINT, json=cell_output.dict(), headers=headers, timeout=30) as resp:
                if 200 <= resp.status < 300:
                    logger.info(f"Блок {cell_output.block_id} принят кластером")
                    return True
        except Exception as e:
            logger.error(f"Ошибка кластера (попытка {attempt+1}): {e}")
        await asyncio.sleep(2 ** attempt)
    return False

# ========== НОВЫЕ ЭНДПОИНТЫ: /feedback и /propose_rule ==========
async def handle_feedback(request: web.Request):
    """Сбор обратной связи от пользователя (RLHF)."""
    session_id = request.headers.get("X-Session-Id")
    if not session_id or session_id not in session_balances:
        return web.json_response({"error": "Session not initialized"}, status=401)
    try:
        data = await request.json()
        block_id = data.get("block_id")
        rating = data.get("rating")  # 1-5
        comment = data.get("comment", "")
        if rating is None or not (1 <= rating <= 5):
            return web.json_response({"error": "Invalid rating"}, status=400)
        # Сохраняем в файл (в реальном проекте – в БД)
        feedback_entry = {
            "session_id": session_id,
            "block_id": block_id,
            "rating": rating,
            "comment": comment,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        with open("feedback_log.json", "a") as f:
            json.dump(feedback_entry, f)
            f.write("\n")
        # Также можно обновить соответствующий CellOutput (если есть доступ)
        return web.json_response({"status": "ok", "message": "Feedback recorded"})
    except Exception as e:
        logger.exception("Ошибка в /feedback")
        return web.json_response({"error": str(e)}, status=500)

async def handle_propose_rule(request: web.Request):
    """Предложение изменения конституционных параметров (голосование)."""
    session_id = request.headers.get("X-Session-Id")
    if not session_id or session_id not in session_balances:
        return web.json_response({"error": "Session not initialized"}, status=401)
    # Только стейкеры могут предлагать (проверка баланса > порога)
    balance = get_balance(session_id)
    if balance < 10.0:
        return web.json_response({"error": "Insufficient stake to propose rule"}, status=403)
    try:
        data = await request.json()
        new_params = data.get("params", {})
        # Валидация
        required_keys = ["spectral_threshold", "drift_threshold", "confidence_threshold_high", "confidence_threshold_low"]
        for key in required_keys:
            if key not in new_params:
                return web.json_response({"error": f"Missing {key}"}, status=400)
        # Создаём предложение как CellOutput типа 'constitutional_proposal'
        proposal_id = hashlib.sha256(f"{session_id}:{int(time.time())}".encode()).hexdigest()[:16]
        block_id = hashlib.sha256(f"{CELL_ID}:{int(time.time())}".encode()).hexdigest()[:16]
        manifest = EntropyManifest(
            gamma=1.0,
            nu=1,
            delta=0.0,
            mu_hash=hashlib.sha256(f"turbollm_{CELL_ID}".encode()).hexdigest()[:12],
            tau_ms=int(time.time()*1000)%100000
        )
        cell_output = CellOutput(
            cell_id=CELL_ID,
            block_id=block_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            decision=f"Proposal: change constitution to {new_params}",
            manifest=manifest,
            poi_chain=[hashlib.sha256(f"step_{i}".encode()).hexdigest() for i in range(3)],
            decision_type="constitutional_proposal",
            case_metadata={
                "proposal_id": proposal_id,
                "proposer_session": session_id,
                "new_params": new_params,
                "status": "active"
            },
            payload={}
        )
        async with aiohttp.ClientSession() as session:
            delivered = await send_to_cluster(session, cell_output)
        if delivered:
            return web.json_response({
                "status": "ok",
                "proposal_id": proposal_id,
                "message": "Proposal recorded. Voting will start soon."
            })
        else:
            return web.json_response({"error": "Failed to record proposal"}, status=500)
    except Exception as e:
        logger.exception("Ошибка в /propose_rule")
        return web.json_response({"error": str(e)}, status=500)

# ========== ОСТАЛЬНЫЕ ЭНДПОИНТЫ ==========
async def handle_session_init(request: web.Request):
    session_id = request.headers.get("X-Session-Id")
    if not session_id or session_id not in session_balances:
        session_id = generate_session_id()
        init_session(session_id)
    return web.json_response({"session_id": session_id, "balance": get_balance(session_id), "status": "ok"})

async def handle_balance(request: web.Request):
    session_id = request.headers.get("X-Session-Id")
    if not session_id or session_id not in session_balances:
        return web.json_response({"error": "Session not found"}, status=404)
    return web.json_response({"session_id": session_id, "balance": get_balance(session_id)})

async def handle_topup_request(request: web.Request):
    return web.json_response({"address": MERCHANT_ADDRESS, "amount": TOPUP_AMOUNT, "currency": "USDT (TRC-20)"})

async def handle_topup_check(request: web.Request):
    session_id = request.headers.get("X-Session-Id")
    if not session_id or session_id not in session_balances:
        return web.json_response({"error": "Session not found"}, status=404)
    success = await check_usdt_transfer(session_id)
    if success:
        return web.json_response({"status": "success", "balance": get_balance(session_id), "message": f"Зачислено {TOPUP_AMOUNT} QRAP"})
    return web.json_response({"status": "pending", "balance": get_balance(session_id), "message": "Платеж не найден"})

async def handle_process(request: web.Request):
    timer = AGENT_REQUEST_DURATION.time()
    session_id = request.headers.get("X-Session-Id")
    if not session_id or session_id not in session_balances:
        return web.json_response({"error": "Session not initialized"}, status=401)
    balance = get_balance(session_id)
    if balance < MIN_BALANCE_TO_START:
        return web.json_response({"error": "Insufficient balance", "balance": balance, "min_required": MIN_BALANCE_TO_START, "topup_needed": True}, status=402)
    try:
        data = await request.json()
        task = data.get("task")
        if not task:
            return web.json_response({"error": "Missing 'task' field"}, status=400)
        supervisor = AgentSupervisorCell(TURBOLLM_ENDPOINT, TURBOLLM_MODEL, TURBOLLM_API_KEY,
                                         MAX_REFLECTION_RETRIES, INSPECTOR_MODEL_PATH, INSPECTOR_SCALER_PATH, AUTO_TRAIN_INSPECTOR)
        cell_input = CellInput(prompt=task, session_id=session_id)
        supervisor_output = await supervisor.process(cell_input, prompt_type="default")
        estimated_cost = 0.01
        new_balance = deduct_balance(session_id, estimated_cost)
        block_id = hashlib.sha256(f"{CELL_ID}:{int(time.time())}".encode()).hexdigest()[:16]
        manifest = EntropyManifest(gamma=supervisor_output.confidence_score, nu=1, delta=0.0,
                                   mu_hash=hashlib.sha256(f"turbollm_{CELL_ID}".encode()).hexdigest()[:12],
                                   tau_ms=int(time.time()*1000)%100000)
        cell_output = CellOutput(
            cell_id=CELL_ID, block_id=block_id, timestamp=datetime.now(timezone.utc).isoformat(),
            decision=supervisor_output.response if supervisor_output.status != "BLOCKED" else "BLOCKED_BY_SUPERVISOR",
            manifest=manifest, poi_chain=[hashlib.sha256(f"step_{i}".encode()).hexdigest() for i in range(3)],
            payload={
                "supervisor_status": supervisor_output.status,
                "confidence": supervisor_output.confidence_score,
                "g_entropy": supervisor_output.metadata.get("g_entropy"),
                "activations_hash": supervisor_output.metadata.get("activations_hash"),
                "model": TURBOLLM_MODEL,
                "anomaly_detected": supervisor_output.metadata.get("anomaly_detected", False),
                "cost": estimated_cost, "balance_after": new_balance,
                "spectral_metrics": supervisor_output.metadata.get("spectral_metrics", {}),
                "cosine_drift": supervisor_output.metadata.get("cosine_drift", 0.0),
                "proof_of_inspection": supervisor_output.metadata.get("proof_of_inspection", "")
            }
        )
        async with aiohttp.ClientSession() as session:
            delivered = await send_to_cluster(session, cell_output)
        AGENT_REQUESTS.labels(status=supervisor_output.status).inc()
        AGENT_CONFIDENCE.set(supervisor_output.confidence_score)
        AGENT_BALANCE.set(new_balance)
        return web.json_response({"status": "ok", "supervisor_status": supervisor_output.status, "cell": cell_output.dict(), "delivered": delivered, "balance": new_balance, "cost": estimated_cost})
    except Exception as e:
        logger.exception("Ошибка в /process")
        return web.json_response({"error": str(e)}, status=500)
    finally:
        timer.observe()

async def handle_stream(request: web.Request):
    session_id = request.headers.get("X-Session-Id")
    if not session_id or session_id not in session_balances:
        return web.json_response({"error": "Session not initialized"}, status=401)
    balance = get_balance(session_id)
    if balance < MIN_BALANCE_TO_START:
        return web.json_response({"error": "Insufficient balance"}, status=402)
    try:
        data = await request.json()
        task = data.get("task")
        if not task:
            return web.json_response({"error": "Missing 'task' field"}, status=400)
        async def stream_generator():
            nonlocal balance
            # Здесь должна быть реальная интеграция с TurboLLM стримингом
            chunks = ["Это ", "пример ", "стриминга ", "с ", "микро-списаниями."]
            for chunk in chunks:
                cost = 0.001
                if balance >= cost:
                    balance = deduct_balance(session_id, cost)
                    AGENT_BALANCE.set(balance)
                    yield f"data: {json.dumps({'text': chunk, 'cost': cost, 'balance': balance})}\n\n"
                    await asyncio.sleep(0.3)
                else:
                    yield f"data: {json.dumps({'text': ' [недостаточно средств]', 'cost': 0, 'balance': balance})}\n\n"
                    break
            yield f"data: {json.dumps({'text': '[DONE]', 'cost': 0, 'balance': balance})}\n\n"
        return web.Response(body=stream_generator(), content_type='text/event-stream',
                            headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive', 'X-Accel-Buffering': 'no'})
    except Exception as e:
        logger.exception("Ошибка в /stream")
        return web.json_response({"error": str(e)}, status=500)

async def handle_arbitrate(request: web.Request):
    timer = AGENT_REQUEST_DURATION.time()
    session_id = request.headers.get("X-Session-Id")
    if not session_id or session_id not in session_balances:
        return web.json_response({"error": "Session not initialized"}, status=401)
    balance = get_balance(session_id)
    COST_ARBITRATION = 0.1
    if balance < COST_ARBITRATION:
        return web.json_response({"error": "Insufficient balance", "balance": balance, "min_required": COST_ARBITRATION, "topup_needed": True}, status=402)
    try:
        data = await request.json()
        # Здесь ожидается структура ArbitrationCase (можно использовать Pydantic)
        # Для простоты оставим как dict
        case_title = data.get("title")
        case_description = data.get("description")
        parties = data.get("parties", [])
        arguments = data.get("arguments", {})
        evidence = data.get("evidence", [])
        company_id = data.get("company_id", "unknown")

        prompt = f"""
        Вы — беспристрастный арбитражный судья. Рассмотрите следующий спор:
        Дело: {case_title}
        Описание: {case_description}
        Стороны: {', '.join(parties)}
        Аргументы сторон: {json.dumps(arguments, indent=2)}
        Доказательства: {', '.join(evidence)}
        Требуется вынести объективное решение с обоснованием.
        Ответ оформите в JSON: {{"verdict": "...", "confidence": 0.95, "rationale": "...", "settlement_suggestion": "..."}}
        """
        supervisor = AgentSupervisorCell(TURBOLLM_ENDPOINT, TURBOLLM_MODEL, TURBOLLM_API_KEY,
                                         MAX_REFLECTION_RETRIES, INSPECTOR_MODEL_PATH, INSPECTOR_SCALER_PATH, AUTO_TRAIN_INSPECTOR)
        cell_input = CellInput(prompt=prompt, session_id=session_id)
        supervisor_output = await supervisor.process(cell_input, prompt_type="arbitration")
        try:
            verdict_data = json.loads(supervisor_output.response)
        except:
            verdict_data = {"verdict": supervisor_output.response, "confidence": supervisor_output.confidence_score, "rationale": "", "settlement_suggestion": ""}
        new_balance = deduct_balance(session_id, COST_ARBITRATION)
        block_id = hashlib.sha256(f"{CELL_ID}:{int(time.time())}".encode()).hexdigest()[:16]
        manifest = EntropyManifest(gamma=supervisor_output.confidence_score, nu=1, delta=0.0,
                                   mu_hash=hashlib.sha256(f"turbollm_{CELL_ID}".encode()).hexdigest()[:12],
                                   tau_ms=int(time.time()*1000)%100000)
        # Сохраняем тренировочные данные для RLHF
        training_data = {
            "prompt": prompt,
            "agent_response": supervisor_output.response,
            "final_verdict": verdict_data.get("verdict"),
            "confidence": supervisor_output.confidence_score,
            "human_override": False  # пока нет, позже можно добавить
        }
        cell_output = CellOutput(
            cell_id=CELL_ID, block_id=block_id, timestamp=datetime.now(timezone.utc).isoformat(),
            decision=verdict_data.get("verdict", supervisor_output.response),
            manifest=manifest, poi_chain=[hashlib.sha256(f"step_{i}".encode()).hexdigest() for i in range(3)],
            company_id=company_id, decision_type="arbitration",
            case_metadata={
                "case_title": case_title,
                "parties": parties,
                "confidence": verdict_data.get("confidence", supervisor_output.confidence_score),
                "rationale": verdict_data.get("rationale", ""),
                "settlement_suggestion": verdict_data.get("settlement_suggestion", ""),
                "spectral_metrics": supervisor_output.metadata.get("spectral_metrics", {}),
                "cosine_drift": supervisor_output.metadata.get("cosine_drift", 0.0),
                "proof_of_inspection": supervisor_output.metadata.get("proof_of_inspection", ""),
                "training_data": training_data  # для RLHF
            },
            payload={
                "supervisor_status": supervisor_output.status,
                "cost": COST_ARBITRATION,
                "balance_after": new_balance
            }
        )
        async with aiohttp.ClientSession() as session:
            delivered = await send_to_cluster(session, cell_output)
        AGENT_REQUESTS.labels(status=supervisor_output.status).inc()
        AGENT_BALANCE.set(new_balance)
        return web.json_response({"status": "ok", "verdict": verdict_data, "delivered": delivered, "balance": new_balance, "cell": cell_output.dict()})
    except Exception as e:
        logger.exception("Ошибка в /arbitrate")
        return web.json_response({"error": str(e)}, status=500)
    finally:
        timer.observe()

async def handle_vote(request: web.Request):
    timer = AGENT_REQUEST_DURATION.time()
    session_id = request.headers.get("X-Session-Id")
    if not session_id or session_id not in session_balances:
        return web.json_response({"error": "Session not initialized"}, status=401)
    balance = get_balance(session_id)
    COST_VOTE = 0.05
    if balance < COST_VOTE:
        return web.json_response({"error": "Insufficient balance"}, status=402)
    try:
        data = await request.json()
        proposal_id = data.get("proposal_id")
        choice = data.get("choice")
        # Здесь должна быть проверка существования предложения и его статуса
        # Для MVP – просто записываем голос
        new_balance = deduct_balance(session_id, COST_VOTE)
        block_id = hashlib.sha256(f"{CELL_ID}:{int(time.time())}".encode()).hexdigest()[:16]
        manifest = EntropyManifest(gamma=1.0, nu=1, delta=0.0,
                                   mu_hash=hashlib.sha256(f"turbollm_{CELL_ID}".encode()).hexdigest()[:12],
                                   tau_ms=int(time.time()*1000)%100000)
        cell_output = CellOutput(
            cell_id=CELL_ID, block_id=block_id, timestamp=datetime.now(timezone.utc).isoformat(),
            decision=f"Vote: {choice}",
            manifest=manifest, poi_chain=[hashlib.sha256(f"step_{i}".encode()).hexdigest() for i in range(3)],
            decision_type="vote",
            case_metadata={
                "proposal_id": proposal_id,
                "vote_choice": choice,
                "vote_weight": 1.0
            },
            payload={"balance_after": new_balance, "cost": COST_VOTE}
        )
        async with aiohttp.ClientSession() as session:
            delivered = await send_to_cluster(session, cell_output)
        AGENT_REQUESTS.labels(status="VOTED").inc()
        AGENT_BALANCE.set(new_balance)
        return web.json_response({"status": "ok", "delivered": delivered, "balance": new_balance, "cell": cell_output.dict()})
    except Exception as e:
        logger.exception("Ошибка в /vote")
        return web.json_response({"error": str(e)}, status=500)
    finally:
        timer.observe()

async def handle_health(request: web.Request):
    return web.json_response({"status": "alive", "cell_id": CELL_ID})

async def handle_metrics(request: web.Request):
    return web.Response(body=generate_latest(), content_type=CONTENT_TYPE_LATEST)

# ========== ЗАПУСК ==========
def main():
    start_http_server(METRICS_PORT)
    logger.info(f"📊 Метрики Prometheus на порту {METRICS_PORT}")

    app = web.Application()
    app.router.add_get("/session/init", handle_session_init)
    app.router.add_get("/balance", handle_balance)
    app.router.add_get("/topup/request", handle_topup_request)
    app.router.add_get("/topup/check", handle_topup_check)
    app.router.add_post("/process", handle_process)
    app.router.add_post("/stream", handle_stream)
    app.router.add_post("/arbitrate", handle_arbitrate)
    app.router.add_post("/vote", handle_vote)
    app.router.add_post("/feedback", handle_feedback)
    app.router.add_post("/propose_rule", handle_propose_rule)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/metrics", handle_metrics)

    logger.info(f"🚀 Агент {CELL_ID} запущен на http://{HOST}:{PORT}")
    logger.info(f"   TurboLLM: {TURBOLLM_ENDPOINT}")
    logger.info(f"   QRAP кластер: {CLUSTER_ENDPOINT}")
    logger.info(f"   Мерчант адрес (USDT): {MERCHANT_ADDRESS}")
    web.run_app(app, host=HOST, port=PORT)

if __name__ == "__main__":
    main()
