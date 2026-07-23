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

# Stop any existing server on the default port so one-command restarts work cleanly.
lsof -ti tcp:8000 | xargs -r kill -9 || true

# Export .env variables into environment without executing the file as shell code.
while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in
    ""|\#*)
      continue
      ;;
  esac

  key=${line%%=*}
  value=${line#*=}

  case "$key" in
    ""|*[!A-Za-z0-9_]* )
      continue
      ;;
  esac

  export "$key=$value"
done < .env

# Start the FastAPI dev server (uvicorn) in the background so this command returns.
echo "Launching uvicorn at http://127.0.0.1:8000"
nohup .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 > server.log 2>&1 &
echo $! > server.pid
echo "Server started in the background. PID: $(cat server.pid)"
echo "Logs: $(pwd)/server.log"
