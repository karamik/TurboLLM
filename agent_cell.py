#!/usr/bin/env python3
"""
agent_cell.py - HTTP-сервис-агент с супервайзером (G-Space Inspector + Self-Healing)
для связи TurboLLM с QRAP-кластером.
"""

import os
import time
import random
import hashlib
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

import numpy as np
import torch
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
import aiohttp
from aiohttp import web
from pydantic import BaseModel, ValidationError

# Prometheus метрики
from prometheus_client import Counter, Gauge, Histogram, start_http_server, generate_latest, CONTENT_TYPE_LATEST

# ========== ЛОГИРОВАНИЕ ==========
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("AgentSupervisorCell")

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
METRICS_PORT = int(os.getenv("METRICS_PORT", "9090"))   # порт для метрик Prometheus

# Пороги для супервайзера
CONFIDENCE_THRESHOLD_HIGH = float(os.getenv("CONFIDENCE_THRESHOLD_HIGH", "0.8"))
CONFIDENCE_THRESHOLD_LOW = float(os.getenv("CONFIDENCE_THRESHOLD_LOW", "0.5"))
MAX_REFLECTION_RETRIES = int(os.getenv("MAX_REFLECTION_RETRIES", "1"))

# Пути к ML-модели (если не заданы – используется автообучение на синтетике)
INSPECTOR_MODEL_PATH = os.getenv("INSPECTOR_MODEL_PATH", "inspector_model.pkl")
INSPECTOR_SCALER_PATH = os.getenv("INSPECTOR_SCALER_PATH", "inspector_scaler.pkl")
AUTO_TRAIN_INSPECTOR = os.getenv("AUTO_TRAIN_INSPECTOR", "true").lower() == "true"

# ========== PROMETHEUS МЕТРИКИ АГЕНТА ==========
AGENT_REQUESTS = Counter('agent_requests_total', 'Total requests processed by agent', ['status'])
AGENT_CONFIDENCE = Gauge('agent_confidence_score', 'Latest confidence score')
AGENT_G_ENTROPY = Gauge('agent_g_entropy', 'Latest G-Space entropy')
AGENT_SUPERVISOR_STATUS = Counter('agent_supervisor_status_total', 'Supervisor decisions', ['status'])
AGENT_REQUEST_DURATION = Histogram('agent_request_duration_seconds', 'Request processing duration')
AGENT_REFLECTION_COUNT = Counter('agent_reflection_total', 'Number of reflection triggers')

# ========== PYDANTIC МОДЕЛИ ДЛЯ CELLOUTPUT (QRAP) ==========
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

# ========== DATACLASS'Ы ДЛЯ СУПЕРВАЙЗЕРА ==========
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

