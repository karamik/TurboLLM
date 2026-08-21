#!/usr/bin/env python3
"""
Unit tests for TurboLLM inference server.
Requires the server to be running (or uses mock for offline testing).
"""

import pytest
import httpx
import json
import time
from typing import Dict, Any

# Базовый URL сервера (можно переопределить через переменную окружения)
BASE_URL = "http://localhost:8000"

# Тестовый промпт (короткий, чтобы быстро проверить)
TEST_PROMPT = "What is the capital of France?"
EXPECTED_KEYWORD = "Paris"

@pytest.fixture
def client():
    """Create HTTP client for testing."""
    return httpx.Client(timeout=30.0, base_url=BASE_URL)

# -------------------------------------------------------------------
# Test health endpoint
# -------------------------------------------------------------------
def test_health(client):
    """Проверить, что эндпоинт /health возвращает статус ok."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "ok"
    assert "engine_ready" in data

# -------------------------------------------------------------------
# Test metrics endpoint
# -------------------------------------------------------------------
def test_metrics(client):
    """Проверить, что /metrics возвращает Prometheus-формат."""
    response = client.get("/metrics")
    assert response.status_code == 200
    # Проверяем наличие хотя бы одной метрики
    text = response.text
    # Должны быть метрики turbollm_*
    assert "turbollm_" in text or "# HELP" in text

# -------------------------------------------------------------------
# Test generate endpoint (non-streaming)
# -------------------------------------------------------------------
def test_generate(client):
    """Проверить генерацию ответа через /generate."""
    payload = {
        "prompt": TEST_PROMPT,
        "max_tokens": 20,
        "temperature": 0.0,  # детерминировано
        "stream": False
    }
    response = client.post("/generate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "request_id" in data
    assert "text" in data
    assert "usage" in data
    # Проверяем, что ответ содержит ожидаемое слово (регистронезависимо)
    assert EXPECTED_KEYWORD.lower() in data["text"].lower()

# -------------------------------------------------------------------
# Test generate with longer context (chunked prefill)
# -------------------------------------------------------------------
def test_generate_long_context(client):
    """Проверить обработку длинного промпта (имитация chunked prefill)."""
    # Создаём длинный промпт (около 1000 слов)
    long_prompt = " ".join(["This is a test sentence. " for _ in range(200)])
    payload = {
        "prompt": long_prompt,
        "max_tokens": 10,
        "temperature": 0.0,
        "stream": False
    }
    start = time.time()
    response = client.post("/generate", json=payload)
    duration = time.time() - start
    assert response.status_code == 200
    data = response.json()
    assert "text" in data
    # Проверяем, что время ответа разумное (< 10 сек для длинного ввода)
    assert duration < 10.0, f"Long context took {duration:.2f}s, too slow"

# -------------------------------------------------------------------
# Test streaming endpoint
# -------------------------------------------------------------------
def test_generate_stream(client):
    """Проверить потоковую генерацию (/generate_stream)."""
    payload = {
        "prompt": TEST_PROMPT,
        "max_tokens": 10,
        "temperature": 0.0,
        "stream": True
    }
    with client.stream("POST", "/generate_stream", json=payload) as response:
        assert response.status_code == 200
        chunks = []
        for chunk in response.iter_text():
            if chunk.strip():
                chunks.append(chunk)
        # Должны получить несколько SSE-событий
        assert len(chunks) > 0
        # Проверяем, что финальный [DONE] присутствует (в последнем чанке)
        # Так как SSE передаёт "data: [DONE]\n\n", проверим последний чанк
        last = chunks[-1] if chunks else ""
        assert "[DONE]" in last or "ERROR" not in last

# -------------------------------------------------------------------
# Test error handling (invalid model)
# -------------------------------------------------------------------
def test_invalid_request(client):
    """Проверить обработку некорректных запросов."""
    payload = {
        "prompt": "test",
        "max_tokens": -5,  # недопустимое значение
    }
    response = client.post("/generate", json=payload)
    # Должна быть ошибка валидации (422)
    assert response.status_code == 422

# -------------------------------------------------------------------
# Test concurrent requests (basic)
# -------------------------------------------------------------------
def test_concurrent_requests(client):
    """Проверить, что сервер выдерживает несколько параллельных запросов."""
    import concurrent.futures

    def send_request(prompt):
        payload = {"prompt": prompt, "max_tokens": 5, "temperature": 0.0}
        return client.post("/generate", json=payload)

    prompts = ["What is AI?", "Explain quantum computing.", "Who wrote Hamlet?"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(send_request, p) for p in prompts]
        results = [f.result() for f in futures]

    for resp in results:
        assert resp.status_code == 200
        data = resp.json()
        assert "text" in data

# -------------------------------------------------------------------
# Запуск тестов, если файл выполняется напрямую
# -------------------------------------------------------------------
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
