.PHONY: all sync test lint format typecheck qa coverage clean help

all: sync

sync:
	@uv sync

test:
	@uv run python -m pytest tests/ -v

lint:
	@uv run ruff check src/ tests/

format:
	@uv run ruff format src/ tests/

typecheck:
	@uv run mypy src/

qa: lint typecheck test

coverage:
	@uv run python -m pytest tests/ -v --cov=automate --cov-report=term-missing

clean:
	@rm -rf build/ dist/ *.egg-info/ src/*.egg-info/ .pytest_cache/ .mypy_cache/ .ruff_cache/
	@find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

help:
	@echo "Available targets:"
	@echo "  sync      - Sync environment"
	@echo "  test      - Run tests"
	@echo "  lint      - Lint with ruff"
	@echo "  format    - Format with ruff"
	@echo "  typecheck - Type check with mypy"
	@echo "  qa        - Full QA (lint + typecheck + test)"
	@echo "  coverage  - Run tests with coverage"
	@echo "  clean     - Remove build artifacts"
