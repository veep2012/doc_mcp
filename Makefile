OS := $(shell uname -s 2>/dev/null || echo Windows_NT)

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
local-venv: ## Create local Python venv and install dependencies; activate it separately
ifeq ($(OS),Windows_NT)
	$(PYTHON_BIN) -m venv .venv
	powershell -NoProfile -ExecutionPolicy Bypass -Command "& { . .venv\Scripts\Activate.ps1; python -m pip install --upgrade pip; pip install -r requirements-dev.txt; playwright install chromium }"
else
	$(PYTHON_BIN) -m venv .venv && . .venv/bin/activate && python -m pip install --upgrade pip && pip install -r requirements-dev.txt && playwright install chromium
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
	@if [ ! -x "$(VENV_PY)" ]; then \
		echo "Create .venv first with 'make local-venv'"; \
		exit 1; \
	fi
	$(VENV_PY) -m pip install -r requirements-dev.txt
	$(VENV_PY) -m build --wheel
