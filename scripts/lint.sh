#!/usr/bin/env bash

set -e
set -x

uv run mypy src tests
uv run ruff check src tests scripts
uv run ruff format src tests --check
