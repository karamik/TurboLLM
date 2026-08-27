#!/usr/bin/env python3
"""
TurboLLM Inference Server
Serves LLM requests via REST API with vLLM backend, streaming, and Prometheus metrics.
"""

import os
import argparse
import logging
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import uvicorn
import torch

# vLLM imports
from vllm.engine.arg_utils import AsyncEngineArgs
from vllm.engine.async_llm_engine import AsyncLLMEngine
from vllm.sampling_params import SamplingParams
from vllm.utils import random_uuid

# Prometheus client
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# ===================== NEW: G‑Space Inspector =====================
from g_inspector.hook_manager import HiddenStateCollector
from g_inspector.config import DEFAULT_LAYER_INDICES
# ==================================================================

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("turbollm")

# -------------------------------------------------------------------
# Prometheus metrics (monitoring)
# -------------------------------------------------------------------
REQUESTS_TOTAL = Counter("turbollm_requests_total", "Total requests", ["model", "status"])
TOKENS_TOTAL = Counter("turbollm_tokens_total", "Tokens generated", ["model"])
REQUEST_DURATION = Histogram("turbollm_request_duration_seconds", "Request duration", ["model"])
GPU_MEMORY_USED = Gauge("turbollm_gpu_memory_used_bytes", "GPU memory used")
GPU_MEMORY_TOTAL = Gauge("turbollm_gpu_memory_total_bytes", "GPU memory total")
ACTIVE_REQUESTS = Gauge("turbollm_active_requests", "Active concurrent requests")

# -------------------------------------------------------------------
# Pydantic request/response models
# -------------------------------------------------------------------
class GenerateRequest(BaseModel):
    prompt: str
    max_tokens: int = Field(256, ge=1, le=32768)
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    top_p: float = Field(0.95, ge=0.0, le=1.0)
    stream: bool = False

class GenerateResponse(BaseModel):
    request_id: str
    text: str
    usage: Dict[str, int]

# -------------------------------------------------------------------
# FastAPI app and engine lifecycle
# -------------------------------------------------------------------
app = FastAPI(title="TurboLLM Engine", version="1.0.0")

engine: Optional[AsyncLLMEngine] = None
# ===================== NEW: G‑Space Collector =====================
_hidden_collector: Optional[HiddenStateCollector] = None
# ==================================================================

def init_engine(model_path: str, **kwargs):
    """Initialize vLLM AsyncEngine with FP8 and long-context optimizations."""
    global engine

    engine_args = AsyncEngineArgs(
        model=model_path,
        tokenizer=model_path,
        dtype=kwargs.get("dtype", "float16"),
        max_model_len=kwargs.get("max_model_len", 32768),
        gpu_memory_utilization=kwargs.get("gpu_memory_utilization", 0.90),
        enforce_eager=True,
        max_num_seqs=kwargs.get("max_num_seqs", 256),
        max_num_batched_tokens=kwargs.get("max_num_batched_tokens", 8192),
        enable_chunked_prefill=True,
        quantization=kwargs.get("quantization", None),
        kv_cache_dtype=kwargs.get("kv_cache_dtype", "auto"),
        trust_remote_code=True,
    )

    logger.info(f"🚀 Initializing vLLM engine with model: {model_path}")
    logger.info(f"⚙️ Engine args: {engine_args}")

    engine = AsyncLLMEngine.from_engine_args(engine_args)
    logger.info("✅ vLLM Engine initialized successfully.")

    # ===================== NEW: Attach G‑Space Collector =====================
    _init_g_inspector()
    # ========================================================================

def _init_g_inspector():
    """Initialize the HiddenStateCollector using the loaded model."""
    global _hidden_collector
    if engine is None:
        logger.warning("Engine not initialized, cannot attach G‑Inspector.")
        return

    try:
        # Access the underlying model (vLLM 0.6+)
        # Adjust path if needed – works for most vLLM versions.
        model = engine.engine.model_executor.driver_worker.model_runner.model
        _hidden_collector = HiddenStateCollector(model, layer_indices=DEFAULT_LAYER_INDICES)
        logger.info("✅ G‑Space Inspector attached successfully.")
    except Exception as e:
        logger.error(f"❌ Failed to attach G‑Space Inspector: {e}")
        _hidden_collector = None

