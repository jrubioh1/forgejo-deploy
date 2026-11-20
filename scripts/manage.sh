#!/usr/bin/env bash
# ==============================================================================
# scripts/manage.sh - CLI de operaciones y administración de Forgejo en Gentoo
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$BASE_DIR"

if [[ -f "${BASE_DIR}/.env" ]]; then
    # shellcheck disable=SC1091
    source "${BASE_DIR}/.env"
fi

# Colores y estilos ANSI
BOLD="\033[1m"
DIM="\033[2m"
CYAN="\033[36m"
GREEN="\033[32m"
YELLOW="\033[33m"
RED="\033[31m"
MAGENTA="\033[35m"
RESET="\033[0m"

log_ok()   { echo -e " ${BOLD}${GREEN}[ ✔ ]${RESET} $*"; }
log_info() { echo -e " ${BOLD}${CYAN}[ ℹ ]${RESET} $*"; }
log_warn() { echo -e " ${BOLD}${YELLOW}[ ⚠ ]${RESET} $*"; }
log_err()  { echo -e " ${BOLD}${RED}[ ✖ ]${RESET} $*"; }

cmd_start() {
    log_info "Iniciando stack de Forgejo en Gentoo..."
    if [[ "${SSH_TUNNEL_ENABLED:-false}" == "true" ]]; then
        "${SCRIPT_DIR}/tunnel-db.sh" start
    fi
    podman-compose up -d
    log_ok "Stack levantado exitosamente."
    echo ""
    cmd_status
}

cmd_stop() {
    log_info "Deteniendo stack de Forgejo ordenadamente (timeout: 30s)..."
    podman-compose down --timeout 30
    if [[ "${SSH_TUNNEL_ENABLED:-false}" == "true" ]]; then
        "${SCRIPT_DIR}/tunnel-db.sh" stop
    fi
    log_ok "Stack detenido y recursos liberados."
}

cmd_restart() {
    cmd_stop
    sleep 1
    cmd_start
}

cmd_status() {
    echo -e "${BOLD}${CYAN}┌────────────────────────────────────────────────────────────────────────┐${RESET}"
    echo -e "${BOLD}${CYAN}│                   ESTADO DEL SERVICIO FORGEJO EN GENTOO                │${RESET}"
    echo -e "${BOLD}${CYAN}└────────────────────────────────────────────────────────────────────────┘${RESET}"
    
    echo -e "\n${BOLD}${MAGENTA}── Contenedores Podman ──────────────────────────────────────────────────${RESET}"
    podman-compose ps || true

    if [[ "${SSH_TUNNEL_ENABLED:-false}" == "true" ]]; then
        echo -e "\n${BOLD}${MAGENTA}── Túnel SSH de Base de Datos ───────────────────────────────────────────${RESET}"
        "${SCRIPT_DIR}/tunnel-db.sh" status || true
    fi

    if [[ "${DB_MODE:-local}" == "local" ]]; then
        echo -e "\n${BOLD}${MAGENTA}── Salud de PostgreSQL Local ────────────────────────────────────────────${RESET}"
        if podman ps --format "{{.Names}}" | grep -q "^forgejo-db$"; then
            if podman exec -i forgejo-db pg_isready -U "${POSTGRES_USER:-forgejo}" -d "${POSTGRES_DB:-forgejo}" >/dev/null 2>&1; then
                log_ok "PostgreSQL respondiendo y listo para conexiones."
            else
                log_warn "PostgreSQL está arrancando o no responde a pg_isready."
            fi
        else
            log_err "El contenedor forgejo-db no se encuentra en ejecución."
        fi
    else
        echo -e "\n${BOLD}${MAGENTA}── Base de Datos Externa ────────────────────────────────────────────────${RESET}"
        log_info "Modo DB_MODE=remote activo hacia: ${BOLD}${FORGEJO_DB_HOST:-desconocido}${RESET}"
    fi

    echo -e "\n${BOLD}${MAGENTA}── Comprobación de Acceso HTTP ──────────────────────────────────────────${RESET}"
    HTTP_PORT="${FORGEJO_HTTP_PORT:-3000}"
    if curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${HTTP_PORT}/" >/dev/null 2>&1; then
        HTTP_CODE="$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${HTTP_PORT}/")"
        log_ok "Forgejo respondiendo en http://127.0.0.1:${HTTP_PORT}/ (Código HTTP: ${BOLD}${GREEN}${HTTP_CODE}${RESET})"
    else
        log_warn "Forgejo aún no responde en http://127.0.0.1:${HTTP_PORT}/ (puede estar iniciando)"
    fi
    echo -e "${BOLD}${CYAN}──────────────────────────────────────────────────────────────────────────${RESET}\n"
}

