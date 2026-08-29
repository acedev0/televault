#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${TELEVAULT_DATA_DIR:-$PROJECT_DIR/data}"
VENV_DIR="${TELEVAULT_VENV_DIR:-$PROJECT_DIR/.venv}"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  python3 -m venv "$VENV_DIR"
  "$VENV_DIR/bin/python" -m pip install --upgrade pip wheel
  "$VENV_DIR/bin/python" -m pip install -r "$PROJECT_DIR/requirements.txt"
fi
if [[ ! -f "$DATA_DIR/secrets.enc" ]]; then
  "$VENV_DIR/bin/python" -m televault --data-dir "$DATA_DIR" setup
fi
PORT="$(awk -F= '$1 == "TELEVAULT_PORT" { print $2 }' "$DATA_DIR/runtime.env" | tail -n 1 | tr -d '[:space:]')"
export TELEVAULT_DATA_DIR="$DATA_DIR"
exec "$VENV_DIR/bin/uvicorn" televault.app:create_app --factory --host 0.0.0.0 --port "${PORT:-8181}" --workers 1 --no-proxy-headers

