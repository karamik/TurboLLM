#!/usr/bin/env python3
"""
train_inspector_from_feedback.py - Дообучение G-Space инспектора на основе
обратной связи пользователей (RLHF).

Поддерживает:
- Хранение активаций в SQLite (вместо файлов).
- Использование спектральных метрик из CellOutput, если активации не найдены.
- Фильтрацию фидбеков по минимальному стейку (балансу) пользователя.

Пример запуска:
    python scripts/train_inspector_from_feedback.py \
        --db activations.db \
        --feedback-log feedback_log.json \
        --model-path inspector_model.pkl \
        --scaler-path inspector_scaler.pkl \
        --min-stake 10 \
        --threshold 10
"""

import os
import sys
import json
import sqlite3
import argparse
import logging
from typing import Dict, List, Tuple, Optional
import numpy as np

# Добавляем путь к корню проекта (чтобы импортировать real_inspector)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from real_inspector import RealInspector

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("TrainInspectorFromFeedback")

# ========== РАБОТА С БАЗОЙ ДАННЫХ ==========
def init_activations_db(db_path: str) -> sqlite3.Connection:
    """Создаёт таблицу activations, если её нет."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS activations (
            block_id TEXT PRIMARY KEY,
            activations_json TEXT,
            timestamp TEXT
        )
    ''')
    conn.commit()
    return conn

def get_activations_from_db(conn: sqlite3.Connection, block_id: str) -> Optional[Dict]:
    """Возвращает словарь активаций для block_id, или None."""
    cur = conn.cursor()
    cur.execute("SELECT activations_json FROM activations WHERE block_id = ?", (block_id,))
    row = cur.fetchone()
    if row and row[0]:
        try:
            return json.loads(row[0])
        except json.JSONDecodeError:
            logger.warning(f"Ошибка парсинга activations_json для {block_id}")
    return None

# ========== ЗАГРУЗКА ЛОГОВ ФИДБЕКА ==========
def load_feedback_log(feedback_path: str) -> List[Dict]:
    """Загружает JSON-логи обратной связи (каждая запись на отдельной строке)."""
    feedback_entries = []
    if not os.path.exists(feedback_path):
        logger.warning(f"Файл {feedback_path} не найден, пропускаем.")
        return []
    with open(feedback_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entry = json.loads(line)
                    feedback_entries.append(entry)
                except json.JSONDecodeError as e:
                    logger.warning(f"Ошибка парсинга строки: {e}")
    logger.info(f"Загружено {len(feedback_entries)} записей обратной связи")
    return feedback_entries

# ========== ИЗВЛЕЧЕНИЕ ПРИЗНАКОВ ==========
def extract_features_from_activations(activations: Dict, inspector: RealInspector) -> Optional[np.ndarray]:
    """Извлекает вектор признаков из активаций."""
    if not activations:
        return None
    try:
        # Настраиваем размерность на основе активаций
        inspector._configure_from_activations(activations)
        features = inspector._extract_features(activations)
        return features.flatten()
    except Exception as e:
        logger.warning(f"Ошибка извлечения признаков из активаций: {e}")
        return None

def extract_features_from_spectral_metrics(spectral_metrics: Dict) -> np.ndarray:
    """
    Извлекает вектор признаков из спектральных метрик (сохранённых в CellOutput).
    Ожидается словарь с ключами 'layer_X_spectral_entropy' и 'total_layer_anomalies'.
    Возвращает плоский массив: сначала все энтропии по слоям, затем total_anomalies.
    """
    if not spectral_metrics:
        return None
    # Сортируем слои по номеру (из ключей)
    layer_entropies = []
    for key, value in spectral_metrics.items():
        if key.endswith("_spectral_entropy"):
            layer_entropies.append(value)
    # Добавляем total_layer_anomalies в конец
    anomalies = spectral_metrics.get("total_layer_anomalies", 0)
    # Если нет энтропий, возвращаем None
    if not layer_entropies:
        return None
    features = layer_entropies + [anomalies]
    return np.array(features)

def build_dataset(feedback_entries: List[Dict],
                  conn: sqlite3.Connection,
                  inspector: RealInspector,
                  min_stake: float = 0,
                  rating_threshold_good: int = 4,
                  rating_threshold_bad: int = 2) -> Tuple[np.ndarray, np.ndarray]:
    """
    Строит датасет на основе логов обратной связи.
    Возвращает (X, y), где y=1 для плохих ответов (аномалии), y=0 для хороших.
    """
    X_list = []
    y_list = []
    skipped_low_stake = 0
    skipped_no_features = 0
    skipped_invalid_rating = 0

    total = len(feedback_entries)
    for entry in feedback_entries:
        rating = entry.get("rating")
        stake = entry.get("balance", 0)  # баланс на момент фидбека
        if rating is None:
            skipped_invalid_rating += 1
            continue

        # Фильтр по стейку
        if stake < min_stake:
            skipped_low_stake += 1
            continue

        # Определяем метку
        if rating <= rating_threshold_bad:
            label = 1
        elif rating >= rating_threshold_good:
            label = 0
        else:
            continue

        # Пытаемся получить признаки
        features = None

        # 1. Сначала ищем активации в БД
        block_id = entry.get("block_id")
        if block_id:
            activations = get_activations_from_db(conn, block_id)
            if activations:
                features = extract_features_from_activations(activations, inspector)

        # 2. Если активаций нет, используем спектральные метрики из лога
        if features is None:
            spectral_metrics = entry.get("spectral_metrics")
            if spectral_metrics:
                features = extract_features_from_spectral_metrics(spectral_metrics)
                # Если извлекли признаки, теперь нужно настроить inspector (сохранить размерность)
                if features is not None:
                    # Для спектральных метрик размерность: количество слоёв + 1 (total_anomalies)
                    # Устанавливаем num_layers как количество энтропий, но для инспектора используем фиктивную размерность
                    # Можно задать feature_dim = len(features)
                    inspector.feature_dim = len(features)
                    inspector.num_layers = len(features) - 1
                    inspector._is_fitted = True  # помечаем, чтобы не было ошибок

        if features is None:
            skipped_no_features += 1
            continue

        X_list.append(features)
        y_list.append(label)

    logger.info(f"Обработано записей: {total}, "
                f"пропущено по низкому стейку: {skipped_low_stake}, "
                f"невалидный рейтинг: {skipped_invalid_rating}, "
                f"нет признаков: {skipped_no_features}, "
                f"использовано для обучения: {len(X_list)}")
    if len(X_list) == 0:
        return np.array([]), np.array([])
    X = np.vstack(X_list)
    y = np.array(y_list)
    return X, y

# ========== ОСНОВНАЯ ФУНКЦИЯ ==========
def main():
    parser = argparse.ArgumentParser(description="Дообучение инспектора на основе обратной связи")
    parser.add_argument("--feedback-log", type=str, default="feedback_log.json",
                        help="Путь к файлу с логами обратной связи (JSON Lines)")
    parser.add_argument("--db", type=str, default="activations.db",
                        help="Путь к SQLite базе данных с активациями")
    parser.add_argument("--model-path", type=str, default="inspector_model.pkl",
                        help="Путь к файлу модели (будет обновлён)")
    parser.add_argument("--scaler-path", type=str, default="inspector_scaler.pkl",
                        help="Путь к файлу скейлера (будет обновлён)")
    parser.add_argument("--min-stake", type=float, default=0,
                        help="Минимальный баланс (стейк) пользователя для учёта фидбека")
    parser.add_argument("--threshold", type=int, default=10,
                        help="Минимальное количество примеров для дообучения")
    parser.add_argument("--rating-good", type=int, default=4,
                        help="Оценка, считающаяся 'хорошей' (метка 0)")
    parser.add_argument("--rating-bad", type=int, default=2,
                        help="Оценка, считающаяся 'плохой' (метка 1)")
    args = parser.parse_args()

    # Инициализация БД
    conn = init_activations_db(args.db)

    # Загружаем инспектор (с автообучением, чтобы он был инициализирован)
    inspector = RealInspector(
        model_path=args.model_path,
        scaler_path=args.scaler_path,
        auto_train=True
    )

    # Загружаем логи фидбека
    feedback_entries = load_feedback_log(args.feedback_log)
    if not feedback_entries:
        logger.info("Нет записей обратной связи, выход.")
        return

    # Строим датасет с фильтрацией по стейку и использованием БД / спектральных метрик
    X, y = build_dataset(
        feedback_entries,
        conn,
        inspector,
        min_stake=args.min_stake,
        rating_threshold_good=args.rating_good,
        rating_threshold_bad=args.rating_bad
    )

    if len(X) < args.threshold:
        logger.info(f"Недостаточно данных (найдено {len(X)}, требуется минимум {args.threshold}). Пропускаем дообучение.")
        return

    # Дообучаем модель
    inspector.retrain(X, y)
    inspector.save(args.model_path, args.scaler_path)
    logger.info("Дообучение завершено, модель сохранена.")
    conn.close()

if __name__ == "__main__":
    main()
