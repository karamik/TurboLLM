# ============================================================
# TurboLLM Makefile – удобные команды для разработки и деплоя
# ============================================================

SHELL := /bin/bash
PROJECT_NAME := turbollm
DOCKER_IMAGE := turbollm:latest
DOCKER_COMPOSE := docker-compose

# Цвета для вывода
GREEN := \033[0;32m
YELLOW := \033[1;33m
RED := \033[0;31m
NC := \033[0m # No Color

.PHONY: help
help: ## Показать справку по всем командам
	@echo -e "$(GREEN)TurboLLM – доступные команды:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-20s$(NC) %s\n", $$1, $$2}'

# -------------------- Установка и зависимости --------------------
.PHONY: install
install: ## Установить Python-зависимости локально
	@echo -e "$(GREEN)📦 Installing dependencies...$(NC)"
	pip install -r requirements.txt
	@echo -e "$(GREEN)✅ Done.$(NC)"

.PHONY: dev-install
dev-install: ## Установить зависимости для разработки (+ линтеры, тесты)
	@echo -e "$(GREEN)📦 Installing dev dependencies...$(NC)"
	pip install -r requirements.txt
	pip install pytest black flake8 mypy
	@echo -e "$(GREEN)✅ Done.$(NC)"

# -------------------- Запуск локально (без Docker) --------------------
.PHONY: run
run: ## Запустить сервер локально (использует MODEL_PATH из окружения)
	@echo -e "$(GREEN)🚀 Running TurboLLM locally...$(NC)"
	./scripts/run_local.sh

.PHONY: run-model
run-model: ## Запустить с указанием модели: make run-model MODEL=./models/llama
	@if [ -z "$(MODEL)" ]; then \
		echo -e "$(RED)❌ Please specify MODEL, e.g. make run-model MODEL=./models/llama$(NC)"; \
		exit 1; \
	fi
	@echo -e "$(GREEN)🚀 Running with model $(MODEL)...$(NC)"
	./scripts/run_local.sh --model $(MODEL)

# -------------------- Docker сборка и запуск --------------------
.PHONY: build
build: ## Собрать Docker-образ
	@echo -e "$(GREEN)🐳 Building Docker image...$(NC)"
	docker build -t $(DOCKER_IMAGE) .
	@echo -e "$(GREEN)✅ Build complete.$(NC)"

.PHONY: up
up: ## Запустить все сервисы в Docker Compose (core только)
	@echo -e "$(GREEN)🐳 Starting services...$(NC)"
	$(DOCKER_COMPOSE) up -d
	@echo -e "$(GREEN)✅ Services started.$(NC)"
	@echo -e "   API available at http://localhost:8000"

.PHONY: up-monitoring
up-monitoring: ## Запустить core + мониторинг (Prometheus, Grafana)
	@echo -e "$(GREEN)🐳 Starting services with monitoring...$(NC)"
	$(DOCKER_COMPOSE) --profile monitoring up -d
	@echo -e "$(GREEN)✅ Services started.$(NC)"
	@echo -e "   API: http://localhost:8000"
	@echo -e "   Prometheus: http://localhost:9090"
	@echo -e "   Grafana: http://localhost:3000 (admin/admin)"

.PHONY: up-enterprise
up-enterprise: ## Запустить все сервисы (core + monitoring + enterprise модули)
	@echo -e "$(GREEN)🐳 Starting all services (enterprise)...$(NC)"
	$(DOCKER_COMPOSE) --profile monitoring --profile enterprise up -d
	@echo -e "$(GREEN)✅ All services started.$(NC)"
	@echo -e "   API: http://localhost:8000"
	@echo -e "   Load Balancer: http://localhost:8080"
	@echo -e "   Dashboard: http://localhost:8081"
	@echo -e "   Prometheus: http://localhost:9090"
	@echo -e "   Grafana: http://localhost:3000 (admin/admin)"

.PHONY: down
down: ## Остановить все Docker-контейнеры
	@echo -e "$(YELLOW)⏹ Stopping services...$(NC)"
	$(DOCKER_COMPOSE) down
	@echo -e "$(GREEN)✅ Done.$(NC)"

.PHONY: logs
logs: ## Показать логи всех контейнеров
	$(DOCKER_COMPOSE) logs -f

.PHONY: ps
ps: ## Показать статус контейнеров
	$(DOCKER_COMPOSE) ps

# -------------------- Модели --------------------
.PHONY: download-model
download-model: ## Скачать модель: make download-model MODEL=meta-llama/Meta-Llama-3-70B
	@if [ -z "$(MODEL)" ]; then \
		echo -e "$(RED)❌ Please specify MODEL, e.g. make download-model MODEL=meta-llama/Meta-Llama-3-70B$(NC)"; \
		exit 1; \
	fi
	@echo -e "$(GREEN)📥 Downloading model $(MODEL)...$(NC)"
	python scripts/download_model.py --model $(MODEL) --quant fp8 --output ./models

# -------------------- Тестирование и проверка кода --------------------
.PHONY: test
test: ## Запустить тесты (pytest)
	pytest tests/ -v

.PHONY: lint
lint: ## Проверить стиль кода (black, flake8)
	black --check turbollm/ scripts/ tests/
	flake8 turbollm/ scripts/ tests/

.PHONY: format
format: ## Отформатировать код (black)
	black turbollm/ scripts/ tests/

# -------------------- Очистка --------------------
.PHONY: clean
clean: ## Удалить временные файлы, кэши, __pycache__
	@echo -e "$(YELLOW)🧹 Cleaning cache files...$(NC)"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .coverage
	@echo -e "$(GREEN)✅ Cleaned.$(NC)"

.PHONY: clean-all
clean-all: clean ## Полная очистка + удаление образов и volumes (осторожно!)
	@echo -e "$(RED)⚠️  This will remove Docker volumes and images. Continue? (y/N)$(NC)"
	@read -p "" ans; \
	if [ "$$ans" = "y" ] || [ "$$ans" = "Y" ]; then \
		$(DOCKER_COMPOSE) down -v --rmi local; \
		echo -e "$(GREEN)✅ Cleaned all.$(NC)"; \
	else \
		echo "Aborted."; \
	fi

# -------------------- Утилиты --------------------
.PHONY: shell
shell: ## Запустить интерактивную оболочку внутри контейнера inference
	$(DOCKER_COMPOSE) exec inference /bin/bash

.PHONY: status
status: ## Показать состояние сервисов
	@echo -e "$(GREEN)Service status:$(NC)"
	@curl -s http://localhost:8000/health | jq . 2>/dev/null || echo "API not responding"

# -------------------- Дефолтная цель --------------------
.DEFAULT_GOAL := help
