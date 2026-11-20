#!/usr/bin/env bash
# ==============================================================================
# setup.sh - Lanzador universal para el instalador visual en Python
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${SCRIPT_DIR}/setup.py" "$@"
