# g_inspector/config.py
"""
Конфигурация G‑Space Inspector: индексы слоёв, пороги, пути к моделям.
"""

import os

# Какие слои модели перехватывать (по умолчанию последние три)
# Для Qwen/LLaMA/Mistral индексы начинаются с 0
DEFAULT_LAYER_INDICES = [-1, -2, -3]   # можно задать конкретные: [30, 31, 32]

# Пороги для детекции аномалий
ANOMALY_THRESHOLD = 0.6          # вероятность аномалии выше этого значения
CONFIDENCE_THRESHOLD_HIGH = 0.8  # для супервайзера
CONFIDENCE_THRESHOLD_LOW = 0.5

# Пути к ML-модели (можно переопределить через env)
INSPECTOR_MODEL_PATH = os.getenv("INSPECTOR_MODEL_PATH", "g_inspector/models/inspector_model.pkl")
INSPECTOR_SCALER_PATH = os.getenv("INSPECTOR_SCALER_PATH", "g_inspector/models/inspector_scaler.pkl")
AUTO_TRAIN_INSPECTOR = os.getenv("AUTO_TRAIN_INSPECTOR", "true").lower() == "true"

# Таймауты для HTTP-запросов
LLM_TIMEOUT = 30
HIDDEN_STATES_TIMEOUT = 5

# Размерность признаков (4 статистики на слой * число слоёв)
FEATURE_DIM = 12  # при 3 слоях

# Параметры генерации синтетических данных
SYNTHETIC_N_SAMPLES = 5000
SYNTHETIC_ANOMALY_RATIO = 0.25
