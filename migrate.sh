#!/usr/bin/env bash
# ==============================================================================
# migrate.sh - Lanzador universal para el asistente de migración en Python
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${SCRIPT_DIR}/migrate.py" "$@"
