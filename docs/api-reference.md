


## 📁 docs/api-reference.md

```markdown
# TurboLLM API Reference

This document describes the REST API endpoints provided by TurboLLM.

**Base URL:** `http://<server>:<port>`

All endpoints accept and return JSON (except streaming, which uses Server-Sent Events).

---

## 🔹 Health Check

### `GET /health`

Returns the status of the inference engine.

**Response:**
```json
{
  "status": "ok",
  "engine_ready": true
}
```

**Status Codes:**
- `200 OK` – service is healthy.
- `503 Service Unavailable` – engine not ready.

---

## 🔹 Prometheus Metrics

### `GET /metrics`

Exposes Prometheus metrics for monitoring.

**Response:** Text/plain in Prometheus exposition format.

**Example:**
```
# HELP turbollm_requests_total Total requests
# TYPE turbollm_requests_total counter
turbollm_requests_total{model="default",status="success"} 123
```

---

## 🔹 Generate (Non‑streaming)

### `POST /generate`

Generates a complete response for a given prompt.

**Request Body:**

| Field         | Type     | Required | Description |
|---------------|----------|----------|-------------|
| `prompt`      | string   | ✅       | Input text. |
| `max_tokens`  | integer  | ❌       | Max tokens to generate. Default: `256`. Min: `1`, Max: `4096`. |
| `temperature` | float    | ❌       | Sampling temperature. Default: `0.7`. Range: `0.0`–`2.0`. |
| `top_p`       | float    | ❌       | Nucleus sampling top‑p. Default: `0.95`. |
| `stream`      | boolean  | ❌       | Must be `false` for this endpoint. |

**Example Request:**
```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "What is the capital of France?",
    "max_tokens": 50,
    "temperature": 0.7
  }'
```

**Successful Response (200 OK):**
```json
{
  "request_id": "abc123",
  "text": "The capital of France is Paris.",
  "usage": {
    "prompt_tokens": 8,
    "completion_tokens": 7,
    "total_tokens": 15
  }
}
```

**Error Responses:**
- `400 Bad Request` – invalid parameters.
- `500 Internal Server Error` – inference failure.
- `503 Service Unavailable` – engine not ready.

---

## 🔹 Generate (Streaming)

### `POST /generate_stream`

Generates a response and streams tokens as they are produced using **Server‑Sent Events (SSE)**.

**Request Body:** Same as `/generate`, but `stream` must be `true`.

**Example Request:**
```bash
curl -X POST http://localhost:8000/generate_stream \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Tell me a short joke.",
    "max_tokens": 30,
    "stream": true
  }'
```

**Response:** A stream of `data:` events.

```
data: Why
data:  do
data:  programmers
data:  prefer
data:  dark
data:  mode?
data: 
data: Because
data:  light
data:  attracts
data:  bugs.
data: [DONE]
```

**Stream Format:**
- Each token is sent as `data: <token>\n\n`.
- End of stream is signaled by `data: [DONE]\n\n`.

**Status Codes:**
- `200 OK` – streaming started (content‑type: `text/event-stream`).
- Same errors as `/generate`.

---

## 🔹 Authentication (Enterprise)

If authentication is enabled, include your API key or JWT in the `Authorization` header:

```
Authorization: Bearer <your-api-key>
```

or

```
Authorization: Bearer <jwt-token>
```

**Unauthorized Response (401):**
```json
{"detail": "Invalid or missing authentication token"}
```

---

## 📋 Error Codes

| Code | Description |
|------|-------------|
| `400` | Invalid request payload (e.g., `max_tokens` out of range). |
| `401` | Unauthorized – missing or invalid API key/JWT. |
| `403` | Forbidden – insufficient permissions or blocked by security filter. |
| `404` | Endpoint not found. |
| `422` | Validation error (e.g., wrong data types). |
| `429` | Rate limit exceeded. |
| `500` | Internal inference error. |
| `503` | Engine not ready or overloaded. |

---

## 🔧 Example Clients

### Python (requests)
```python
import requests

response = requests.post(
    "http://localhost:8000/generate",
    json={"prompt": "Hello", "max_tokens": 10}
)
print(response.json()["text"])
```

### Python (streaming with SSE)
```python
import requests

with requests.post(
    "http://localhost:8000/generate_stream",
    json={"prompt": "Tell me a story", "stream": True},
    stream=True
) as r:
    for line in r.iter_lines():
        if line:
            data = line.decode().replace("data: ", "")
            if data == "[DONE]":
                break
            print(data, end="")
```

### cURL (streaming)
```bash
curl -N -X POST http://localhost:8000/generate_stream \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Hello","stream":true}'
```

---

*Last updated: August 2026*
```

---

## 📁 docs/monitoring.md

```markdown
# Monitoring TurboLLM

This guide explains how to set up and use monitoring for TurboLLM.

---

## 📊 Metrics Available

