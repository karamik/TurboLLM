#!/bin/bash
# run_local.sh – Local development launcher for TurboLLM
# Usage: ./scripts/run_local.sh [--model /path/to/model] [--port 8000]

set -e

# Цветной вывод
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 TurboLLM – Local Development Launcher${NC}"

# Значения по умолчанию
MODEL_PATH=${MODEL_PATH:-"/app/model"}   # можно переопределить переменной окружения
PORT=${PORT:-8000}
HOST=${HOST:-"0.0.0.0"}
QUANTIZATION=${QUANTIZATION:-"fp8"}
KV_CACHE_DTYPE=${KV_CACHE_DTYPE:-"fp8"}
MAX_MODEL_LEN=${MAX_MODEL_LEN:-32768}

# Парсинг аргументов командной строки
while [[ $# -gt 0 ]]; do
    case $1 in
        --model)
            MODEL_PATH="$2"
            shift 2
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        --host)
            HOST="$2"
            shift 2
            ;;
        --no-quant)
            QUANTIZATION=""
            shift
            ;;
        --help)
            echo "Usage: $0 [--model /path/to/model] [--port 8000] [--host 0.0.0.0] [--no-quant]"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Проверка наличия Python и зависимостей
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python3 not found. Please install Python 3.10+.${NC}"
    exit 1
fi

# Проверка наличия CUDA
if ! command -v nvidia-smi &> /dev/null; then
    echo -e "${YELLOW}⚠️  NVIDIA drivers not detected. GPU may not be available.${NC}"
else
    echo -e "${GREEN}✅ NVIDIA GPU detected:${NC}"
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | head -1
fi

# Проверка установленных пакетов Python
if ! python3 -c "import vllm" 2>/dev/null; then
    echo -e "${YELLOW}⚠️  vLLM not found. Installing dependencies...${NC}"
    pip install -r requirements.txt
fi

# Проверка существования модели
if [ ! -d "$MODEL_PATH" ]; then
    echo -e "${YELLOW}⚠️  Model directory $MODEL_PATH does not exist.${NC}"
    echo -e "   You can download a model using: python scripts/download_model.py --model <model_name>"
    echo -e "   Or set MODEL_PATH environment variable to an existing model."
    exit 1
fi

echo -e "${GREEN}📂 Using model: $MODEL_PATH${NC}"
echo -e "${GREEN}🌐 Listening on: $HOST:$PORT${NC}"
if [ -n "$QUANTIZATION" ]; then
    echo -e "${GREEN}⚡ Quantization: $QUANTIZATION${NC}"
    echo -e "${GREEN}⚡ KV-cache dtype: $KV_CACHE_DTYPE${NC}"
else
    echo -e "${YELLOW}⚡ Quantization disabled (FP16)${NC}"
fi
echo -e "${GREEN}📏 Max context length: $MAX_MODEL_LEN${NC}"

# Запуск сервера
echo -e "${GREEN}▶️  Starting TurboLLM...${NC}"
export MODEL_PATH="$MODEL_PATH"
export PORT="$PORT"
export HOST="$HOST"
export QUANTIZATION="$QUANTIZATION"
export KV_CACHE_DTYPE="$KV_CACHE_DTYPE"
export MAX_MODEL_LEN="$MAX_MODEL_LEN"

python3 -m turbollm.serve --model "$MODEL_PATH" --port "$PORT" --host "$HOST" \
    ${QUANTIZATION:+--quantization "$QUANTIZATION"} \
    ${KV_CACHE_DTYPE:+--kv-cache-dtype "$KV_CACHE_DTYPE"} \
    --max-model-len "$MAX_MODEL_LEN"
