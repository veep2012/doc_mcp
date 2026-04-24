OS := $(shell uname -s 2>/dev/null || echo Windows_NT)
CODEX_BUNDLED_PYTHON ?= /Users/alekseikrutskikh/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3

.DEFAULT_GOAL := help

ifeq ($(OS),Windows_NT)
PYTHON_BIN ?= python
VENV_PY := .venv\Scripts\python.exe
else
PYTHON_BIN ?= python3
VENV_PY := .venv/bin/python
endif

.PHONY: help
help: ## Show available make targets
	@awk 'BEGIN {FS = ":.*## "}; /^[a-zA-Z0-9_.-]+:.*## / {printf "%-14s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

.PHONY: local-venv
local-venv: ## Create a local Python venv and install project dependencies
ifeq ($(OS),Windows_NT)
	$(PYTHON_BIN) -m venv .venv
	powershell -NoProfile -ExecutionPolicy Bypass -Command "& { . .venv\Scripts\Activate.ps1; python -m pip install --upgrade pip; pip install -r requirements.txt -r requirements-dev.txt; playwright install chromium }"
else
	$(PYTHON_BIN) -m venv .venv && . .venv/bin/activate && python -m pip install --upgrade pip && pip install -r requirements.txt -r requirements-dev.txt && playwright install chromium
endif

.PHONY: audit
audit: ## Run dependency vulnerability audit against project requirements
ifneq (,$(wildcard .venv))
	$(VENV_PY) -m pip_audit -r requirements.txt
else
	$(PYTHON_BIN) -m pip_audit -r requirements.txt
endif

.PHONY: wheel
wheel: ## Build a distributable wheel into dist/
ifneq (,$(wildcard .venv))
	@if $(VENV_PY) -c "import setuptools" >/dev/null 2>&1; then \
		$(VENV_PY) -m pip wheel . -w dist --no-deps --no-build-isolation; \
	elif [ -x "$(CODEX_BUNDLED_PYTHON)" ]; then \
		$(CODEX_BUNDLED_PYTHON) -m pip wheel . -w dist --no-deps --no-build-isolation; \
	else \
		$(PYTHON_BIN) -m pip wheel . -w dist --no-deps; \
	fi
else
	$(PYTHON_BIN) -m pip wheel . -w dist --no-deps
endif
