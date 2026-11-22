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

# Deletes every source, news item and setting.
reset:
	rm -rf data
