#!/usr/bin/env python3
"""
train_inspector.py - Генерация синтетического датасета активаций и обучение ML-классификатора.
"""

import os
import pickle
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

# Параметры генерации
NUM_SAMPLES = 5000
FEATURE_DIM = 12  # 4 статистики (mean, std, max, min) * 3 слоя (как в _extract_features)
NORMAL_MEAN = 0.2
NORMAL_STD = 0.1
ANOMALY_SHIFT = 0.8  # насколько отличаются аномальные активации

def generate_synthetic_data(n_samples=1000, anomaly_ratio=0.2):
    """
    Генерирует синтетические признаки активаций.
    Возвращает X (np.array) и y (np.array) метки (0 - норма, 1 - аномалия).
    """
    n_anomaly = int(n_samples * anomaly_ratio)
    n_normal = n_samples - n_anomaly

    # Нормальные образцы
    X_normal = np.random.normal(loc=NORMAL_MEAN, scale=NORMAL_STD, size=(n_normal, FEATURE_DIM))
    y_normal = np.zeros(n_normal, dtype=int)

    # Аномальные образцы (смещение по среднему и увеличение разброса)
    X_anomaly = np.random.normal(loc=NORMAL_MEAN + ANOMALY_SHIFT, scale=NORMAL_STD*1.5, size=(n_anomaly, FEATURE_DIM))
    y_anomaly = np.ones(n_anomaly, dtype=int)

    X = np.vstack([X_normal, X_anomaly])
    y = np.hstack([y_normal, y_anomaly])

    # Перемешиваем
    indices = np.random.permutation(len(X))
    return X[indices], y[indices]

def train_and_save(model_path='inspector_model.pkl', scaler_path='inspector_scaler.pkl'):
    """Генерирует данные, обучает модель и сохраняет."""
    print("Генерация синтетических данных...")
    X, y = generate_synthetic_data(NUM_SAMPLES, anomaly_ratio=0.25)

    # Разделение на обучающую и тестовую выборку
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # Стандартизация
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # Обучение логистической регрессии
    model = LogisticRegression(max_iter=1000, random_state=42)
    model.fit(X_train_scaled, y_train)

    # Оценка
    y_pred = model.predict(X_test_scaled)
    print("Classification report on test set:")
    print(classification_report(y_test, y_pred, target_names=['normal', 'anomaly']))

    # Сохранение
    with open(model_path, 'wb') as f:
        pickle.dump(model, f)
    with open(scaler_path, 'wb') as f:
        pickle.dump(scaler, f)

    print(f"Модель сохранена в {model_path}, скейлер в {scaler_path}")

if __name__ == "__main__":
    # Создаём папку для моделей, если её нет
    os.makedirs('g_inspector/models', exist_ok=True)
    train_and_save(
        model_path='g_inspector/models/inspector_model.pkl',
        scaler_path='g_inspector/models/inspector_scaler.pkl'
    )
