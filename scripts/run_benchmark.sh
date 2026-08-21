#!/bin/bash
# run_benchmark.sh – Quick benchmark launcher for TurboLLM
# Usage: ./scripts/run_benchmark.sh [--stream] [--requests N] [--concurrency C]

set -e

# Цвета
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${GREEN}📊 TurboLLM Benchmark Suite${NC}"

# Значения по умолчанию
URL=${URL:-"http://localhost:8000"}
REQUESTS=${REQUESTS:-50}
CONCURRENCY=${CONCURRENCY:-5}
MAX_TOKENS=${MAX_TOKENS:-50}
STREAM=""
PROMPT_FILE=""
PROMPT_TEXT=""

# Парсинг аргументов
while [[ $# -gt 0 ]]; do
    case $1 in
        --stream)
            STREAM="--stream"
            shift
            ;;
        --requests)
            REQUESTS="$2"
            shift 2
            ;;
        --concurrency)
            CONCURRENCY="$2"
            shift 2
            ;;
        --max-tokens)
            MAX_TOKENS="$2"
            shift 2
            ;;
        --url)
            URL="$2"
            shift 2
            ;;
        --prompt)
            PROMPT_TEXT="$2"
            shift 2
            ;;
        --prompt-file)
            PROMPT_FILE="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --stream              Use streaming API"
            echo "  --requests N          Number of requests (default: 50)"
            echo "  --concurrency C       Concurrent workers (default: 5)"
            echo "  --max-tokens N        Max tokens per request (default: 50)"
            echo "  --url URL             API base URL (default: http://localhost:8000)"
            echo "  --prompt TEXT         Custom prompt text"
            echo "  --prompt-file FILE    Read prompt from file"
            echo "  --help                Show this help"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Определяем промпт
if [ -n "$PROMPT_FILE" ] && [ -f "$PROMPT_FILE" ]; then
    PROMPT_TEXT=$(cat "$PROMPT_FILE")
elif [ -z "$PROMPT_TEXT" ]; then
    # Промпт по умолчанию
    PROMPT_TEXT="Explain the theory of relativity in simple terms."
fi

echo -e "${YELLOW}⚙️  Configuration:${NC}"
echo "  URL: $URL"
echo "  Requests: $REQUESTS"
echo "  Concurrency: $CONCURRENCY"
echo "  Max tokens: $MAX_TOKENS"
echo "  Streaming: ${STREAM:-no}"
echo "  Prompt: ${PROMPT_TEXT:0:60}..."
echo

# Создаём временный файл для результатов
RESULT_FILE="/tmp/benchmark_result_$$.txt"

# Запускаем бенчмарк
echo -e "${BLUE}▶️  Starting benchmark...${NC}"
python3 scripts/benchmark.py \
    --url "$URL" \
    --requests "$REQUESTS" \
    --concurrency "$CONCURRENCY" \
    --max-tokens "$MAX_TOKENS" \
    --prompt "$PROMPT_TEXT" \
    $STREAM \
    2>&1 | tee "$RESULT_FILE"

# Извлекаем ключевые метрики и сохраняем в лог
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_DIR="./benchmark_logs"
mkdir -p "$LOG_DIR"
cp "$RESULT_FILE" "$LOG_DIR/benchmark_${TIMESTAMP}.log"

echo -e "\n${GREEN}✅ Benchmark complete. Log saved to: ${LOG_DIR}/benchmark_${TIMESTAMP}.log${NC}"

# Показываем краткую сводку
echo -e "\n${YELLOW}📈 Quick summary:${NC}"
grep -E "(Throughput|Total time|Requests|Tokens per request)" "$RESULT_FILE" || true

# Удаляем временный файл
rm -f "$RESULT_FILE"
