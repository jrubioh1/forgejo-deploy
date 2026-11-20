#!/usr/bin/env bash
# ==============================================================================
# scripts/tunnel-db.sh - Gestor del túnel SSH persistente para BD PostgreSQL remota
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Cargar variables de entorno
if [[ -f "${BASE_DIR}/.env" ]]; then
    # shellcheck disable=SC1091
    source "${BASE_DIR}/.env"
fi

SOCKET_PATH="/run/forgejo-db-tunnel.sock"
SSH_TUNNEL_ENABLED="${SSH_TUNNEL_ENABLED:-false}"
SSH_TUNNEL_USER="${SSH_TUNNEL_USER:-root}"
SSH_TUNNEL_HOST="${SSH_TUNNEL_HOST:-localhost}"
SSH_TUNNEL_PORT="${SSH_TUNNEL_PORT:-22}"
SSH_TUNNEL_KEY="${SSH_TUNNEL_KEY:-/root/.ssh/id_ed25519}"
SSH_TUNNEL_REMOTE_DB_HOST="${SSH_TUNNEL_REMOTE_DB_HOST:-127.0.0.1}"
SSH_TUNNEL_REMOTE_DB_PORT="${SSH_TUNNEL_REMOTE_DB_PORT:-5432}"
SSH_TUNNEL_BIND_IP="${SSH_TUNNEL_BIND_IP:-0.0.0.0}"
SSH_TUNNEL_LOCAL_PORT="${SSH_TUNNEL_LOCAL_PORT:-5432}"

is_tunnel_running() {
    if [[ -S "$SOCKET_PATH" ]]; then
        if ssh -S "$SOCKET_PATH" -O check "${SSH_TUNNEL_USER}@${SSH_TUNNEL_HOST}" >/dev/null 2>&1; then
            return 0
        fi
    fi
    return 1
}

tunnel_start() {
    if [[ "$SSH_TUNNEL_ENABLED" != "true" ]]; then
        echo "[*] Túnel SSH no habilitado en .env (SSH_TUNNEL_ENABLED=false). Saltando."
        return 0
    fi

    if is_tunnel_running; then
        echo "[+] El túnel SSH ya está activo y en ejecución (socket: $SOCKET_PATH)."
        return 0
    fi

    # Eliminar socket huérfano si existe
    rm -f "$SOCKET_PATH"

    if [[ ! -f "$SSH_TUNNEL_KEY" ]]; then
        echo "[!] Error: No se encontró la clave privada SSH en: $SSH_TUNNEL_KEY" >&2
        return 1
    fi

    echo "[*] Estableciendo túnel SSH hacia ${SSH_TUNNEL_USER}@${SSH_TUNNEL_HOST}:${SSH_TUNNEL_PORT}..."
    echo "    Mapeo: ${SSH_TUNNEL_BIND_IP}:${SSH_TUNNEL_LOCAL_PORT} -> ${SSH_TUNNEL_REMOTE_DB_HOST}:${SSH_TUNNEL_REMOTE_DB_PORT}"

    ssh -f -N -T -M \
        -S "$SOCKET_PATH" \
        -L "${SSH_TUNNEL_BIND_IP}:${SSH_TUNNEL_LOCAL_PORT}:${SSH_TUNNEL_REMOTE_DB_HOST}:${SSH_TUNNEL_REMOTE_DB_PORT}" \
        -p "${SSH_TUNNEL_PORT}" \
        -i "${SSH_TUNNEL_KEY}" \
        -o ExitOnForwardFailure=yes \
        -o ServerAliveInterval=15 \
        -o ServerAliveCountMax=3 \
        -o StrictHostKeyChecking=accept-new \
        "${SSH_TUNNEL_USER}@${SSH_TUNNEL_HOST}"

    # Esperar confirmación del socket
    local retries=10
    while [[ $retries -gt 0 ]]; do
        if is_tunnel_running; then
            echo "[+] Túnel SSH establecido con éxito."
            return 0
        fi
        sleep 0.5
        retries=$((retries - 1))
    done

    echo "[!] Error: No se pudo verificar la activación del túnel SSH." >&2
    return 1
}

tunnel_stop() {
    if [[ ! -S "$SOCKET_PATH" ]]; then
        echo "[*] El túnel SSH no está en ejecución."
        return 0
    fi

    echo "[*] Cerrando túnel SSH ordenadamente..."
    ssh -S "$SOCKET_PATH" -O exit "${SSH_TUNNEL_USER}@${SSH_TUNNEL_HOST}" >/dev/null 2>&1 || true
    rm -f "$SOCKET_PATH"
    echo "[+] Túnel SSH detenido."
}

tunnel_status() {
    if is_tunnel_running; then
        echo "[+] Estado: ACTIVO (Túnel hacia ${SSH_TUNNEL_HOST} conectado en puerto ${SSH_TUNNEL_LOCAL_PORT})."
        return 0
    else
        echo "[-] Estado: INACTIVO (El túnel SSH no se encuentra en ejecución)."
        return 1
    fi
}

case "${1:-}" in
    start)
        tunnel_start
        ;;
    stop)
        tunnel_stop
        ;;
    restart)
        tunnel_stop
        sleep 1
        tunnel_start
        ;;
    status)
        tunnel_status
        ;;
    *)
        echo "Uso: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
