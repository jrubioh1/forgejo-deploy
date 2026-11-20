#!/usr/bin/env bash
# ==============================================================================
# scripts/manage.sh - Wrapper de compatibilidad para manage.py
# ==============================================================================
set -euo pipefail

TARGET="${BASH_SOURCE[0]}"
while [ -L "$TARGET" ]; do
    DIR="$(cd -P "$(dirname "$TARGET")" && pwd)"
    TARGET="$(readlink "$TARGET")"
    [[ $TARGET != /* ]] && TARGET="$DIR/$TARGET"
done
DIR="$(cd -P "$(dirname "$TARGET")" && pwd)"

# Si el script está en scripts/, BASE_DIR es el padre. Si está en la raíz, es DIR.
if [ -f "${DIR}/manage.py" ]; then
    MANAGE_PY="${DIR}/manage.py"
elif [ -f "${DIR}/../manage.py" ]; then
    MANAGE_PY="${DIR}/../manage.py"
else
    echo "Error: manage.py no encontrado." >&2
    exit 1
fi

exec python3 "${MANAGE_PY}" "$@"
