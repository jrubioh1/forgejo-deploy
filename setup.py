#!/usr/bin/env python3
"""
setup.py - Asistente de Instalación y Despliegue de Forgejo en Gentoo Linux.
           Forgejo Deployment & Setup Assistant for Gentoo Linux.

Soporte Bilingüe / Bilingual Support: Español & English.
Cero dependencias externas / Zero third-party dependencies (Pure Python 3).
Incluye soporte de desescalado a Podman Rootless, detección dinámica de versiones,
selección de puertos/bind IPs para Forgejo y PostgreSQL, y reversión.
"""

from __future__ import annotations

import getpass
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Importar helper de versiones rootless
BASE_DIR_PATH = Path(__file__).resolve().parent
SCRIPTS_DIR_PATH = BASE_DIR_PATH / "scripts"
if str(SCRIPTS_DIR_PATH) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR_PATH))

from forgejo_version import (
    DEFAULT_FALLBACK_TAG,
    ensure_rootless_tag,
    fetch_available_rootless_versions,
)

# ==============================================================================
# DICCIONARIO DE INTERNACIONALIZACIÓN (I18N) / LOCALIZATION STRINGS
# ==============================================================================
STRINGS: Dict[str, Dict[str, str]] = {
    "es": {
        "banner_title": "FORGEJO & POSTGRESQL - INSTALADOR GENTOO",
        "banner_sub": "Despliegue de Infraestructura y Configuración de Producción",
        "deps_ok": "Dependencias verificadas: {deps}",
        "deps_err": "Faltan dependencias en Gentoo: {missing}",
        "deps_hint": "Instálalas en Portage ejecutando:",
        "root_ok": "Ejecución como root detectada ({user}:0). Podman operará con privilegios completos.",
        "user_info": "Ejecución como usuario no-root: {user} (UID: {uid}, GID: {gid})",
        "subuid_ok": "Asignaciones en /etc/subuid y /etc/subgid verificadas correctamente.",
        "subuid_warn": "No se encontraron rangos en /etc/subuid o /etc/subgid para {user}.",
        "subuid_hint": "Para Podman rootless, añade: {user}:100000:65536 a ambos ficheros.",
        "dirs_ok": "Directorios persistentes configurados con permisos seguros (0700).",
        "selinux_ok": "Contextos SELinux (container_file_t) aplicados.",
        "env_exists": "Ya existe un archivo .env en: {path}",
        "env_overwrite": "¿Deseas reconfigurar y sobrescribir el archivo .env existente? [s/N]",
        "env_kept": "Configuración existente conservada sin modificaciones.",
        "step_web_title": "Red, Puertos y Acceso Web de Forgejo",
        "step_web_opt1": "Acceso Directo por Puerto (Escucha en 0.0.0.0, sin intermediarios)",
        "step_web_opt2": "Subdominio con Apache Reverse Proxy (Escucha en 127.0.0.1, Apache gestiona dominio y SSL)",
        "prompt_web_choice": "Selecciona opción [1/2]",
        "prompt_http_port": "Puerto HTTP de Forgejo",
        "prompt_http_bind": "IP de enlace para HTTP (ej. 0.0.0.0 o 127.0.0.1)",
        "prompt_ssh_port": "Puerto SSH Git para Forgejo",
        "prompt_ssh_bind": "IP de enlace para SSH Git",
        "prompt_domain": "Introduce el dominio público de Forgejo",
        "prompt_host": "Introduce la IP o hostname del servidor",
        "port_privileged_warn": "Aviso: El puerto {port} es < 1024. En modo Rootless puede requerir sysctl net.ipv4.ip_unprivileged_port_start.",
        "port_invalid": "Puerto no válido. Utilizando valor predeterminado: {default}",
        "desc_direct": "Acceso Directo ({url})",
        "desc_apache": "Subdominio Apache ({url})",
        "step_db_title": "Base de Datos PostgreSQL (Puertos y Conexión)",
        "step_db_opt1": "Local en Contenedor (PostgreSQL 18 en este servidor)",
        "step_db_opt2": "Host / Túnel SSH Existente (PostgreSQL ya disponible en host.containers.internal:5432)",
        "step_db_opt3": "Remota en otro servidor (Conectar por IP directa o crear un túnel SSH nuevo)",
        "prompt_db_choice": "Selecciona opción [1/2/3]",
        "prompt_pg_port": "Puerto de PostgreSQL en el host (ej. 5432 o 5433 si 5432 está ocupado)",
        "prompt_pg_bind": "IP de enlace para PostgreSQL en el host",
        "prompt_db_name": "Nombre de la base de datos",
        "prompt_db_user": "Usuario de la base de datos",
        "prompt_db_pass": "Contraseña de la base de datos",
        "prompt_db_host": "Host y puerto de la BD remota",
        "prompt_tunnel_create": "¿Deseas crear un nuevo túnel SSH gestionado por este stack? [s/N]",
        "prompt_ssh_user": "Usuario SSH remoto",
        "prompt_ssh_host": "Host SSH remoto",
        "prompt_ssh_key": "Ruta a la clave privada SSH",
        "desc_db_local": "Contenedor PostgreSQL 18 Local (puerto host: {port})",
        "desc_db_host": "Host local / Túnel SSH existente (host.containers.internal:5432)",
        "desc_db_remote_direct": "Remota directa ({host})",
        "desc_db_remote_tunnel": "Remota por túnel nuevo ({user}@{host})",
        "step_ver_title": "Versión de Forgejo (100% Rootless Obligatorio)",
        "ver_checking": "Consultando versiones estables en tiempo real desde Codeberg...",
        "ver_opt_latest": "Última versión estable fijada: {tag} [Recomendado]",
        "ver_opt_stream": "Canal continuo de versión: {tag} (recibe parches automáticos)",
        "ver_opt_custom": "Especificar otra versión personalizada (se auto-completará con -rootless)",
        "prompt_ver_choice": "Selecciona opción de versión [1/2/3]",
        "prompt_ver_custom": "Introduce el tag de versión",
        "ver_desc_latest": "Estable fijada ({tag})",
        "ver_desc_stream": "Canal continuo ({tag})",
        "ver_desc_custom": "Personalizada ({tag})",
        "env_saved": "Archivo .env generado y protegido con permisos 0600.",
        "prompt_openrc": "¿Deseas instalar el servicio OpenRC para arranque del sistema ahora? [S/n]",
        "openrc_user_title": "Seguridad y Usuario del Servicio (Podman Rootless)",
        "openrc_user_opt1": "Crear usuario de sistema dedicado sin login ('forgejo') [Recomendado]",
        "openrc_user_opt2": "Usar un usuario existente del sistema (ej. {user})",
        "openrc_user_choice": "Selecciona opción de usuario [1/2]",
        "openrc_user_input": "Nombre de usuario del sistema",
        "user_created": "Usuario de sistema '{user}' creado exitosamente (home: {home}, shell: /sbin/nologin).",
        "subuid_assigned": "Rangos subordinate UID/GID ({range}) configurados en /etc/subuid y /etc/subgid.",
        "openrc_ok": "Servicio OpenRC instalado exitosamente en /etc/init.d/forgejo.",
        "confd_ok": "Configuración del servicio generada en /etc/conf.d/forgejo (FORGEJO_USER={user}).",
        "openrc_runlevel_prompt": "¿Deseas habilitar el servicio en el arranque del sistema (rc-update add forgejo default)? [s/N]",
        "openrc_runlevel_ok": "Servicio 'forgejo' añadido al runlevel default de OpenRC.",
        "openrc_warn": "Se requieren privilegios de root para escribir en /etc/init.d/ y /etc/conf.d/.",
        "card_title": "RESUMEN DE LA CONFIGURACIÓN APLICADA",
        "row_web": "Modo de Acceso",
        "row_http_port": "Puerto HTTP",
        "row_ssh_port": "Puerto SSH Git",
        "row_db": "Base de Datos",
        "row_pg_port": "Puerto PostgreSQL",
        "row_version": "Versión Forgejo",
        "row_container": "Contenedor Local",
        "row_tunnel": "Túnel SSH",
        "row_user": "Usuario Servicio",
        "row_env": "Archivo .env",
        "status_active": "ACTIVO",
        "status_inactive": "INACTIVO (Ahorro de recursos)",
        "status_not_needed": "NO REQUERIDO",
        "footer_cmds": "Comandos de gestión listos para usar:",
        "footer_start": "Iniciar servicio:",
        "footer_status": "Ver estado:",
        "footer_logs": "Ver registros:",
        "footer_admin": "Crear admin:",
        "footer_upgrade": "Actualizar versión:",
        "footer_uninstall": "Desinstalar o revertir:",
        "footer_migrate": "Para importar datos desde plataformas externas, ejecuta:",
        # Reversión / Rollback
        "revert_banner": "DESINSTALACIÓN Y REVERSIÓN DE FORGEJO (OPENRC)",
        "revert_confirm": "¿Estás seguro de que deseas desinstalar el servicio OpenRC y revertir las modificaciones? [s/N]",
        "revert_stopping": "Deteniendo servicio OpenRC 'forgejo'...",
        "revert_runlevel": "Eliminando servicio 'forgejo' de los niveles de arranque OpenRC...",
        "revert_files": "Eliminando /etc/init.d/forgejo y /etc/conf.d/forgejo...",
        "revert_user_prompt": "¿Deseas eliminar el usuario de sistema '{user}' y purgar sus entradas en subuid/subgid? [s/N]",
        "revert_user_del": "Eliminando usuario '{user}' y limpiando /etc/subuid y /etc/subgid...",
        "revert_data_notice": "AVISO: Los repositorios en ./data, base de datos en ./postgres y .env se han CONSERVADO por seguridad.",
        "revert_done": "Reversión completada con éxito. El sistema ha vuelto a su estado previo.",
        "revert_cancelled": "Operación de reversión cancelada por el usuario.",
    },
    "en": {
        "banner_title": "FORGEJO & POSTGRESQL - GENTOO INSTALLER",
        "banner_sub": "Infrastructure Deployment & Production Setup",
        "deps_ok": "Verified dependencies: {deps}",
        "deps_err": "Missing dependencies in Gentoo: {missing}",
        "deps_hint": "Install them via Portage by running:",
        "root_ok": "Root execution detected ({user}:0). Podman will operate with full container privileges.",
        "user_info": "Running as non-root user: {user} (UID: {uid}, GID: {gid})",
        "subuid_ok": "Assignments in /etc/subuid and /etc/subgid verified successfully.",
        "subuid_warn": "No ranges found in /etc/subuid or /etc/subgid for {user}.",
        "subuid_hint": "For rootless Podman, add: {user}:100000:65536 to both files.",
        "dirs_ok": "Persistent directories created with secure permissions (0700).",
        "selinux_ok": "SELinux contexts (container_file_t) applied.",
        "env_exists": "A .env file already exists at: {path}",
        "env_overwrite": "Do you want to reconfigure and overwrite the existing .env file? [y/N]",
        "env_kept": "Existing configuration preserved without changes.",
        "step_web_title": "Forgejo Network, Ports & Web Access",
        "step_web_opt1": "Direct Port Access (Listening on 0.0.0.0, standalone)",
        "step_web_opt2": "Subdomain with Apache Reverse Proxy (Listening on 127.0.0.1, Apache handles domain & SSL)",
        "prompt_web_choice": "Select option [1/2]",
        "prompt_http_port": "Forgejo HTTP port",
        "prompt_http_bind": "HTTP bind IP (e.g. 0.0.0.0 or 127.0.0.1)",
        "prompt_ssh_port": "Forgejo Git SSH port",
        "prompt_ssh_bind": "Git SSH bind IP",
        "prompt_domain": "Enter the public domain for Forgejo",
        "prompt_host": "Enter server IP or hostname",
        "port_privileged_warn": "Warning: Port {port} is < 1024. In Rootless mode it may require sysctl net.ipv4.ip_unprivileged_port_start.",
        "port_invalid": "Invalid port. Using default: {default}",
        "desc_direct": "Direct Port Access ({url})",
        "desc_apache": "Apache Subdomain ({url})",
        "step_db_title": "PostgreSQL Database (Ports & Connection)",
        "step_db_opt1": "Local in Container (PostgreSQL 18 on this server)",
        "step_db_opt2": "Host / Existing SSH Tunnel (PostgreSQL already available on host.containers.internal:5432)",
        "step_db_opt3": "Remote on another server (Connect via direct network IP or create a new SSH tunnel)",
        "prompt_db_choice": "Select option [1/2/3]",
        "prompt_pg_port": "PostgreSQL host port (e.g. 5432 or 5433 if 5432 is in use)",
        "prompt_pg_bind": "PostgreSQL host bind IP",
        "prompt_db_name": "Database name",
        "prompt_db_user": "Database user",
        "prompt_db_pass": "Database password",
        "prompt_db_host": "Remote DB host and port",
        "prompt_tunnel_create": "Do you want to create a new SSH tunnel managed by this stack? [y/N]",
        "prompt_ssh_user": "Remote SSH user",
        "prompt_ssh_host": "Remote SSH host",
        "prompt_ssh_key": "Path to private SSH key",
        "desc_db_local": "Local PostgreSQL 18 Container (host port: {port})",
        "desc_db_host": "Host local / Existing SSH tunnel (host.containers.internal:5432)",
        "desc_db_remote_direct": "Remote direct ({host})",
        "desc_db_remote_tunnel": "Remote via new SSH tunnel ({user}@{host})",
        "step_ver_title": "Forgejo Version (100% Rootless Mandatory)",
        "ver_checking": "Checking stable releases in real-time from Codeberg...",
        "ver_opt_latest": "Latest pinned stable release: {tag} [Recommended]",
        "ver_opt_stream": "Rolling version stream: {tag} (automatic patch updates)",
        "ver_opt_custom": "Specify custom version (will auto-append -rootless)",
        "prompt_ver_choice": "Select version option [1/2/3]",
        "prompt_ver_custom": "Enter version tag",
        "ver_desc_latest": "Pinned stable ({tag})",
        "ver_desc_stream": "Rolling stream ({tag})",
        "ver_desc_custom": "Custom ({tag})",
        "env_saved": ".env file created and secured with 0600 permissions.",
        "prompt_openrc": "Do you want to install OpenRC service for system boot now? [Y/n]",
        "openrc_user_title": "Security & Service User (Rootless Podman)",
        "openrc_user_opt1": "Create dedicated system user without login ('forgejo') [Recommended]",
        "openrc_user_opt2": "Use an existing system user (e.g. {user})",
        "openrc_user_choice": "Select user option [1/2]",
        "openrc_user_input": "System username",
        "user_created": "System user '{user}' created successfully (home: {home}, shell: /sbin/nologin).",
        "subuid_assigned": "Subordinate UID/GID ranges ({range}) configured in /etc/subuid and /etc/subgid.",
        "openrc_ok": "OpenRC service successfully installed in /etc/init.d/forgejo.",
        "confd_ok": "Service configuration generated in /etc/conf.d/forgejo (FORGEJO_USER={user}).",
        "openrc_runlevel_prompt": "Do you want to enable service on system boot (rc-update add forgejo default)? [y/N]",
        "openrc_runlevel_ok": "Service 'forgejo' added to OpenRC default runlevel.",
        "openrc_warn": "Root privileges required to write to /etc/init.d/ and /etc/conf.d/.",
        "card_title": "CONFIGURATION SUMMARY",
        "row_web": "Access Mode",
        "row_http_port": "HTTP Port",
        "row_ssh_port": "Git SSH Port",
        "row_db": "Database",
        "row_pg_port": "PostgreSQL Port",
        "row_version": "Forgejo Version",
        "row_container": "Local Container",
        "row_tunnel": "SSH Tunnel",
        "row_user": "Service User",
        "row_env": ".env File",
        "status_active": "ACTIVE",
        "status_inactive": "INACTIVE (Resource saving)",
        "status_not_needed": "NOT REQUIRED",
        "footer_cmds": "Management commands ready to use:",
        "footer_start": "Start service:",
        "footer_status": "Check status:",
        "footer_logs": "View logs:",
        "footer_admin": "Create admin:",
        "footer_upgrade": "Upgrade version:",
        "footer_uninstall": "Uninstall or revert:",
        "footer_migrate": "To import data from external platforms, run:",
        # Reversal / Rollback
        "revert_banner": "FORGEJO OPENRC UNINSTALLATION & REVERSAL",
        "revert_confirm": "Are you sure you want to uninstall OpenRC service and revert system modifications? [y/N]",
        "revert_stopping": "Stopping OpenRC service 'forgejo'...",
        "revert_runlevel": "Removing 'forgejo' service from OpenRC runlevels...",
        "revert_files": "Removing /etc/init.d/forgejo and /etc/conf.d/forgejo...",
        "revert_user_prompt": "Do you want to delete system user '{user}' and purge its subuid/subgid entries? [y/N]",
        "revert_user_del": "Deleting user '{user}' and cleaning /etc/subuid and /etc/subgid...",
        "revert_data_notice": "NOTICE: Repositories in ./data, database in ./postgres and .env have been PRESERVED for safety.",
        "revert_done": "Reversal completed successfully. The system has returned to its previous state.",
        "revert_cancelled": "Reversal operation cancelled by user.",
    },
}