@app.on_event("startup")
async def startup():
    """Load model when app starts using environment variables."""
    model_path = os.environ.get("MODEL_PATH", "/app/model")
    quant = os.environ.get("QUANTIZATION") or None
    kv_cache_dtype = os.environ.get("KV_CACHE_DTYPE", "auto")
    max_model_len = int(os.environ.get("MAX_MODEL_LEN", "32768"))

    init_engine(
        model_path=model_path,
        dtype="float16",
        quantization=quant if quant != "" else None,
        kv_cache_dtype=kv_cache_dtype,
        max_model_len=max_model_len,
        gpu_memory_utilization=0.90,
    )

    # Update initial GPU metrics
    if torch.cuda.is_available():
        for i in range(torch.cuda.device_count()):
            GPU_MEMORY_TOTAL.set(torch.cuda.get_device_properties(i).total_memory)
            GPU_MEMORY_USED.set(torch.cuda.memory_reserved(i))

# -------------------------------------------------------------------
# Health & Metrics endpoints
# -------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok", "engine_ready": engine is not None}

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

# ===================== NEW: Hidden States endpoint =====================
@app.get("/hidden_states")
async def get_hidden_states():
    """
    Возвращает активации скрытых состояний (последнего запроса) и очищает буфер.
    Используется agent_cell.py для G‑Space анализа.
    """
    if _hidden_collector is None:
        raise HTTPException(status_code=503, detail="G‑Space Inspector not initialized")
    try:
        activations = _hidden_collector.get_and_clear()
        # Преобразуем тензоры в списки для JSON-сериализации
        result = {}
        for layer, tensor in activations.items():
            result[str(layer)] = tensor.tolist()
        return {"activations": result}
    except Exception as e:
        logger.exception("Error fetching hidden states")
        raise HTTPException(status_code=500, detail=str(e))
# ========================================================================

# -------------------------------------------------------------------
# Generation endpoint (non-streaming)
# -------------------------------------------------------------------
@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest):
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not ready")

    ACTIVE_REQUESTS.inc()
    request_id = random_uuid()
    timer = REQUEST_DURATION.labels(model="default").time()

    try:
        sampling_params = SamplingParams(
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            top_p=request.top_p,
        )

        output = None
        async for request_output in engine.generate(request.prompt, sampling_params, request_id):
            output = request_output

        if output is None:
            raise RuntimeError("No output generated from engine.")

        response_text = output.outputs[0].text
        prompt_tokens = len(output.prompt_token_ids)
        completion_tokens = len(output.outputs[0].token_ids)

        usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }

        REQUESTS_TOTAL.labels(model="default", status="success").inc()
        TOKENS_TOTAL.labels(model="default").inc(completion_tokens)

        return GenerateResponse(
            request_id=request_id,
            text=response_text,
            usage=usage,
        )

    except Exception as e:
        REQUESTS_TOTAL.labels(model="default", status="error").inc()
        logger.exception("Generation failed")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        timer.observe()
        ACTIVE_REQUESTS.dec()

# -------------------------------------------------------------------
# Streaming endpoint (SSE for instant first-token response)
# -------------------------------------------------------------------
@app.post("/generate_stream")
async def generate_stream(request: GenerateRequest):
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not ready")

    if not request.stream:
        return await generate(request)

    async def stream_generator():
        request_id = random_uuid()
        sampling_params = SamplingParams(
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            top_p=request.top_p,
        )

        try:
            sent_len = 0
            async for request_output in engine.generate(request.prompt, sampling_params, request_id):
                current_text = request_output.outputs[0].text
                delta = current_text[sent_len:]
                sent_len = len(current_text)
                if delta:
                    yield f"data: {delta}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: ERROR: {str(e)}\n\n"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")

# -------------------------------------------------------------------
# CLI entry point
# -------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="TurboLLM Inference Server")
    parser.add_argument("--model", type=str, default=os.environ.get("MODEL_PATH", "/app/model"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--quantization", type=str, default=os.environ.get("QUANTIZATION", ""))
    parser.add_argument("--kv-cache-dtype", type=str, default=os.environ.get("KV_CACHE_DTYPE", "auto"))
    parser.add_argument("--max-model-len", type=int, default=int(os.environ.get("MAX_MODEL_LEN", "32768")))
    args = parser.parse_args()

    os.environ["MODEL_PATH"] = args.model
    os.environ["QUANTIZATION"] = args.quantization
    os.environ["KV_CACHE_DTYPE"] = args.kv_cache_dtype
    os.environ["MAX_MODEL_LEN"] = str(args.max_model_len)

    uvicorn.run("turbollm.serve:app", host=args.host, port=args.port, reload=False)

if __name__ == "__main__":
    main()
