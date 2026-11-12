# Ramp developer entry points. `make help` lists targets.
.PHONY: help setup up up-core down logs test test-all lint format typecheck eval audit ci

UV ?= uv
RUN = $(UV) run
COMPOSE = docker compose

help:  ## List targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

setup:  ## Install the pinned environment and git pre-commit hooks
	$(UV) sync --all-groups
	$(RUN) pre-commit install

up:  ## Start the full stack (api, worker, redis, MLflow, Langfuse)
	$(COMPOSE) --profile observability up -d --build

up-core:  ## Start api, worker, redis, MLflow (no Langfuse)
	$(COMPOSE) up -d --build

down:  ## Stop the stack
	$(COMPOSE) --profile observability down

logs:  ## Tail stack logs
	$(COMPOSE) --profile observability logs -f --tail=100

test:  ## Fast unit tests (no browser, network, or LLM)
	$(RUN) pytest

test-all:  ## All tests including integration (needs Playwright browsers)
	$(RUN) pytest -m ""

lint:  ## Ruff lint + format check + mypy strict
	$(RUN) ruff check .
	$(RUN) ruff format --check .
	$(RUN) mypy

format:  ## Auto-format
	$(RUN) ruff format .
	$(RUN) ruff check --fix .

eval:  ## Run the benchmark and write evals/results (Phase 2)
	@echo "eval harness arrives in Phase 2"

audit:  ## Audit a URL: make audit URL=https://example.org
	$(RUN) ramp audit "$(URL)"

ci: lint test  ## What CI runs
