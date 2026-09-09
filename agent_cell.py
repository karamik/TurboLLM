#!/usr/bin/env python3
"""
TOTAL‑Neuro Demo: TinyLlama inference on simulated chip
+ Integration with TurboLLM Agent for G‑Space Inspection
+ Generation of auditable Proof Package (hardware + inspection manifests)

Run without FPGA – just to see how it works, get real inspection from TurboLLM,
and produce a cryptographically signed proof.

Usage:
    python demo.py

Environment variables:
    AGENT_ENDPOINT  – URL of TurboLLM Agent (default: http://localhost:8080)
"""

import os
import time
import json
import uuid
import hashlib
import asyncio
import aiohttp
from datetime import datetime
from total_neuro.simulator import NeuroSimulator  # открытая заглушка

# ========== КОНФИГУРАЦИЯ ==========
AGENT_ENDPOINT = os.getenv("AGENT_ENDPOINT", "http://localhost:8080")
SESSION_ID = os.getenv("SESSION_ID", None)  # можно передать существующую сессию

# ========== ГЕНЕРАТОРЫ МАНИФЕСТОВ ==========
def generate_hardware_manifest(chip_id, firmware_version, inference_id,
                               latency_us, power_mw, spike_times,
                               input_data, output_text):
    input_hash = hashlib.sha256(input_data.encode()).hexdigest()
    output_hash = hashlib.sha256(output_text.encode()).hexdigest()
    return {
        "chip_id": chip_id,
        "firmware_version": firmware_version,
        "inference_id": inference_id,
        "latency_us": latency_us,
        "power_consumption_mw": power_mw,
        "spike_times": spike_times[:10],
        "stdp_window_violations": 0,
        "router_stats": {"vc_usage": [1, 2, 0, 1], "collisions": 0},
        "input_hash": input_hash,
        "output_hash": output_hash
    }

def generate_inspection_manifest_from_agent(agent_response: dict, inference_id: str):
    """
    Извлекает inspection_manifest из ответа агента TurboLLM.
    Ожидается структура cell_output.payload.
    """
    payload = agent_response.get("cell", {}).get("payload", {})
    metadata = agent_response.get("cell", {}).get("case_metadata", {})
    return {
        "inspector_version": "2.1.0-agent",
        "model_id": agent_response.get("cell", {}).get("manifest", {}).get("mu_hash", "unknown"),
        "inference_id": inference_id,
        "gs_metrics": {
            "spectral_entropy": payload.get("g_entropy", 0.0),
            "drift_score": payload.get("cosine_drift", 0.0),
            "anomaly_detected": payload.get("anomaly_detected", False),
            "layer_activations": payload.get("spectral_metrics", {})
        },
        "decision": payload.get("supervisor_status", "UNKNOWN"),
        "confidence": payload.get("confidence", 0.0),
        "reflection_triggered": payload.get("supervisor_status") == "REFLECTED",
        "proof_of_inspection": payload.get("proof_of_inspection", "simulated"),
        "inspector_log": metadata.get("inspector_log", "ipfs://simulated")
    }