TurboLLM exposes Prometheus metrics at `/metrics`. Key metrics:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `turbollm_requests_total` | Counter | `model`, `status` | Total requests (success/error). |
| `turbollm_tokens_total` | Counter | `model` | Total generated tokens. |
| `turbollm_request_duration_seconds` | Histogram | `model` | Request latency (seconds). |
| `turbollm_gpu_memory_used_bytes` | Gauge | – | GPU memory currently used. |
| `turbollm_gpu_memory_total_bytes` | Gauge | – | Total GPU memory. |
| `turbollm_active_requests` | Gauge | – | Concurrent in‑flight requests. |

Additional vLLM metrics are also exposed (e.g., `vllm:num_requests_running`, `vllm:gpu_cache_usage_perc`).

---

## 🚀 Setting Up Prometheus

### Option 1: Docker Compose (recommended)

Enable the `monitoring` profile (see `docker-compose.yml`):

```bash
docker-compose --profile monitoring up -d
```

This starts:
- Prometheus (port `9090`)
- Grafana (port `3000`)

Prometheus is pre‑configured to scrape TurboLLM every 15 seconds.

### Option 2: Manual Configuration

Add this job to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'turbollm'
    static_configs:
      - targets: ['<your-turbollm-host>:8000']
    metrics_path: /metrics
    scrape_interval: 15s
```

---

## 📈 Setting Up Grafana

1. Access Grafana at `http://localhost:3000` (default credentials: `admin`/`admin`).
2. Add Prometheus as a datasource (URL: `http://prometheus:9090`).
3. Import the pre‑built dashboard from `configs/grafana/dashboards/turbollm-dashboard.json` (or copy its content).
4. Explore metrics with the query builder.

### Dashboard Overview

The default dashboard includes these panels:

- **Total Requests** – success vs. error count.
- **Total Tokens Generated** – cumulative token usage.
- **GPU Memory Usage** – percentage used.
- **Active Requests** – current concurrency.
- **Request Duration** – average latency over time.
- **Request Rate** – successful vs. error requests per second.

---

## 🔔 Alerts (Alertmanager)

You can define alert rules to be notified when issues arise.

### Example Alert Rules (`alerts.yml`)

```yaml
groups:
  - name: turbollm_alerts
    interval: 30s
    rules:
      - alert: HighGPUMemory
        expr: (turbollm_gpu_memory_used_bytes / turbollm_gpu_memory_total_bytes) > 0.9
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "GPU memory usage > 90%"
          description: "GPU memory is at {{ $value | humanizePercentage }}."

      - alert: HighErrorRate
        expr: rate(turbollm_requests_total{status="error"}[5m]) > 5
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "High error rate (> 5 req/s)"
          description: "Error rate is {{ $value }} req/s."

      - alert: SlowResponse
        expr: histogram_quantile(0.95, rate(turbollm_request_duration_seconds_bucket[5m])) > 10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "95th percentile latency > 10s"
          description: "Responses are slow: {{ $value }}s."
```

Add these to your Prometheus config and configure Alertmanager to send notifications (email, Slack, Telegram).

---

## 🔍 Logging

TurboLLM logs to stdout (json format if `LOG_LEVEL=DEBUG`). For production, collect logs with:

- **Docker**: `docker logs turbollm-inference`
- **Kubernetes**: `kubectl logs <pod-name>`
- **Centralized logging**: forward to ELK/Loki stack.

---

## 📉 Monitoring GPU with DCGM (Optional)

