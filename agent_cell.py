#!/usr/bin/env python3
"""
agent_cell.py - HTTP-сервис-агент для связи TurboLLM с QRAP-кластером.
"""

import os
import time
import random
import hashlib
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any

import aiohttp
from aiohttp import web
from pydantic import BaseModel, ValidationError

# === Конфигурация ===
TURBOLLM_ENDPOINT = os.getenv("TURBOLLM_ENDPOINT", "http://turbollm:8000/v1")
TURBOLLM_MODEL = os.getenv("TURBOLLM_MODEL", "meta-llama/Meta-Llama-3-70B")
TURBOLLM_API_KEY = os.getenv("TURBOLLM_API_KEY", "EMPTY")

CLUSTER_ENDPOINT = os.getenv("CLUSTER_ENDPOINT", "http://qrap-node:50051/api/v1/block")
CLUSTER_API_KEY = os.getenv("CLUSTER_API_KEY", "")  # если нужен

CELL_ID = os.getenv("CELL_ID", f"cell_{random.randint(1000, 9999)}")
N_AGENTS = int(os.getenv("N_AGENTS", "10"))

HOST = os.getenv("AGENT_HOST", "0.0.0.0")
PORT = int(os.getenv("AGENT_PORT", "8080"))


# === Pydantic-модели ===
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
    poi_chain: list[str]
    payload: Dict[str, Any]


# === Вспомогательные функции ===
async def call_turbollm(session: aiohttp.ClientSession, prompt: str) -> Dict[str, Any]:
    """Вызов TurboLLM с повторными попытками."""
    headers = {
        "Authorization": f"Bearer {TURBOLLM_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": TURBOLLM_MODEL,
        "messages": [
            {"role": "system", "content": "Ты — автономный агент. Проанализируй данные и ответь кратко: только 'A' или 'B'."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 5
    }

    for attempt in range(3):
        try:
            async with session.post(f"{TURBOLLM_ENDPOINT}/chat/completions", json=payload, headers=headers, timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    answer = data["choices"][0]["message"]["content"].strip().upper()
                    decision = "A" if "A" in answer else ("B" if "B" in answer else "A")
                    return {"decision": decision, "usage": data.get("usage", {"total_tokens": 42}), "raw": answer}
                else:
                    text = await resp.text()
                    print(f"TurboLLM error (attempt {attempt+1}): {resp.status} - {text}")
        except Exception as e:
            print(f"TurboLLM connection error (attempt {attempt+1}): {e}")
        await asyncio.sleep(2 ** attempt)  # экспоненциальная задержка

    # Fallback
    return {"decision": random.choice(["A", "B"]), "usage": {"total_tokens": 0}, "raw": "FALLBACK"}


async def generate_cell(task_prompt: str) -> CellOutput:
    """Генерация CellOutput на основе задачи."""
    async with aiohttp.ClientSession() as session:
        decisions = [random.choice(["A", "B"]) for _ in range(N_AGENTS)]
        poi_chain = []
        switch_counts = []
        max_iterations = 5
        total_tokens = 0

        for step in range(1, max_iterations + 1):
            prev_decisions = decisions.copy()
            new_decisions = []
            switches = 0

            for i in range(N_AGENTS):
                sample = random.sample([d for idx, d in enumerate(prev_decisions) if idx != i], min(3, N_AGENTS - 1))
                prompt = f"Задача: {task_prompt}\nМнения других агентов: {sample}. Каково твое решение (A или B)?"
                res = await call_turbollm(session, prompt)
                new_decisions.append(res["decision"])
                total_tokens += res["usage"].get("total_tokens", 0)
                if res["decision"] != prev_decisions[i]:
                    switches += 1

            decisions = new_decisions
            switch_counts.append(switches / N_AGENTS)

            state_str = f"{CELL_ID}:{step}:{sorted(decisions)}"
            step_hash = hashlib.sha256(state_str.encode()).hexdigest()
            poi_chain.append(step_hash)

            if decisions == prev_decisions:
                break

        count_a = decisions.count("A")
        gamma = max(count_a, N_AGENTS - count_a) / N_AGENTS
        final_decision = "A" if count_a >= N_AGENTS / 2 else "B"
        delta = sum(switch_counts) / len(switch_counts) if switch_counts else 0.0
        mu_hash = hashlib.sha256(f"turbollm_entropy_{CELL_ID}".encode()).hexdigest()[:12]
        tau_ms = int(time.time() * 1000) % 100000

        manifest = EntropyManifest(
            gamma=round(gamma, 4),
            nu=len(poi_chain),
            delta=round(delta, 4),
            mu_hash=mu_hash,
            tau_ms=tau_ms
        )

        block_id = hashlib.sha256(f"{CELL_ID}:{poi_chain[-1]}".encode()).hexdigest()[:16]

        return CellOutput(
            cell_id=CELL_ID,
            block_id=block_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            decision=final_decision,
            manifest=manifest,
            poi_chain=poi_chain,
            payload={
                "model": TURBOLLM_MODEL,
                "total_tokens_used": total_tokens,
                "agents_count": N_AGENTS,
                "task": task_prompt
            }
        )


async def send_to_cluster(session: aiohttp.ClientSession, cell_output: CellOutput) -> bool:
    """Отправка блока в QRAP с повторными попытками."""
    headers = {"Content-Type": "application/json"}
    if CLUSTER_API_KEY:
        headers["Authorization"] = f"Bearer {CLUSTER_API_KEY}"

    for attempt in range(3):
        try:
            async with session.post(CLUSTER_ENDPOINT, json=cell_output.dict(), headers=headers, timeout=30) as resp:
                if 200 <= resp.status < 300:
                    res_data = await resp.json()
                    print(f"[{CELL_ID}] Блок {cell_output.block_id} принят кластером: {res_data}")
                    return True
                else:
                    text = await resp.text()
                    print(f"Cluster error (attempt {attempt+1}): {resp.status} - {text}")
        except Exception as e:
            print(f"Cluster connection error (attempt {attempt+1}): {e}")
        await asyncio.sleep(2 ** attempt)
    return False


# === HTTP-обработчики ===
async def handle_process(request: web.Request):
    """Обработка POST /process — принять задачу, сгенерировать блок, отправить в QRAP."""
    try:
        data = await request.json()
        task = data.get("task")
        if not task:
            return web.json_response({"error": "Missing 'task' field"}, status=400)

        # Генерация CellOutput
        cell = await generate_cell(task)

        # Отправка в QRAP
        async with aiohttp.ClientSession() as session:
            success = await send_to_cluster(session, cell)

        return web.json_response({
            "status": "ok" if success else "delivery_failed",
            "cell": cell.dict(),
            "delivered": success
        }, status=200 if success else 207)

    except ValidationError as e:
        return web.json_response({"error": f"Validation error: {e}"}, status=400)
    except Exception as e:
        return web.json_response({"error": f"Internal error: {str(e)}"}, status=500)


async def handle_health(request: web.Request):
    """Healthcheck для оркестратора."""
    return web.json_response({"status": "alive", "cell_id": CELL_ID})


# === Запуск сервера ===
def main():
    app = web.Application()
    app.router.add_post("/process", handle_process)
    app.router.add_get("/health", handle_health)
    print(f"🚀 Агент {CELL_ID} запущен на http://{HOST}:{PORT}")
    print(f"   TurboLLM: {TURBOLLM_ENDPOINT}")
    print(f"   QRAP кластер: {CLUSTER_ENDPOINT}")
    web.run_app(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