class UI:
    """Terminal styling and internationalized output helper."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    MAGENTA = "\033[35m"

    lang: str = "es"

    @classmethod
    def t(cls, key: str, **kwargs) -> str:
        text = STRINGS.get(cls.lang, STRINGS["es"]).get(key, key)
        return text.format(**kwargs) if kwargs else text

    @classmethod
    def banner(cls, title: str, subtitle: str = "") -> None:
        width = 74
        print(f"\n{cls.BOLD}{cls.CYAN}┌{'─' * (width - 2)}┐{cls.RESET}")
        print(f"{cls.BOLD}{cls.CYAN}│{title.center(width - 2)}│{cls.RESET}")
        if subtitle:
            print(f"{cls.DIM}{cls.CYAN}│{subtitle.center(width - 2)}│{cls.RESET}")
        print(f"{cls.BOLD}{cls.CYAN}└{'─' * (width - 2)}┘{cls.RESET}\n")

    @classmethod
    def section(cls, step: str, title: str) -> None:
        header = f"[{step}] {title}"
        pad = max(2, 68 - len(header))
        print(f"\n{cls.BOLD}{cls.MAGENTA}┌── {header} {'─' * pad}┐{cls.RESET}")

    @classmethod
    def end_section(cls) -> None:
        print(f"{cls.BOLD}{cls.MAGENTA}└{'─' * 72}┘{cls.RESET}")

    @classmethod
    def card(cls, title: str, rows: List[Tuple[str, str]]) -> None:
        width = 74
        print(f"\n{cls.BOLD}{cls.GREEN}┌── {title} {'─' * (width - len(title) - 6)}┐{cls.RESET}")
        for label, val in rows:
            formatted_label = f"  {label}:".ljust(22)
            print(f"{cls.BOLD}{cls.GREEN}│{cls.RESET} {cls.BOLD}{formatted_label}{cls.RESET} {cls.CYAN}{val}{cls.RESET}".ljust(width + 15) + f"{cls.BOLD}{cls.GREEN}│{cls.RESET}")
        print(f"{cls.BOLD}{cls.GREEN}└{'─' * (width - 2)}┘{cls.RESET}\n")

    @classmethod
    def ok(cls, msg: str) -> None:
        print(f" {cls.BOLD}{cls.GREEN}[ ✔ ]{cls.RESET} {msg}")

    @classmethod
    def info(cls, msg: str) -> None:
        print(f" {cls.BOLD}{cls.CYAN}[ ℹ ]{cls.RESET} {msg}")

    @classmethod
    def warn(cls, msg: str) -> None:
        print(f" {cls.BOLD}{cls.YELLOW}[ ⚠ ]{cls.RESET} {msg}")

    @classmethod
    def err(cls, msg: str) -> None:
        print(f" {cls.BOLD}{cls.RED}[ ✖ ]{cls.RESET} {msg}")

    @classmethod
    def prompt(cls, text: str, default: str = "") -> str:
        prompt_str = f" {cls.BOLD}{cls.YELLOW}?{cls.RESET} {text}"
        if default:
            prompt_str += f" {cls.DIM}[{default}]{cls.RESET}"
        prompt_str += ": "
        try:
            val = input(prompt_str).strip()
            return val if val else default
        except (EOFError, KeyboardInterrupt):
            print("")
            return default

    @classmethod
    def prompt_password(cls, text: str, default: str = "") -> str:
        prompt_str = f" {cls.BOLD}{cls.YELLOW}?{cls.RESET} {text}"
        if default:
            prompt_str += f" {cls.DIM}[auto-generate]{cls.RESET}" if cls.lang == "en" else f" {cls.DIM}[generar aleatoria]{cls.RESET}"
        prompt_str += ": "
        try:
            val = getpass.getpass(prompt_str).strip()
            return val if val else default
        except (EOFError, KeyboardInterrupt):
            print("")
            return default


def select_language() -> str:
    """Permite seleccionar el idioma interactivo o vía flag --lang."""
    for arg in sys.argv[1:]:
        if arg in ("--lang=es", "--es"):
            return "es"
        if arg in ("--lang=en", "--en"):
            return "en"

    print("\nSelect Language / Selecciona Idioma:")
    print("  1) Español [Predeterminado]")
    print("  2) English")
    choice = input("  Choice / Opción [1/2]: ").strip()
    return "en" if choice == "2" else "es"


def _prompt_port(prompt_text: str, default: int) -> int:
    """Solicita un puerto, lo valida en el rango 1-65535 y advierte si < 1024."""
    val_str = UI.prompt(prompt_text, default=str(default))
    try:
        port = int(val_str)
        if 1 <= port <= 65535:
            if port < 1024:
                UI.warn(UI.t("port_privileged_warn", port=port))
            return port
    except ValueError:
        pass
    UI.warn(UI.t("port_invalid", default=default))
    return default


def _run_privileged(cmd: List[str]) -> bool:
    """Ejecuta un comando con privilegios elevados (directo si es root o vía sudo)."""
    try:
        if os.getuid() == 0:
            res = subprocess.run(cmd, check=True, capture_output=True, text=True)
        elif shutil.which("sudo"):
            res = subprocess.run(["sudo"] + cmd, check=True, capture_output=True, text=True)
        else:
            return False
        return res.returncode == 0
    except Exception:
        return False


def _ensure_subids(username: str) -> bool:
    """Verifica y añade rangos subordinate UID/GID en /etc/subuid y /etc/subgid si no existen."""
    files = ["/etc/subuid", "/etc/subgid"]
    allocated = False
    range_str = ""

    for file_path_str in files:
        path = Path(file_path_str)
        if not path.exists():
            continue

        try:
            content = path.read_text(encoding="utf-8")
            has_user = any(line.strip().startswith(f"{username}:") for line in content.splitlines())
            if not has_user:
                next_start = 200000
                for line in content.splitlines():
                    parts = line.strip().split(":")
                    if len(parts) >= 3 and parts[1].isdigit() and parts[2].isdigit():
                        end_val = int(parts[1]) + int(parts[2])
                        if end_val > next_start:
                            next_start = end_val

                subid_line = f"{username}:{next_start}:65536"
                range_str = f"{next_start}-{next_start + 65535}"
                cmd = ["sh", "-c", f"printf '%s\\n' '{subid_line}' >> '{file_path_str}'"]
                if _run_privileged(cmd):
                    allocated = True
        except Exception:
            pass

    if allocated and range_str:
        UI.ok(UI.t("subuid_assigned", range=range_str))
    return True


def _create_system_user(username: str = "forgejo") -> bool:
    """Crea un usuario de sistema dedicado sin shell interactiva para Podman rootless."""
    check = subprocess.run(["id", username], capture_output=True, text=True)
    home_dir = f"/var/lib/{username}"

    if check.returncode == 0:
        _ensure_subids(username)
        return True

    cmd = [
        "useradd",
        "-r",
        "-m",
        "-d", home_dir,
        "-s", "/sbin/nologin",
        "-c", "Forgejo Podman Git Service",
        username,
    ]
    if _run_privileged(cmd):
        UI.ok(UI.t("user_created", user=username, home=home_dir))
        _ensure_subids(username)
        return True
    return False


def check_dependencies() -> None:
    required = ["podman", "git", "openssl"]
    missing = [cmd for cmd in required if not shutil.which(cmd)]

    has_compose = shutil.which("podman-compose") or shutil.which("docker-compose")
    if not has_compose:
        missing.append("podman-compose")

    if missing:
        UI.err(UI.t("deps_err", missing=", ".join(missing)))
        UI.info(UI.t("deps_hint"))
        print(f"   {UI.BOLD}emerge --ask app-containers/podman app-containers/podman-compose dev-vcs/git{UI.RESET}\n")
        sys.exit(1)

    all_deps = required + ["podman-compose"]
    UI.ok(UI.t("deps_ok", deps=", ".join(all_deps)))


def check_user_and_permissions(base_dir: Path) -> Tuple[int, int, str]:
    caller_user = os.environ.get("SUDO_USER") or getpass.getuser()
    uid = os.getuid()
    gid = os.getgid()

    if uid == 0:
        if caller_user and caller_user != "root":
            try:
                import pwd
                pw = pwd.getpwnam(caller_user)
                uid, gid = pw.pw_uid, pw.pw_gid
                userns_mode = "keep-id"
                UI.info(UI.t("user_info", user=caller_user, uid=uid, gid=gid))
            except Exception:
                userns_mode = "keep-id"
                UI.ok(UI.t("root_ok", user="root"))
        else:
            userns_mode = "keep-id"
            UI.ok(UI.t("root_ok", user="root"))
    else:
        userns_mode = "keep-id"
        UI.info(UI.t("user_info", user=caller_user, uid=uid, gid=gid))

    for folder in ["data", "postgres"]:
        d = base_dir / folder
        d.mkdir(parents=True, exist_ok=True)
        try:
            d.chmod(0o700)
        except OSError:
            pass
    UI.ok(UI.t("dirs_ok"))

    if shutil.which("chcon"):
        for folder in ["data", "postgres"]:
            try:
                subprocess.run(["chcon", "-R", "-t", "container_file_t", str(base_dir / folder)], capture_output=True, check=False)
            except Exception:
                pass
        UI.ok(UI.t("selinux_ok"))

    return uid, gid, userns_mode


def configure_web_access() -> Tuple[str, int, str, int, str, str, str]:
    """Configura el modo de acceso, IP de enlace y puertos para HTTP y SSH Git."""
    UI.section(UI.t("step_web_title"), "1/3")
    print(f" {UI.CYAN}1){UI.RESET} {UI.BOLD}{UI.t('step_web_opt1')}{UI.RESET}")
    print(f" {UI.CYAN}2){UI.RESET} {UI.BOLD}{UI.t('step_web_opt2')}{UI.RESET}")
    UI.end_section()

    choice = UI.prompt(UI.t("prompt_web_choice"), default="1")

    # Puertos e IPs de bind
    if choice == "2":
        default_http_bind = "127.0.0.1"
        domain = UI.prompt(UI.t("prompt_domain"), default="git.tudominio.com")
        http_port = _prompt_port(UI.t("prompt_http_port"), default=3000)
        bind_ip = UI.prompt(UI.t("prompt_http_bind"), default=default_http_bind)
        ssh_port = _prompt_port(UI.t("prompt_ssh_port"), default=2222)
        ssh_bind_ip = UI.prompt(UI.t("prompt_ssh_bind"), default="0.0.0.0")

        root_url = f"https://{domain}/"
        mode_str = UI.t("desc_apache", url=root_url)
    else:
        default_http_bind = "0.0.0.0"
        domain = UI.prompt(UI.t("prompt_host"), default="localhost")
        http_port = _prompt_port(UI.t("prompt_http_port"), default=3000)
        bind_ip = UI.prompt(UI.t("prompt_http_bind"), default=default_http_bind)
        ssh_port = _prompt_port(UI.t("prompt_ssh_port"), default=2222)
        ssh_bind_ip = UI.prompt(UI.t("prompt_ssh_bind"), default="0.0.0.0")

        port_suffix = f":{http_port}" if http_port != 80 else ""
        root_url = f"http://{domain}{port_suffix}/"
        mode_str = UI.t("desc_direct", url=root_url)

    return bind_ip, http_port, ssh_bind_ip, ssh_port, domain, root_url, mode_str


def configure_database() -> Tuple[str, str, str, str, str, str, str, int, bool, str, str, str, str]:
    """Configura la conexión a base de datos y puertos de enlace para PostgreSQL."""
    UI.section(UI.t("step_db_title"), "2/3")
    print(f" {UI.CYAN}1){UI.RESET} {UI.BOLD}{UI.t('step_db_opt1')}{UI.RESET}")
    print(f" {UI.CYAN}2){UI.RESET} {UI.BOLD}{UI.t('step_db_opt2')}{UI.RESET}")
    print(f" {UI.CYAN}3){UI.RESET} {UI.BOLD}{UI.t('step_db_opt3')}{UI.RESET}")
    UI.end_section()

    choice = UI.prompt(UI.t("prompt_db_choice"), default="1")
    random_password = secrets.token_hex(20)

    if choice == "2":
        db_mode = "remote"
        profiles = ""
        db_host = "host.containers.internal:5432"
        pg_bind_ip = "127.0.0.1"
        pg_port = 5432
        db_name = UI.prompt(UI.t("prompt_db_name"), default="forgejo")
        db_user = UI.prompt(UI.t("prompt_db_user"), default="forgejo")
        db_pass = UI.prompt_password(UI.t("prompt_db_pass"), default=random_password)
        ssh_tunnel_enabled = False
        ssh_user = "root"
        ssh_host = "servidor-remoto"
        ssh_key = "/root/.ssh/id_ed25519"
        db_desc = UI.t("desc_db_host")

    elif choice == "3":
        db_mode = "remote"
        profiles = ""
        db_host = UI.prompt(UI.t("prompt_db_host"), default="192.168.1.50:5432")
        pg_bind_ip = "127.0.0.1"
        pg_port = 5432
        db_name = UI.prompt(UI.t("prompt_db_name"), default="forgejo")
        db_user = UI.prompt(UI.t("prompt_db_user"), default="forgejo")
        db_pass = UI.prompt_password(UI.t("prompt_db_pass"), default=random_password)

        create_tunnel = UI.prompt(UI.t("prompt_tunnel_create"), default="N").lower()
        if create_tunnel.startswith("s") or create_tunnel.startswith("y"):
            ssh_tunnel_enabled = True
            db_host = "host.containers.internal:5432"
            ssh_user = UI.prompt(UI.t("prompt_ssh_user"), default="root")
            ssh_host = UI.prompt(UI.t("prompt_ssh_host"), default="servidor-bd.remoto.com")
            ssh_key = UI.prompt(UI.t("prompt_ssh_key"), default="/root/.ssh/id_ed25519")
            db_desc = UI.t("desc_db_remote_tunnel", user=ssh_user, host=ssh_host)
        else:
            ssh_tunnel_enabled = False
            ssh_user = "root"
            ssh_host = "servidor-remoto"
            ssh_key = "/root/.ssh/id_ed25519"
            db_desc = UI.t("desc_db_remote_direct", host=db_host)

    else:
        db_mode = "local"
        profiles = "local-db"
        db_host = "db:5432"
        # Permitir elegir el puerto y bind IP de PostgreSQL en el host
        pg_port = _prompt_port(UI.t("prompt_pg_port"), default=5432)
        pg_bind_ip = UI.prompt(UI.t("prompt_pg_bind"), default="127.0.0.1")
        db_name = UI.prompt(UI.t("prompt_db_name"), default="forgejo")
        db_user = UI.prompt(UI.t("prompt_db_user"), default="forgejo")
        db_pass = random_password
        ssh_tunnel_enabled = False
        ssh_user = "root"
        ssh_host = "servidor-remoto"
        ssh_key = "/root/.ssh/id_ed25519"
        db_desc = UI.t("desc_db_local", port=pg_port)

    return (
        db_mode,
        profiles,
        db_host,
        db_name,
        db_user,
        db_pass,
        pg_bind_ip,
        pg_port,
        ssh_tunnel_enabled,
        ssh_user,
        ssh_host,
        ssh_key,
        db_desc,
    )


def configure_forgejo_version() -> Tuple[str, str]:
    """Descubre dinámicamente versiones estables desde Codeberg y garantiza el tag rootless."""
    UI.section(UI.t("step_ver_title"), "3/3")
    UI.info(UI.t("ver_checking"))
    discovered = fetch_available_rootless_versions(timeout=3.0)
    latest_tag = discovered[0] if discovered else DEFAULT_FALLBACK_TAG
    major_num = latest_tag.split(".")[0]
    stream_tag = f"{major_num}-rootless"

    print(f" {UI.CYAN}1){UI.RESET} {UI.BOLD}{UI.t('ver_opt_latest', tag=latest_tag)}{UI.RESET}")
    print(f" {UI.CYAN}2){UI.RESET} {UI.BOLD}{UI.t('ver_opt_stream', tag=stream_tag)}{UI.RESET}")
    print(f" {UI.CYAN}3){UI.RESET} {UI.BOLD}{UI.t('ver_opt_custom')}{UI.RESET}")
    UI.end_section()

    choice = UI.prompt(UI.t("prompt_ver_choice"), default="1")
    if choice == "2":
        chosen_version = stream_tag
        desc = UI.t("ver_desc_stream", tag=stream_tag)
    elif choice == "3":
        custom = UI.prompt(UI.t("prompt_ver_custom"), default=latest_tag)
        chosen_version = ensure_rootless_tag(custom)
        desc = UI.t("ver_desc_custom", tag=chosen_version)
    else:
        chosen_version = latest_tag
        desc = UI.t("ver_desc_latest", tag=latest_tag)

    return chosen_version, desc


def install_openrc_service(base_dir: Path) -> str:
    """Configura el demonio OpenRC con desescalado seguro a usuario sin privilegios."""
    init_src = base_dir / "scripts" / "forgejo.initd"
    init_dst = Path("/etc/init.d/forgejo")
    conf_dst = Path("/etc/conf.d/forgejo")

    if not init_src.exists():
        return ""

    choice = UI.prompt(f"\n{UI.t('prompt_openrc')}", default="S" if UI.lang == "es" else "Y").lower()
    if not (choice.startswith("s") or choice.startswith("y")):
        return ""

    # Detección de usuario invocador
    caller_user = os.environ.get("SUDO_USER") or getpass.getuser()
    if caller_user == "root":
        try:
            caller_user = base_dir.owner()
        except Exception:
            caller_user = "forgejo"

    UI.section(UI.t("openrc_user_title"), "OpenRC")
    print(f" {UI.CYAN}1){UI.RESET} {UI.BOLD}{UI.t('openrc_user_opt1')}{UI.RESET}")
    print(f" {UI.CYAN}2){UI.RESET} {UI.BOLD}{UI.t('openrc_user_opt2', user=caller_user)}{UI.RESET}")
    UI.end_section()

    user_choice = UI.prompt(UI.t("openrc_user_choice"), default="1")
    if user_choice == "2":
        selected_user = UI.prompt(UI.t("openrc_user_input"), default=caller_user)
        _ensure_subids(selected_user)
    else:
        selected_user = "forgejo"
        _create_system_user("forgejo")

    # Ajustar permisos para que el usuario sin privilegios pueda escribir en ./data y ./postgres
    if selected_user != "root":
        _run_privileged(["chown", "-R", f"{selected_user}:{selected_user}", str(base_dir / "data"), str(base_dir / "postgres")])

    # Generar /etc/conf.d/forgejo
    conf_content = f"""# /etc/conf.d/forgejo - Configuración generada por setup.py
