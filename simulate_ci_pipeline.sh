#!/usr/bin/env bash
# simulate_ci_pipeline.sh — Run the same checks as .github/workflows/ci.yml locally
set -euo pipefail

echo "=== CI Pipeline Simulation ==="
echo ""

echo "[1/3] Lint with ruff..."
uv run ruff check bookmark_tools tests

echo ""
echo "[2/3] Check formatting with ruff..."
uv run ruff format --check bookmark_tools tests

echo ""
echo "[3/3] Run tests..."
uv run pytest tests/ -v

echo ""
echo "=== All checks passed ==="
