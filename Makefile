PYTHON ?= python3
VENV_PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/pip
PYTEST ?= .venv/bin/pytest
COMPOSE ?= docker-compose

.PHONY: install install-extended test run-api migrate stack-up stack-down stack-logs demo

install:
	$(PYTHON) -m venv .venv
	$(PIP) install --upgrade pip setuptools wheel
	$(PIP) install -e ".[dev]" --no-build-isolation

install-extended:
	$(PYTHON) -m venv .venv
	$(PIP) install --upgrade pip setuptools wheel
	$(PIP) install -e ".[dev,extended]" --no-build-isolation

test:
	$(PYTEST)

run-api:
	$(VENV_PYTHON) -m uvicorn kfabric.api.app:app --reload

migrate:
	.venv/bin/kfabric-migrate

stack-up:
	$(COMPOSE) up -d --build

stack-down:
	$(COMPOSE) down

stack-logs:
	$(COMPOSE) logs -f api worker

demo:
	$(VENV_PYTHON) scripts/generate_demo_scenarios.py --output /tmp/kfabric-demo-manifest.json
