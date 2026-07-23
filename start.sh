#!/usr/bin/env bash
set -euo pipefail

# Move to project root (script lives at repo root)
cd "$(dirname "$0")"

echo "Starting DocuTrust AI dev environment..."

# Create venv if missing
if [ ! -d .venv ]; then
  echo "Creating virtualenv (.venv)..."
  python3 -m venv .venv
fi

# Activate venv
# shellcheck disable=SC1091
. .venv/bin/activate

# Upgrade pip and install requirements
echo "Installing Python dependencies (this may take a minute)..."
pip install --upgrade pip >/dev/null
pip install -r requirements.txt

# Ensure .env exists
if [ ! -f .env ]; then
  echo "Creating .env from .env.example"
  cp .env.example .env
fi

# Export .env variables into environment
set -a
# shellcheck disable=SC1091
. .env
set +a

# Start the FastAPI dev server (uvicorn)
echo "Launching uvicorn at http://127.0.0.1:8000"
exec .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
