#!/usr/bin/env bash
set -euo pipefail

# Resolve repository root (this script lives in <repo>/.cursor)
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Python's venv module needs ensurepip; install it if the base image lacks it.
if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3-venv
fi

# Backend: isolated virtualenv + pinned dependencies.
python3 -m venv .venv
# shellcheck source=/dev/null
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -r backend/requirements.txt

# Frontend: deterministic install from the committed lockfile.
npm --prefix frontend ci
