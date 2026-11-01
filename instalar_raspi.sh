#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Falta Python 3. Instálalo con: sudo apt install python3 python3-venv" >&2
  exit 1
fi
exec python3 -m scripts.instalar_raspi "$@"