cmd_logs() {
    local target="${1:-}"
    if [[ -z "$target" ]]; then
        podman-compose logs -f
    else
        podman-compose logs -f "$target"
    fi
}

cmd_backup() {
    local timestamp
    timestamp="$(date +%Y%m%d_%H%M%S)"
    local backup_dir="${BASE_DIR}/backups"
    mkdir -p "$backup_dir"

    log_info "Iniciando copia de seguridad consistente..."

    # 1. Backup de Base de Datos
    if [[ "${DB_MODE:-local}" == "local" ]]; then
        local sql_file="${backup_dir}/db-forgejo-${timestamp}.sql.gz"
        log_info "Exportando PostgreSQL hacia: ${CYAN}${sql_file}${RESET}"
        podman exec -i forgejo-db pg_dump -U "${POSTGRES_USER:-forgejo}" "${POSTGRES_DB:-forgejo}" | gzip > "$sql_file"
        log_ok "Base de datos respaldada correctamente."
    else
        log_info "DB_MODE=remote: Realiza el dump en el servidor central o vía conexión remota."
    fi

    # 2. Backup de Repositorios y Datos de Forgejo
    local data_file="${backup_dir}/data-forgejo-${timestamp}.tar.gz"
    log_info "Empaquetando repositorios hacia: ${CYAN}${data_file}${RESET}"
    tar -czf "$data_file" -C "$BASE_DIR" data/
    log_ok "Almacenamiento de Forgejo respaldado correctamente."

    echo ""
    log_ok "Respaldo finalizado en: ${backup_dir}"
    ls -lh "${backup_dir}"/*"${timestamp}"*
}

cmd_create_admin() {
    echo -e "\n${BOLD}${CYAN}┌── Creación de Administrador en Forgejo ────────────────────────────────┐${RESET}"
    read -r -p " Nombre de usuario administrador [admin]: " ADMIN_U
    ADMIN_U="${ADMIN_U:-admin}"
    read -r -p " Correo electrónico [admin@local.domain]: " ADMIN_M
    ADMIN_M="${ADMIN_M:-admin@local.domain}"
    read -r -s -p " Contraseña para el administrador: " ADMIN_P
    echo ""
    echo -e "${BOLD}${CYAN}└────────────────────────────────────────────────────────────────────────┘${RESET}"

    if [[ -z "$ADMIN_P" ]]; then
        log_err "La contraseña no puede estar vacía."
        return 1
    fi

    log_info "Creando usuario administrador dentro del contenedor..."
    podman exec -it forgejo-app forgejo admin user create \
        --admin \
        --username "$ADMIN_U" \
        --email "$ADMIN_M" \
        --password "$ADMIN_P" \
        --must-change-password=false

    log_ok "Administrador '${BOLD}${ADMIN_U}${RESET}' creado exitosamente."
}

cmd_cli() {
    podman exec -it forgejo-app forgejo "$@"
}

cmd_uninstall() {
    "${BASE_DIR}/setup.sh" --revert
}

cmd_upgrade() {
    shift || true
    python3 "${SCRIPT_DIR}/upgrade.py" "$@"
}

case "${1:-}" in
    start)
        cmd_start
        ;;
    stop)
        cmd_stop
        ;;
    restart)
        cmd_restart
        ;;
    status)
        cmd_status
        ;;
    logs)
        shift
        cmd_logs "$@"
        ;;
    backup)
        cmd_backup
        ;;
    create-admin)
        cmd_create_admin
        ;;
    cli)
        shift
        cmd_cli "$@"
        ;;
    upgrade|update)
        cmd_upgrade "$@"
        ;;
    uninstall|revert)
        cmd_uninstall
        ;;
    *)
        echo -e "${BOLD}Uso:${RESET} $0 {start|stop|restart|status|logs [server|db]|backup|create-admin|upgrade|cli <args>|uninstall}"
        exit 1
        ;;
esac