FORGEJO_DIR="{base_dir}"
FORGEJO_USER="{selected_user}"
"""
    tmp_conf = base_dir / ".forgejo.confd.tmp"
    try:
        tmp_conf.write_text(conf_content, encoding="utf-8")
        if _run_privileged(["cp", str(tmp_conf), str(conf_dst)]):
            _run_privileged(["chmod", "644", str(conf_dst)])
            UI.ok(UI.t("confd_ok", user=selected_user))
    finally:
        if tmp_conf.exists():
            tmp_conf.unlink()

    # Copiar /etc/init.d/forgejo
    if _run_privileged(["cp", str(init_src), str(init_dst)]):
        _run_privileged(["chmod", "755", str(init_dst)])
        UI.ok(UI.t("openrc_ok"))

        # Preguntar si desea añadir al arranque de OpenRC
        add_runlevel = UI.prompt(UI.t("openrc_runlevel_prompt"), default="N").lower()
        if add_runlevel.startswith("s") or add_runlevel.startswith("y"):
            if _run_privileged(["rc-update", "add", "forgejo", "default"]):
                UI.ok(UI.t("openrc_runlevel_ok"))
    else:
        UI.warn(UI.t("openrc_warn"))

    return selected_user


def revert_installation(base_dir: Path) -> None:
    """Desinstala limpiamente el servicio OpenRC y revierte usuarios/configuraciones."""
    UI.banner(UI.t("revert_banner"))

    confirm = UI.prompt(UI.t("revert_confirm"), default="N").lower()
    if not (confirm.startswith("s") or confirm.startswith("y")):
        UI.info(UI.t("revert_cancelled"))
        return

    # 1. Leer configuración existente en /etc/conf.d/forgejo si existe
    target_user = "forgejo"
    conf_file = Path("/etc/conf.d/forgejo")
    if conf_file.exists():
        try:
            for line in conf_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("FORGEJO_USER="):
                    target_user = line.split("=", 1)[1].strip('"\'; ')
        except Exception:
            pass

    # 2. Detener servicio
    UI.info(UI.t("revert_stopping"))
    _run_privileged(["rc-service", "forgejo", "stop"])

    # 3. Eliminar de niveles de arranque
    UI.info(UI.t("revert_runlevel"))
    _run_privileged(["rc-update", "del", "forgejo", "default"])

    # 4. Eliminar ficheros OpenRC
    UI.info(UI.t("revert_files"))
    _run_privileged(["rm", "-f", "/etc/init.d/forgejo", "/etc/conf.d/forgejo"])

    # 5. Preguntar si se desea eliminar el usuario de sistema
    user_exists = subprocess.run(["id", target_user], capture_output=True, text=True).returncode == 0
    if user_exists and target_user not in ("root", os.environ.get("SUDO_USER", "")):
        del_user = UI.prompt(UI.t("revert_user_prompt", user=target_user), default="N").lower()
        if del_user.startswith("s") or del_user.startswith("y"):
            UI.info(UI.t("revert_user_del", user=target_user))
            # Matar procesos del usuario
            _run_privileged(["pkill", "-u", target_user])
            # Eliminar usuario y su home
            _run_privileged(["userdel", "-r", target_user])
            # Purgar de /etc/subuid y /etc/subgid
            _run_privileged(["sed", "-i", f"/^{target_user}:/d", "/etc/subuid"])
            _run_privileged(["sed", "-i", f"/^{target_user}:/d", "/etc/subgid"])

    # 6. Aviso sobre datos
    UI.ok(UI.t("revert_done"))
    UI.warn(UI.t("revert_data_notice"))


def main() -> None:
    base_dir = Path(__file__).resolve().parent

    # 1. Selección de idioma
    UI.lang = select_language()

    # Si se invoca con --revert o --uninstall, derivar a la rutina de desinstalación
    if any(arg in ("--revert", "--uninstall") for arg in sys.argv[1:]):
        revert_installation(base_dir)
        sys.exit(0)

    UI.banner(
        UI.t("banner_title"),
        UI.t("banner_sub"),
    )

    # 2. Comprobaciones previas
    check_dependencies()
    uid, gid, userns_mode = check_user_and_permissions(base_dir)

    env_path = base_dir / ".env"
    if env_path.exists():
        UI.warn(UI.t("env_exists", path=env_path))
        overwrite = UI.prompt(UI.t("env_overwrite"), default="N").lower()
        if not (overwrite.startswith("s") or overwrite.startswith("y")):
            UI.info(UI.t("env_kept"))
            sys.exit(0)

    # 3. Asistente interactivo
    (
        bind_ip,
        http_port,
        ssh_bind_ip,
        ssh_port,
        domain,
        root_url,
        web_desc,
    ) = configure_web_access()

    (
        db_mode,
        profiles,
        db_host,
        db_name,
        db_user,
        db_pass,
        pg_bind_ip,
        pg_port,
        ssh_tunnel,
        ssh_user,
        ssh_host,
        ssh_key,
        db_desc,
    ) = configure_database()

    forgejo_ver, ver_desc = configure_forgejo_version()

    # 4. Escribir archivo .env
    env_content = f"""# ==============================================================================