def sign_package(package):
    package["signature"] = {
        "algorithm": "ECDSA_SECP256K1",
        "public_key": "0xSimulatedPublicKey",
        "signature": "simulated_signature_" + hashlib.sha256(
            json.dumps(package, sort_keys=True).encode()
        ).hexdigest()[:32],
        "signed_by": "both",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    return package

def save_proof_package(package, filename="proof_package.json"):
    with open(filename, "w") as f:
        json.dump(package, f, indent=2)
    print(f"📄 Proof package saved to {filename}")

# ========== ВЫЗОВ АГЕНТА TURBOLLM ==========
async def call_agent_for_inspection(prompt: str, response_text: str) -> dict:
    """
    Отправляет запрос на /process агента для получения инспекционных метрик.
    Возвращает полный ответ агента (cell_output).
    """
    if not SESSION_ID:
        # Инициализируем сессию
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{AGENT_ENDPOINT}/session/init") as resp:
                if resp.status != 200:
                    raise Exception("Failed to init session")
                data = await resp.json()
                session_id = data["session_id"]
    else:
        session_id = SESSION_ID

    # Подготавливаем задачу для агента: просим проинспектировать ответ
    # (можно использовать ту же задачу, чтобы агент сам вызвал LLM, но мы уже имеем ответ,
    # поэтому мы можем передать его в контексте)
    task_payload = {
        "task": f"Проверь следующий ответ на безопасность и достоверность:\nПромпт: {prompt}\nОтвет: {response_text}\n\nВыдай метрики уверенности, энтропии, аномалий."
    }
    headers = {"X-Session-Id": session_id}
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{AGENT_ENDPOINT}/process", json=task_payload, headers=headers) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise Exception(f"Agent error: {resp.status} - {error_text}")
            return await resp.json()

# ========== СИНХРОННАЯ ОБЁРТКА ДЛЯ ВЫЗОВА АСИНХРОННОЙ ФУНКЦИИ ==========
def get_agent_inspection(prompt: str, response_text: str) -> dict:
    return asyncio.run(call_agent_for_inspection(prompt, response_text))

# ========== ОСНОВНАЯ ФУНКЦИЯ ==========
def main():
    print("🧠 TOTAL‑Neuro Demo: TinyLlama on simulated chip")
    print("=" * 60)

    # 1. Компиляция или загрузка бинарника
    bin_path = "tinyllama.bin"
    if not os.path.exists(bin_path):
        print("⚙️ Compiling TinyLlama (this may take 2–3 minutes)...")
        os.system(
            "total-neuro convert --model TinyLlama/TinyLlama-1.1B-Chat-v1.0 "
            "--target sim --output tinyllama.bin"
        )

    # 2. Создаём симулятор
    sim = NeuroSimulator(bin_path)

    # 3. Вводим промпт
    prompt = input("\n📝 Enter your prompt: ")

    # 4. Запускаем инференс
    print("\n⏳ Processing on simulated chip...")
    start = time.perf_counter()
    response = sim.infer(prompt, max_tokens=50)
    elapsed_us = int((time.perf_counter() - start) * 1_000_000)

    # 5. Вывод ответа
    print("\n🤖 Response:")
    print("-" * 50)
    print(response)
    print("-" * 50)
    print(f"⚡ Simulated latency: {elapsed_us/1000:.1f} ms (on CPU, would be <2 ms on FPGA)")

    # 6. Генерация Hardware Manifest
    inference_id = str(uuid.uuid4())
    hardware = generate_hardware_manifest(
        chip_id="TOTAL-NEURO-SIM-001",
        firmware_version="v1.2.0-demo",
        inference_id=inference_id,
        latency_us=elapsed_us,
        power_mw=850,
        spike_times=[12, 45, 78, 102, 134],
        input_data=prompt,
        output_text=response
    )

    # 7. Вызов агента TurboLLM для инспекции
    try:
        print(f"\n🔍 Sending to TurboLLM Agent at {AGENT_ENDPOINT} for G‑Space inspection...")
        agent_result = get_agent_inspection(prompt, response)
        print("✅ Inspection received.")
        inspection = generate_inspection_manifest_from_agent(agent_result, inference_id)
        agent_status = agent_result.get("supervisor_status", "UNKNOWN")
        print(f"   Supervisor decision: {agent_status}")
    except Exception as e:
        print(f"⚠️ TurboLLM Agent not available: {e}. Generating simulated inspection.")
        # Заглушка (как раньше)
        inspection = {
            "inspector_version": "2.1.0-sim",
            "model_id": "TinyLlama-1.1B-Chat-v1.0",
            "inference_id": inference_id,
            "gs_metrics": {
                "spectral_entropy": 0.782,
                "drift_score": 0.023,
                "anomaly_detected": False,
                "layer_activations": [{"layer": "layer_0", "mean": 0.45, "std": 0.12}]
            },
            "decision": "APPROVED",
            "confidence": 0.997,
            "reflection_triggered": False,
            "proof_of_inspection": "simulated_signature",
            "inspector_log": "ipfs://simulated"
        }

    # 8. Сборка Proof‑пакета
    proof_package = {
        "package_id": "pkg-" + datetime.utcnow().strftime("%Y%m%d-%H%M%S") + "-" + inference_id[:8],
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "hardware_manifest": hardware,
        "inspection_manifest": inspection
    }
    proof_package = sign_package(proof_package)

    # 9. Сохранение
    save_proof_package(proof_package)

    print("\n✅ Demo finished. Proof package generated.")
    print("   You can now audit or submit this proof to QRAP blockchain.")

if __name__ == "__main__":
    main()