For deeper GPU metrics (temperature, power, PCIe bandwidth), deploy the [NVIDIA DCGM Exporter](https://github.com/NVIDIA/dcgm-exporter):

```bash
docker run -d --gpus all --name dcgm-exporter \
  -p 9400:9400 \
  nvcr.io/nvidia/k8s/dcgm-exporter:latest
```

Then add it to Prometheus as a target.

---

## 📊 Query Examples

- **Average latency (last 5 minutes):**
  ```
  rate(turbollm_request_duration_seconds_sum[5m]) / rate(turbollm_request_duration_seconds_count[5m])
  ```

- **Tokens per second:**
  ```
  rate(turbollm_tokens_total[1m])
  ```

- **Error rate:**
  ```
  rate(turbollm_requests_total{status="error"}[1m])
  ```

---

*Last updated: August 2026*
```

---

## 📁 docs/performance-tuning.md

```markdown
# Performance Tuning Guide

This guide explains how to optimise TurboLLM for maximum throughput and minimal latency, especially for long‑context workloads.

---

## 🧠 Understanding the Bottlenecks

TurboLLM performance depends on:

- **GPU compute** – floating‑point operations (FP8/FP16).
- **Memory bandwidth** – especially for large models and long contexts.
- **Memory capacity** – VRAM limits batch size and context length.
- **Scheduling overhead** – batching and prefill phases.

---

## ⚡ Key Optimisations in TurboLLM

| Feature | Benefit |
|---------|---------|
| **FP8 weights** | Halves model size, increases compute throughput. |
| **FP8 KV‑cache** | Reduces memory usage for long contexts (up to 2× more context). |
| **PagedAttention** | Efficient memory management (no fragmentation). |
| **Chunked Prefill** | Fast first token even for huge prompts. |
| **Continuous Batching** | Maximises GPU utilisation by interleaving requests. |

---

## 🔧 Configuration Parameters

### Environment Variables

| Variable | Description | Recommended Value |
|----------|-------------|-------------------|
| `MAX_MODEL_LEN` | Maximum context length (tokens). | `32768` (or as high as memory allows). |
| `GPU_MEMORY_UTILIZATION` | Fraction of VRAM used by vLLM. | `0.85`–`0.90` (leave room for overhead). |
| `MAX_NUM_SEQS` | Max concurrent sequences per batch. | `256` (increase if memory permits). |
| `MAX_NUM_BATCHED_TOKENS` | Max tokens processed in a single batch step. | `8192` (higher = more throughput, but higher latency). |
| `KV_CACHE_DTYPE` | Data type for KV‑cache. | **`fp8`** (critical for long contexts). |
| `QUANTIZATION` | Weight quantization. | **`fp8`** (always use if hardware supports). |
| `ENABLE_CHUNKED_PREFILL` | Split long prompts into chunks. | **`true`** (default in vLLM 0.4+). |

---

## 📈 Tuning for Specific Use Cases

### 1. Low Latency (Interactive Chat)

- Reduce `MAX_NUM_BATCHED_TOKENS` to lower prefill time.
- Use streaming (`/generate_stream`) to show first token immediately.
- Keep `MAX_MODEL_LEN` moderate (e.g., 4096–8192).
- Use a small batch size: `MAX_NUM_SEQS = 32–64`.

### 2. High Throughput (Batch Processing)

- Increase `MAX_NUM_BATCHED_TOKENS` (up to 16384).
- Increase `GPU_MEMORY_UTILIZATION` to `0.95` (if no other workloads).
- Use large batch sizes: `MAX_NUM_SEQS = 512+`.
- Disable chunked prefill (if prompts are short).

### 3. Very Long Contexts (RAG, Document Analysis)

- Set `MAX_MODEL_LEN` to the maximum needed (e.g., 32768, 65536).
- **Must use FP8 KV‑cache** to stay within VRAM.
- Reduce `MAX_NUM_SEQS` to avoid OOM (e.g., 8–16).
- Enable chunked prefill to avoid timeouts.

### 4. Multi‑User Concurrent Load

- Use **Continuous Batching** (default in vLLM).
- Ensure `MAX_NUM_SEQS` is high enough to handle peak concurrency.
- Consider horizontal scaling (multiple replicas) with a load balancer.

---

## 🧪 Benchmarking Your Configuration

Use the provided benchmark script to measure latency and throughput:

```bash
# Run a quick test
./scripts/run_benchmark.sh --requests 100 --concurrency 10

# Test streaming performance
./scripts/run_benchmark.sh --stream --requests 50 --concurrency 5

# Long prompt test (read prompt from file)
./scripts/run_benchmark.sh --prompt-file long_prompt.txt --requests 20 --concurrency 2
```

Iterate: change parameters, run the benchmark, and compare results.

---

## 🛠️ vLLM Advanced Options

These can be set in `AsyncEngineArgs` (in `serve.py`):

- `enable_prefix_caching`: Cache KV prefixes (reduces compute for repeated prefixes). **Experimental**.
- `swap_space`: Swap memory (GB) – use if VRAM is insufficient (slows down inference).
- `max_parallel_loading_workers`: Number of workers for model loading (default=1).

**Example:**
```python
engine_args = AsyncEngineArgs(
    model=model_path,
    max_model_len=32768,
    gpu_memory_utilization=0.90,
    max_num_seqs=128,
    max_num_batched_tokens=8192,
    enable_chunked_prefill=True,
    kv_cache_dtype='fp8',
    quantization='fp8',
    enable_prefix_caching=False,
    swap_space=4,  # GB, if needed
)
```

---

## 📉 Monitoring Performance

Keep an eye on these metrics:

- **GPU memory usage** – should be stable below 95%.
- **Queue length** (`vllm:num_requests_waiting`) – if >0, increase batch size or add replicas.
- **Request latency** – watch 95th percentile.
- **KV cache usage** (`vllm:gpu_cache_usage_perc`) – ideally >80% for efficiency.

---

## 🚀 Hardware Recommendations

| Model Size | Minimum VRAM | Recommended VRAM | GPUs |
|------------|--------------|------------------|------|
| 7B (FP8)   | 8 GB         | 16 GB            | RTX 4070+ |
| 13B (FP8)  | 16 GB        | 24 GB            | RTX 4090 |
| 70B (FP8)  | 40 GB        | 80 GB            | A100/H100 |

For 70B with FP8 and long contexts, multiple GPUs may be needed (tensor parallelism).

---

## 📚 Further Reading

- [vLLM Performance Tuning](https://vllm.readthedocs.io/en/latest/serving/tuning.html)
- [NVIDIA FP8 Guide](https://docs.nvidia.com/deeplearning/transformer-engine/user-guide/examples/fp8_primer.html)
- [PagedAttention Paper](https://arxiv.org/abs/2309.06180)

---

*Last updated: August 2026*
```
