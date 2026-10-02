#!/usr/bin/env bash
set -euo pipefail

command -v python3 >/dev/null || { printf 'Python 3 is required.\n' >&2; exit 1; }
exec python3 "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/installer.py" "$@"
