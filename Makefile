.PHONY: all sync test lint format format-check typecheck workflows qa coverage clean help

all: sync

sync:
	@uv sync

test:
	@uv run python -m pytest tests/ -v

lint:
	@uv run ruff check src/ tests/

format:
	@uv run ruff format src/ tests/

format-check:
	@uv run ruff format --check src/ tests/

workflows:
	@command -v actionlint >/dev/null 2>&1 && actionlint || echo "actionlint not installed; skipping (CI runs it)"

typecheck:
	@uv run mypy src/

qa: lint format-check typecheck workflows test

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
	@echo "  format-check - Check formatting without rewriting"
	@echo "  workflows - Lint GitHub Actions workflows with actionlint"
	@echo "  typecheck - Type check with mypy"
	@echo "  qa        - Full QA (lint + format-check + typecheck + workflows + test)"
	@echo "  coverage  - Run tests with coverage"
	@echo "  clean     - Remove build artifacts"