# ========== РЕАЛЬНЫЙ G-SPACE INSPECTOR (ML-КЛАССИФИКАТОР) ==========
class RealInspector:
    """
    Анализирует скрытые активации (hidden_states) модели с помощью ML-классификатора.
    Поддерживает автообучение на синтетических данных при отсутствии сохранённой модели.
    """
    def __init__(self,
                 model_path: Optional[str] = None,
                 scaler_path: Optional[str] = None,
                 auto_train: bool = False):
        self.model = None
        self.scaler = None
        self.anomaly_threshold = 0.6
        self._is_fitted = False

        # Загрузка готовой модели, если есть
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

        # Если модель не загружена, но auto_train=True – обучаем на синтетике
        if not self._is_fitted and auto_train:
            logger.info("ML-модель не найдена, выполняется обучение на синтетических данных...")
            self._train_on_synthetic()
            if model_path and scaler_path:
                self.save(model_path, scaler_path)

    def _train_on_synthetic(self, n_samples=5000, anomaly_ratio=0.25):
        """Генерирует синтетические данные и обучает логистическую регрессию."""
        FEATURE_DIM = 12   # 4 статистики на слой * 3 слоя (как в _extract_features)
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
        """
        Преобразует активации в плоский вектор признаков.
        Ожидает словарь {номер_слоя: тензор или список}.
        """
        features = []
        for layer, vals in activations.items():
            if isinstance(vals, torch.Tensor):
                vals = vals.numpy()
            elif isinstance(vals, list):
                vals = np.array(vals)
            if vals.ndim > 1:
                vals = vals.mean(axis=0)   # усреднение по первому измерению
            # Статистики: среднее, стандартное отклонение, максимум, минимум
            features.extend([vals.mean(), vals.std(), vals.max(), vals.min()])
        return np.array(features).reshape(1, -1)

    def analyze_activations(self, prompt: str, preliminary_response: str, activations: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Анализирует активации и возвращает словарь с метриками.
        В случае ошибки или отсутствия активаций переключается на эвристику.
        """
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
        """Запасная эвристика: проверка по ключевым словам или статистикам активаций."""
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
        """Сохраняет обученную модель и скейлер в файлы."""
        if self._is_fitted:
            import pickle
            with open(model_path, 'wb') as f:
                pickle.dump(self.model, f)
            with open(scaler_path, 'wb') as f:
                pickle.dump(self.scaler, f)
            logger.info(f"ML-модель сохранена в {model_path}")
        else:
            logger.warning("Модель не обучена, сохранение невозможно")

# ========== СУПЕРВАЙЗЕР-ЯЧЕЙКА (САМОИСЦЕЛЯЮЩИЙСЯ АГЕНТ) ==========
class AgentSupervisorCell:
    """
    Интеллектуальная ячейка агента с функцией самоисцеления (Self-Healing)
    и надзором на базе скрытых активаций G-Space.
    """
    def __init__(self,
                 llm_endpoint: str,
                 model: str,
                 api_key: str,
                 max_retries: int = 1,
                 inspector_model_path: Optional[str] = None,
                 inspector_scaler_path: Optional[str] = None,
                 auto_train_inspector: bool = False):
        self.llm_endpoint = llm_endpoint
        self.model = model
        self.api_key = api_key
        self.max_retries = max_retries
        self.inspector = RealInspector(
            model_path=inspector_model_path,
            scaler_path=inspector_scaler_path,
            auto_train=auto_train_inspector
        )

    async def process(self, cell_input: CellInput) -> CellOutputSupervisor:
        logger.info(f"Обработка запроса для сессии {cell_input.session_id}...")

        # 1. Первичный инференс (получение ответа и активаций от TurboLLM)
        raw_response, activations = await self._call_llm_with_activations(cell_input.prompt, cell_input.context)

        # 2. Инспекция G-пространства
        inspection_result = self.inspector.analyze_activations(cell_input.prompt, raw_response, activations)
        confidence = inspection_result["confidence"]
        entropy = inspection_result["entropy"]
        anomaly = inspection_result["anomaly_detected"]

        logger.info(f"G-Inspector: уверенность={confidence}, энтропия={entropy}, аномалия={anomaly}")

        # 3. Принятие решений супервайзером
        if not anomaly and confidence >= CONFIDENCE_THRESHOLD_HIGH:
            status = "APPROVED"
            response = raw_response
        elif anomaly and confidence < CONFIDENCE_THRESHOLD_LOW:
            status = "BLOCKED"
            response = "[Защитный протокол]: Запрос заблокирован супервайзером из-за обнаружения манипулятивных паттернов в G-пространстве."
            logger.warning(f"БЛОКИРОВКА: {inspection_result['reason']}")
        else:
            status = "REFLECTED"
            logger.info("РЕФЛЕКСИЯ: модель сомневается или низкая уверенность, запуск самоисцеления...")
            AGENT_REFLECTION_COUNT.inc()
            response = await self._trigger_reflection(cell_input.prompt, raw_response)
            confidence = min(1.0, confidence + 0.3)

        # Обновляем метрики
        AGENT_REQUESTS.labels(status=status).inc()
        AGENT_CONFIDENCE.set(confidence)
        AGENT_G_ENTROPY.set(entropy)
        AGENT_SUPERVISOR_STATUS.labels(status=status).inc()

        return CellOutputSupervisor(
            response=response,
            confidence_score=confidence,
            status=status,
            metadata={
                "g_entropy": entropy,
                "supervisor_action": status.lower(),
                "activations_hash": hashlib.sha256(str(activations).encode()).hexdigest()[:8] if activations else None,
                "anomaly_detected": anomaly
            }
        )

    async def _call_llm_with_activations(self, prompt: str, context: Optional[str]) -> (str, Optional[Dict]):
        """
        Вызов TurboLLM (chat/completions) и получение активаций через /hidden_states.
        Возвращает (ответ, словарь активаций).
        """
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            messages = [
                {"role": "system", "content": "Ты — автономный агент. Проанализируй данные и ответь кратко."},
                {"role": "user", "content": prompt}
            ]
            if context:
                messages.insert(1, {"role": "assistant", "content": f"Контекст: {context}"})

            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 150
            }

            response_text = ""
            activations = None

            for attempt in range(3):
                try:
                    async with session.post(f"{self.llm_endpoint}/chat/completions",
                                            json=payload, headers=headers, timeout=30) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            response_text = data["choices"][0]["message"]["content"].strip()
                            break
                        else:
                            text = await resp.text()
                            logger.error(f"Ошибка TurboLLM (попытка {attempt+1}): {resp.status} - {text}")
                except Exception as e:
                    logger.error(f"Ошибка соединения с TurboLLM (попытка {attempt+1}): {e}")
                await asyncio.sleep(2 ** attempt)
            else:
                logger.error("Не удалось получить ответ от TurboLLM после 3 попыток. Используем fallback.")
                response_text = "[Fallback] Не удалось получить ответ от модели."

            # Получение активаций (если эндпоинт доступен)
            try:
                async with session.get(f"{self.llm_endpoint}/hidden_states", headers=headers, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        activations = data.get("activations", {})
                    else:
                        logger.warning(f"Не удалось получить hidden_states: HTTP {resp.status}")
            except Exception as e:
                logger.warning(f"Не удалось получить hidden_states: {e}")

            return response_text, activations

    async def _trigger_reflection(self, original_prompt: str, flawed_response: str) -> str:
        """Запускает рефлексию – повторный запрос с корректирующим промптом."""
        reflection_prompt = (
            f"Внимание! Предыдущий ответ вызвал сомнения в надежности. "
            f"Пересмотри задачу с точки зрения безопасности и корпоративных регламентов.\n"
            f"Исходный запрос: {original_prompt}\n"
            f"Предыдущий ответ (требует проверки): {flawed_response}"
        )
        corrected_response, _ = await self._call_llm_with_activations(reflection_prompt, None)
        return f"[Рефлексия выполнена]: {corrected_response}"

# ========== ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ ОТПРАВКИ В QRAP ==========
async def send_to_cluster(session: aiohttp.ClientSession, cell_output: CellOutput) -> bool:
    """Отправляет CellOutput в QRAP-кластер с повторными попытками."""
    headers = {"Content-Type": "application/json"}
    if CLUSTER_API_KEY:
        headers["Authorization"] = f"Bearer {CLUSTER_API_KEY}"

    for attempt in range(3):
        try:
            async with session.post(CLUSTER_ENDPOINT, json=cell_output.dict(), headers=headers, timeout=30) as resp:
                if 200 <= resp.status < 300:
                    res_data = await resp.json()
                    logger.info(f"Блок {cell_output.block_id} принят кластером: {res_data}")
                    return True
                else:
                    text = await resp.text()
                    logger.error(f"Ошибка кластера (попытка {attempt+1}): {resp.status} - {text}")
        except Exception as e:
            logger.error(f"Ошибка соединения с кластером (попытка {attempt+1}): {e}")
        await asyncio.sleep(2 ** attempt)
    return False

# ========== HTTP-ОБРАБОТЧИКИ ==========
async def handle_process(request: web.Request):
    """POST /process – принять задачу, прогнать через супервайзера, отправить в QRAP."""
    timer = AGENT_REQUEST_DURATION.time()
    try:
        data = await request.json()
        task = data.get("task")
        if not task:
            return web.json_response({"error": "Missing 'task' field"}, status=400)

        # Создаём супервайзера (можно вынести глобально для производительности)
        supervisor = AgentSupervisorCell(
            llm_endpoint=TURBOLLM_ENDPOINT,
            model=TURBOLLM_MODEL,
            api_key=TURBOLLM_API_KEY,
            max_retries=MAX_REFLECTION_RETRIES,
            inspector_model_path=INSPECTOR_MODEL_PATH,
            inspector_scaler_path=INSPECTOR_SCALER_PATH,
            auto_train_inspector=AUTO_TRAIN_INSPECTOR
        )
        cell_input = CellInput(prompt=task, session_id=data.get("session_id", CELL_ID))
        supervisor_output = await supervisor.process(cell_input)

        # Формируем CellOutput для QRAP
        block_id = hashlib.sha256(f"{CELL_ID}:{int(time.time())}".encode()).hexdigest()[:16]
        manifest = EntropyManifest(
            gamma=supervisor_output.confidence_score,
            nu=1,
            delta=0.0,
            mu_hash=hashlib.sha256(f"turbollm_{CELL_ID}".encode()).hexdigest()[:12],
            tau_ms=int(time.time() * 1000) % 100000
        )
        cell_output = CellOutput(
            cell_id=CELL_ID,
            block_id=block_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            decision=supervisor_output.response if supervisor_output.status != "BLOCKED" else "BLOCKED_BY_SUPERVISOR",
            manifest=manifest,
            poi_chain=[hashlib.sha256(f"step_{i}".encode()).hexdigest() for i in range(3)],
            payload={
                "supervisor_status": supervisor_output.status,
                "confidence": supervisor_output.confidence_score,
                "g_entropy": supervisor_output.metadata.get("g_entropy"),
                "activations_hash": supervisor_output.metadata.get("activations_hash"),
                "model": TURBOLLM_MODEL,
                "anomaly_detected": supervisor_output.metadata.get("anomaly_detected", False)
            }
        )

        # Отправка в QRAP
        async with aiohttp.ClientSession() as session:
            delivered = await send_to_cluster(session, cell_output)

        return web.json_response({
            "status": "ok" if delivered else "delivery_failed",
            "supervisor_status": supervisor_output.status,
            "cell": cell_output.dict(),
            "delivered": delivered
        }, status=200 if delivered else 207)

    except ValidationError as e:
        return web.json_response({"error": f"Validation error: {e}"}, status=400)
    except Exception as e:
        logger.exception("Внутренняя ошибка в /process")
        return web.json_response({"error": f"Internal error: {str(e)}"}, status=500)
    finally:
        timer.observe()

async def handle_health(request: web.Request):
    """Healthcheck для оркестратора."""
    return web.json_response({"status": "alive", "cell_id": CELL_ID})

async def handle_metrics(request: web.Request):
    """Эндпоинт для Prometheus метрик."""
    return web.Response(body=generate_latest(), content_type=CONTENT_TYPE_LATEST)

# ========== ЗАПУСК СЕРВЕРА ==========
def main():
    # Запуск HTTP-сервера для метрик на отдельном порту (9090)
    start_http_server(METRICS_PORT)
    logger.info(f"📊 Метрики Prometheus доступны на порту {METRICS_PORT}")

    # Основной сервер агента
    app = web.Application()
    app.router.add_post("/process", handle_process)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/metrics", handle_metrics)   # можно и так, если не хотим отдельный порт

    logger.info(f"🚀 Агент {CELL_ID} запущен на http://{HOST}:{PORT}")
    logger.info(f"   TurboLLM: {TURBOLLM_ENDPOINT}")
    logger.info(f"   QRAP кластер: {CLUSTER_ENDPOINT}")
    web.run_app(app, host=HOST, port=PORT)

if __name__ == "__main__":
    main()