# CONFIGURACIÓN GENERADA POR SETUP.PY EN GENTOO LINUX
# ==============================================================================

# Versión de Forgejo (100% Rootless Obligatorio)
FORGEJO_VERSION={forgejo_ver}

# Modo de Base de Datos / Database Mode
DB_MODE={db_mode}
COMPOSE_PROFILES={profiles}
FORGEJO_DB_TYPE=postgres
FORGEJO_DB_HOST={db_host}
POSTGRES_DB={db_name}
POSTGRES_USER={db_user}
POSTGRES_PASSWORD={db_pass}
POSTGRES_BIND_IP={pg_bind_ip}
POSTGRES_PORT={pg_port}

# Túnel SSH / SSH Tunnel
SSH_TUNNEL_ENABLED={"true" if ssh_tunnel else "false"}
SSH_TUNNEL_BIND_IP=0.0.0.0
SSH_TUNNEL_USER={ssh_user}
SSH_TUNNEL_HOST={ssh_host}
SSH_TUNNEL_PORT=22
SSH_TUNNEL_KEY={ssh_key}
SSH_TUNNEL_REMOTE_DB_HOST=127.0.0.1
SSH_TUNNEL_REMOTE_DB_PORT=5432
SSH_TUNNEL_LOCAL_PORT=5432

