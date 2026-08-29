#!/usr/bin/env bash
set -Eeuo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"

export TELEVAULT_DATA_DIR="${TELEVAULT_DATA_DIR:-$project_dir/data}"
export TELEVAULT_VENV_DIR="${TELEVAULT_VENV_DIR:-$project_dir/.venv}"

exec bash "$project_dir/start.sh"
