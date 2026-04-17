#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-MyFaceclone.settings}"

python -m uvicorn MyFaceclone.asgi:application --host 0.0.0.0 --port 8000 --workers 1
