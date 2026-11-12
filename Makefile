# Ramp developer entry points. `make help` lists targets.
.PHONY: help setup browsers up up-core down logs test test-all lint format eval audit mcp fetch-bad reproduce-bad eval-smoke benchmark ci

UV ?= uv
RUN = $(UV) run
COMPOSE = docker compose

help:  ## List targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

setup:  ## Install the pinned environment, browsers, and git pre-commit hooks
	$(UV) sync --all-groups
	$(RUN) pre-commit install
	$(MAKE) browsers

browsers:  ## Install Chromium for Playwright and the Node axe reference runner
	$(RUN) playwright install chromium
	cd benchmark/reference && npm ci && npx playwright install chromium

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

eval:  ## Run the full benchmark for SYSTEM (default axe-baseline) into evals/results/
	$(RUN) python -m ramp.evals.runner --system $(or $(SYSTEM),axe-baseline) --subset full

eval-smoke:  ## Fast benchmark subset (what CI runs)
	$(RUN) python -m ramp.evals.runner --system $(or $(SYSTEM),axe-baseline) --subset smoke

benchmark:  ## Regenerate synthetic/adversarial pages, labels, and the label JSON Schema
	$(RUN) python benchmark/build_benchmark.py

audit:  ## Audit a URL: make audit URL=https://example.org
	$(RUN) ramp audit "$(URL)"

mcp:  ## Run the ramp-a11y-mcp server over stdio
	$(RUN) ramp mcp-server

fetch-bad:  ## Download the W3C BAD demo pages (polite, robots-aware) into benchmark/bad/site
	$(RUN) python benchmark/bad/fetch_bad.py

reproduce-bad:  ## Phase 1 acceptance: Ramp vs @axe-core/playwright on W3C BAD, exact match
	$(RUN) python -m ramp.evals.reproduce_bad

ci: lint test  ## What CI runs
