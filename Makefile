OS := $(shell uname -s 2>/dev/null || echo Windows_NT)

ifeq ($(OS),Windows_NT)
PYTHON_BIN ?= python
VENV_PY := .venv\Scripts\python.exe
else
PYTHON_BIN ?= python3
VENV_PY := .venv/bin/python
endif

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
