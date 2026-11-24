.PHONY: dev test lint format check reset

dev:
	uv run newscout

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .

check: lint test

reset:
	rm -rf data
