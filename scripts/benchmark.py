#!/usr/bin/env python3
"""
Benchmark script for TurboLLM.
Measures latency, throughput, and memory usage.
Usage:
    python scripts/benchmark.py --url http://localhost:8000 --prompt "Hello" --requests 100 --concurrency 10
"""

import argparse
import time
import statistics
import threading
import concurrent.futures
from typing import List, Dict, Any
import httpx
import json
import sys
import os

# -------------------------------------------------------------------
# Конфигурация
# -------------------------------------------------------------------
DEFAULT_URL = "http://localhost:8000"
DEFAULT_PROMPT = "What is the capital of France? Explain briefly."
DEFAULT_MAX_TOKENS = 50
DEFAULT_REQUESTS = 100
DEFAULT_CONCURRENCY = 10
DEFAULT_TIMEOUT = 60

# -------------------------------------------------------------------
# Вспомогательные функции
# -------------------------------------------------------------------
def format_duration(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.2f} ms"
    return f"{seconds:.3f} s"

def print_stats(title: str, values: List[float], unit: str = "s"):
    if not values:
        print(f"{title}: no data")
        return
    avg = statistics.mean(values)
    median = statistics.median(values)
    p95 = statistics.quantiles(values, n=20)[-1] if len(values) >= 20 else max(values)
    p99 = statistics.quantiles(values, n=100)[-1] if len(values) >= 100 else max(values)
    print(f"{title}:")
    print(f"  count   : {len(values)}")
    print(f"  min     : {format_duration(min(values))}")
    print(f"  max     : {format_duration(max(values))}")
    print(f"  avg     : {format_duration(avg)}")
    print(f"  median  : {format_duration(median)}")
    print(f"  95th    : {format_duration(p95)}")
    print(f"  99th    : {format_duration(p99)}")

# -------------------------------------------------------------------
# Основной бенчмарк
# -------------------------------------------------------------------
def run_benchmark(
    url: str,
    prompt: str,
    max_tokens: int,
    requests: int,
    concurrency: int,
    timeout: int,
    stream: bool = False,
):
    print(f"🚀 Benchmarking {url}")
    print(f"   Prompt: '{prompt[:60]}...'")
    print(f"   Max tokens: {max_tokens}")
    print(f"   Requests: {requests}")
    print(f"   Concurrency: {concurrency}")
    print(f"   Streaming: {stream}")
    print()

    endpoint = "/generate_stream" if stream else "/generate"
    full_url = url + endpoint

    # Подготовка payload
    payload = {
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": 0.7,
        "stream": stream,
    }

    # Для синхронного режима используем httpx.Client, для асинхронного – не нужно.
    # Будем использовать синхронный подход с пулом потоков.

    # Список для хранения задержек
    latencies: List[float] = []
    errors = 0
    total_tokens = 0

    # Функция для одного запроса
    def send_request():
        nonlocal errors, total_tokens
        start = time.perf_counter()
        try:
            with httpx.Client(timeout=timeout) as client:
                if stream:
                    # Для стриминга нужно накапливать токены
                    response = client.post(full_url, json=payload)
                    response.raise_for_status()
                    # Стриминг: читаем чанки
                    token_count = 0
                    for line in response.iter_lines():
                        if line.startswith(b"data: "):
                            data = line[6:].decode().strip()
                            if data == "[DONE]":
                                break
                            token_count += 1
                    # Считаем токены
                    total_tokens += token_count
                else:
                    response = client.post(full_url, json=payload)
                    response.raise_for_status()
                    data = response.json()
                    if "usage" in data:
                        total_tokens += data["usage"].get("completion_tokens", 0)
                    elif "text" in data:
                        total_tokens += len(data["text"].split())  # грубо
            end = time.perf_counter()
            latencies.append(end - start)
        except Exception as e:
            errors += 1
            # print(f"  Error: {e}")

    # Исполняем запросы параллельно
    print(f"⏳ Sending {requests} requests with {concurrency} workers...")
    start_total = time.perf_counter()

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(send_request) for _ in range(requests)]
        # Ждём завершения с прогресс-баром (опционально)
        done = 0
        for f in concurrent.futures.as_completed(futures):
            done += 1
            if done % max(1, requests // 20) == 0:
                print(f"   Progress: {done}/{requests} requests completed", end="\r")
        print()

    end_total = time.perf_counter()
    total_duration = end_total - start_total

    # Результаты
    print("\n📊 Results:")
    print(f"  Total time        : {format_duration(total_duration)}")
    print(f"  Requests          : {len(latencies)} successful, {errors} errors")
    print(f"  Total tokens      : {total_tokens}")
    if total_duration > 0:
        print(f"  Throughput (req/s): {len(latencies) / total_duration:.2f}")
        print(f"  Throughput (tok/s): {total_tokens / total_duration:.2f}")
        print(f"  Tokens per request: {total_tokens / max(1, len(latencies)):.2f}")

    if latencies:
        print()
        print_stats("Latency", latencies, "s")

    # Дополнительно: использование GPU памяти (если есть nvidia-smi)
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            lines = result.stdout.strip().splitlines()
            print("\n💾 GPU Memory (nvidia-smi):")
            for i, line in enumerate(lines):
                used, total = line.split(",")
                print(f"  GPU {i}: {used.strip()} / {total.strip()}")
    except FileNotFoundError:
        pass  # nvidia-smi не найден

# -------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Benchmark TurboLLM inference")
    parser.add_argument("--url", type=str, default=DEFAULT_URL,
                        help="Base URL of TurboLLM API")
    parser.add_argument("--prompt", type=str, default=DEFAULT_PROMPT,
                        help="Prompt text")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS,
                        help="Maximum tokens to generate")
    parser.add_argument("--requests", type=int, default=DEFAULT_REQUESTS,
                        help="Number of requests")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY,
                        help="Number of concurrent workers")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                        help="Timeout per request (seconds)")
    parser.add_argument("--stream", action="store_true",
                        help="Use streaming API")
    args = parser.parse_args()

    run_benchmark(
        url=args.url,
        prompt=args.prompt,
        max_tokens=args.max_tokens,
        requests=args.requests,
        concurrency=args.concurrency,
        timeout=args.timeout,
        stream=args.stream,
    )

if __name__ == "__main__":
    main()