# Red y Acceso Web / Network & Web Access
FORGEJO_BIND_IP={bind_ip}
FORGEJO_HTTP_PORT={http_port}
FORGEJO_SSH_BIND_IP={ssh_bind_ip}
FORGEJO_SSH_PORT={ssh_port}
FORGEJO_DOMAIN={domain}
FORGEJO_ROOT_URL={root_url}

# Usuario y Permisos / Container User
USER_UID={uid}
USER_GID={gid}
USERNS_MODE={userns_mode}
"""
    env_path.write_text(env_content, encoding="utf-8")
    env_path.chmod(0o600)
    UI.ok(UI.t("env_saved"))

    # 5. Instalación de OpenRC con desescalado
    service_user = install_openrc_service(base_dir)

    # 6. Tarjeta de resumen
    summary_rows = [
        (UI.t("row_version"), ver_desc),
        (UI.t("row_web"), web_desc),
        (UI.t("row_http_port"), f"{http_port} (Bind: {bind_ip})"),
        (UI.t("row_ssh_port"), f"{ssh_port} (Bind: {ssh_bind_ip})"),
        (UI.t("row_db"), db_desc),
        (UI.t("row_pg_port"), f"{pg_port} (Bind: {pg_bind_ip})" if profiles == "local-db" else db_host),
        (UI.t("row_container"), f"{UI.t('status_active')} (local-db)" if profiles == "local-db" else UI.t("status_inactive")),
        (UI.t("row_tunnel"), UI.t("status_active") if ssh_tunnel else UI.t("status_not_needed")),
        (UI.t("row_user"), service_user if service_user else "rootless"),
        (UI.t("row_env"), str(env_path)),
    ]
    UI.card(UI.t("card_title"), summary_rows)

    print(f"{UI.BOLD}{UI.t('footer_cmds')}{UI.RESET}")
    print(f"  • {UI.t('footer_start')}       {UI.CYAN}./scripts/manage.sh start{UI.RESET} (or: {UI.CYAN}rc-service forgejo start{UI.RESET})")
    print(f"  • {UI.t('footer_status')}         {UI.CYAN}./scripts/manage.sh status{UI.RESET}")
    print(f"  • {UI.t('footer_logs')}           {UI.CYAN}./scripts/manage.sh logs server{UI.RESET}")
    print(f"  • {UI.t('footer_admin')}          {UI.CYAN}./scripts/manage.sh create-admin{UI.RESET}")
    print(f"  • {UI.t('footer_upgrade')}        {UI.CYAN}./scripts/manage.sh upgrade{UI.RESET}")
    print(f"  • {UI.t('footer_uninstall')}      {UI.CYAN}./setup.sh --revert{UI.RESET}")
    print(f"\n  {UI.DIM}{UI.t('footer_migrate')}{UI.RESET} {UI.BOLD}{UI.CYAN}./migrate.sh{UI.RESET}\n")


if __name__ == "__main__":
    main()
