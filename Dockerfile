# Используем официальный образ NVIDIA CUDA с Python
FROM nvidia/cuda:12.2.0-base-ubuntu22.04

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-pip \
    git \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Создаём ссылку python3 -> python
RUN ln -s /usr/bin/python3.10 /usr/bin/python

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем Python-пакеты (включая vLLM, torch, etc.)
RUN pip3 install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY turbollm/ ./turbollm/
COPY scripts/ ./scripts/
COPY configs/ ./configs/

# Открываем порт для API (по умолчанию 8000)
EXPOSE 8000

# Команда запуска (может быть переопределена в compose)
CMD ["python", "-m", "turbollm.serve", "--model", "/app/model", "--port", "8000"]
