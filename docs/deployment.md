

This guide covers how to deploy TurboLLM in different environments – from a single GPU machine to a production‑grade Kubernetes cluster.

---

## 📋 Prerequisites

### Hardware
- **GPU**: NVIDIA Ada Lovelace (RTX 4090, RTX 6000 Ada), Hopper (H100), or newer with FP8 tensor core support.
- **VRAM**: 24 GB+ for 70B models with FP8 quantization.
- **CPU**: 8+ cores recommended.
- **RAM**: 32 GB+ recommended.
- **Storage**: 100 GB+ for model weights and logs.

### Software
- **OS**: Ubuntu 22.04 LTS (recommended) or similar Linux distribution.
- **NVIDIA Drivers**: 545.23.06+ (for CUDA 12.2+).
- **CUDA Toolkit**: 12.2+.
- **Docker**: 24.0+ (if using containers).
- **Kubernetes**: 1.27+ (if using Helm).

---

## 🚀 Option 1: Local Deployment (Bare Metal)

This is the simplest way to run TurboLLM directly on your machine.

### Step 1: Install System Dependencies

```bash
# Update package list
sudo apt update

# Install Python 3.10 and pip
sudo apt install -y python3.10 python3-pip

# Install NVIDIA drivers (if not already installed)
# Check current driver: nvidia-smi
# If missing, follow: https://www.nvidia.com/download/index.aspx

# Install CUDA toolkit 12.2+
# Follow instructions at: https://developer.nvidia.com/cuda-downloads
```

### Step 2: Set Up Python Environment

```bash
# Create and activate a virtual environment (optional but recommended)
python3.10 -m venv venv
source venv/bin/activate

# Install TurboLLM and dependencies
git clone https://github.com/karamik/TurboLLM.git
cd TurboLLM
pip install -r requirements.txt
```

### Step 3: Download a Model

```bash
# Download Llama-3-70B with FP8 quantization (requires Hugging Face token if gated)
python scripts/download_model.py --model meta-llama/Meta-Llama-3-70B --quant fp8 --output ./models

# Alternatively, use any HF model:
# python scripts/download_model.py --model mistralai/Mistral-7B-v0.1 --output ./models
```

### Step 4: Start the Server

```bash
# Using the convenience script
./scripts/run_local.sh --model ./models/Meta-Llama-3-70B_fp8 --port 8000

# Or directly via Python
python -m turbollm.serve --model ./models/Meta-Llama-3-70B_fp8 --port 8000 --quantization fp8 --kv-cache-dtype fp8
```

### Step 5: Test the API

```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"What is AI?","max_tokens":50}'
```

---

## 🐳 Option 2: Docker Compose Deployment

This is recommended for production on a single host with multiple containers.

### Step 1: Install Docker and NVIDIA Container Toolkit

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Install NVIDIA Container Toolkit
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt update
sudo apt install -y nvidia-container-toolkit
sudo systemctl restart docker
```

### Step 2: Prepare Model and Configurations

```bash
# Download model (as in local deployment)
python scripts/download_model.py --model meta-llama/Meta-Llama-3-70B --quant fp8 --output ./models

# (Optional) Create .env file from template
cp .env.example .env
# Edit .env with your settings
```

### Step 3: Start Services

```bash
# Start core inference only
docker-compose up -d

# Start with monitoring (Prometheus + Grafana)
docker-compose --profile monitoring up -d

# Start everything including enterprise modules
docker-compose --profile monitoring --profile enterprise up -d
```

### Step 4: Verify

```bash
# Check health
curl http://localhost:8000/health

# View logs
docker-compose logs -f inference

# Access Grafana (if monitoring enabled): http://localhost:3000 (admin/admin)
```

---

## ☸️ Option 3: Kubernetes with Helm

For scalable, cloud‑native deployments.

### Step 1: Install Kubernetes Tools

```bash
# Install kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl && sudo mv kubectl /usr/local/bin/

# Install Helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

### Step 2: Prepare Model Storage

Create a Persistent Volume for model weights. Example using NFS or cloud storage:

```yaml
# model-pvc.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: model-pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 50Gi
```

Apply:
```bash
kubectl apply -f model-pvc.yaml
```

Copy your model into the PVC (using a temporary pod or direct upload).

### Step 3: Customize Helm Values

```bash
# Copy values template
cp deploy/helm/values.yaml my-values.yaml

# Edit my-values.yaml:
# - Set inference.model.path to the PVC mount path.
# - Adjust resource limits (GPU, memory).
# - Enable monitoring/enterprise if desired.
# - Configure ingress if exposing externally.
```

### Step 4: Install the Chart

```bash
helm install turbollm ./deploy/helm -f my-values.yaml --namespace turbollm --create-namespace
```

### Step 5: Verify Deployment

```bash
kubectl get pods -n turbollm
kubectl logs -f deployment/turbollm-inference -n turbollm
```

### Step 6: Scale (if needed)

```bash
# Manual scaling
kubectl scale deployment turbollm-inference --replicas=3 -n turbollm

# Or use HPA (set autoscaling.enabled=true in values)
```

---

## 🔧 Environment Variables Reference

| Variable | Description | Default |
|----------|-------------|---------|
| `MODEL_PATH` | Path to model directory | `/app/model` |
| `PORT` | API port | `8000` |
| `HOST` | Bind host | `0.0.0.0` |
| `QUANTIZATION` | `fp8` or empty | `fp8` |
| `KV_CACHE_DTYPE` | `fp8` or `auto` | `fp8` |
| `MAX_MODEL_LEN` | Max context length | `32768` |
| `GPU_MEMORY_UTILIZATION` | GPU memory usage ratio | `0.90` |
| `LOG_LEVEL` | `DEBUG`,`INFO`,`WARNING`,`ERROR` | `INFO` |
| `ENABLE_METRICS` | Enable `/metrics` endpoint | `true` |

---

## 🧪 Testing Your Deployment

```bash
# Simple health check
curl -s http://localhost:8000/health | jq .

# Generate a response
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Hello, world!","max_tokens":20}'

# Run benchmark
./scripts/run_benchmark.sh --requests 20 --concurrency 2
```

---

## ❗ Common Issues & Troubleshooting

### "CUDA out of memory" (OOM)
- Reduce `MAX_MODEL_LEN`.
- Lower `GPU_MEMORY_UTILIZATION` to `0.80`.
- Ensure FP8 quantization is enabled.
- Use a smaller batch size: set `MAX_NUM_SEQS` lower.

### "No GPU detected"
- Check NVIDIA drivers: `nvidia-smi`.
- For Docker: ensure `--gpus all` or `runtime: nvidia` is set.
- For Kubernetes: verify `nvidia-device-plugin` is installed.

### Slow first token on long prompts
- Ensure `ENABLE_CHUNKED_PREFILL=true` (vLLM default with recent versions).
- Increase `MAX_NUM_BATCHED_TOKENS` if memory allows.

### Model download fails
- Set `HF_TOKEN` if model is gated.
- Check network connectivity.

---

## 📚 Next Steps

- Configure [enterprise modules](enterprise-modules.md) for production.
- Set up [monitoring dashboards](monitoring.md) for deeper insights.
- Tune performance using [benchmarking tools](../scripts/benchmark.py).

---

*Last updated: August 2026*
```

---

