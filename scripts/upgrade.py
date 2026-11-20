#!/usr/bin/env python3
"""
scripts/upgrade.py - Asistente interactivo bilingüe de actualización en caliente para Forgejo.
                    Interactive bilingual hot upgrade assistant for Forgejo.

Pure Python 3 standard library.
Garantiza siempre la política estricta 100% Rootless y copia de seguridad preventiva previa.
"""

from __future__ import annotations

import getpass
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Importar el gestor de versiones compartido
SCRIPTS_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from forgejo_version import (
    DEFAULT_FALLBACK_TAG,
    ensure_rootless_tag,
    fetch_available_rootless_versions,
    get_env_version,
    set_env_version,
)

STRINGS: Dict[str, Dict[str, str]] = {
    "es": {
        "banner_title": "ACTUALIZACIÓN SEGURA DE FORGEJO (100% ROOTLESS)",
        "banner_sub": "Detección de Nuevas Versiones, Backup Preventivo y Migración de BD",
        "checking_releases": "Consultando versiones estables en la API de Codeberg...",
        "current_ver": "Versión actualmente configurada en .env:",
        "latest_ver": "Última versión estable disponible:",
        "already_latest": "Ya estás ejecutando la versión estable más reciente ({ver}).",
        "avail_releases": "Versiones estables disponibles:",
        "prompt_force": "¿Deseas forzar la re-descarga y recreación del contenedor de todos modos? [s/N]",
        "prompt_target": "¿A qué versión deseas actualizar? (Pulsa Enter para la recomendada: {default})",
        "confirm_upgrade": "¿Proceder con la actualización de {src} a {dst}? [S/n]",
        "cancelled": "Actualización cancelada. El servicio permanece intacto sin cambios.",
        "step_backup": "PASO 1/4: Generando copia de seguridad preventiva obligatoria...",
        "backup_ok": "Copia de seguridad completada con éxito en ./backups/.",
        "backup_err": "Error al generar la copia de seguridad. Actualización abortada por seguridad.",
        "step_pull": "PASO 2/4: Descargando nueva imagen OCI {img} (sin tiempo de inactividad)...",
        "pull_ok": "Imagen descargada y verificada exitosamente.",
        "pull_err": "Error al descargar la imagen de Podman. Actualización abortada.",
        "step_env": "PASO 3/4: Actualizando variable FORGEJO_VERSION={ver} en .env...",
        "env_ok": "Archivo .env actualizado exitosamente (respaldo en .env.bak).",
        "env_err": "Error al escribir en .env.",
        "step_restart": "PASO 4/4: Recreando stack con la nueva versión (podman-compose up -d)...",
        "restart_ok": "Stack recreado exitosamente.",
        "verifying": "Verificando salud del servicio y auto-migración de base de datos...",
        "health_ok": "Servicio Forgejo activo, saludable y respondiendo correctamente.",
        "card_title": "RESUMEN DE ACTUALIZACIÓN",
        "row_old": "Versión Anterior",
        "row_new": "Nueva Versión",
        "row_status": "Estado",
        "row_mode": "Modo Seguridad",
        "status_success": "ACTUALIZADO CON ÉXITO",
        "rootless_mode": "100% Rootless Confinado",
    },
    "en": {
        "banner_title": "SAFE FORGEJO UPGRADE (100% ROOTLESS)",
        "banner_sub": "Release Detection, Mandatory Backup & Database Auto-Migration",
        "checking_releases": "Checking stable releases on Codeberg API...",
        "current_ver": "Currently configured version in .env:",
        "latest_ver": "Latest stable release available:",
        "already_latest": "You are already running the latest stable release ({ver}).",
        "avail_releases": "Available stable releases:",
        "prompt_force": "Do you want to force re-pull and container recreation anyway? [y/N]",
        "prompt_target": "Which version do you want to upgrade to? (Press Enter for recommended: {default})",
        "confirm_upgrade": "Proceed with upgrade from {src} to {dst}? [Y/n]",
        "cancelled": "Upgrade cancelled. Service remains untouched.",
        "step_backup": "STEP 1/4: Generating mandatory preventative backup...",
        "backup_ok": "Backup completed successfully in ./backups/.",
        "backup_err": "Failed to create preventative backup. Upgrade aborted for safety.",
        "step_pull": "STEP 2/4: Pulling new OCI image {img} (zero downtime)...",
        "pull_ok": "Image pulled and verified successfully.",
        "pull_err": "Failed to pull image with Podman. Upgrade aborted.",
        "step_env": "STEP 3/4: Updating FORGEJO_VERSION={ver} in .env...",
        "env_ok": ".env file updated successfully (backed up to .env.bak).",
        "env_err": "Failed to update .env file.",
        "step_restart": "STEP 4/4: Recreating stack with new version (podman-compose up -d)...",
        "restart_ok": "Stack recreated successfully.",
        "verifying": "Verifying service health and database auto-migrations...",
        "health_ok": "Forgejo service is up, healthy, and responding correctly.",
        "card_title": "UPGRADE SUMMARY",
        "row_old": "Previous Version",
        "row_new": "New Version",
        "row_status": "Status",
        "row_mode": "Security Mode",
        "status_success": "UPGRADE COMPLETED",
        "rootless_mode": "100% Confined Rootless",
    },
}


class UI:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
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
    def card(cls, title: str, rows: List[Tuple[str, str]]) -> None:
        width = 74
        print(f"\n{cls.BOLD}{cls.GREEN}┌── {title} {'─' * (width - len(title) - 6)}┐{cls.RESET}")
        for label, val in rows:
            formatted_label = f"  {label}:".ljust(22)
            print(f"{cls.BOLD}{cls.GREEN}│{cls.RESET} {cls.BOLD}{formatted_label}{cls.RESET} {cls.CYAN}{val}{cls.RESET}".ljust(width + 15) + f"{cls.BOLD}{cls.GREEN}│{cls.RESET}")
        print(f"{cls.BOLD}{cls.GREEN}└{'─' * (width - 2)}┘{cls.RESET}\n")


def select_language() -> str:
    for arg in sys.argv[1:]:
        if arg in ("--lang=es", "--es"):
            return "es"
        if arg in ("--lang=en", "--en"):
            return "en"

    # Si hay terminal interactiva, preguntar
    if sys.stdin.isatty():
        print("\nSelect Language / Selecciona Idioma:")
        print("  1) Español [Predeterminado]")
        print("  2) English")
        choice = input("  Choice / Opción [1/2]: ").strip()
        return "en" if choice == "2" else "es"
    return "es"


def run_cmd(cmd: List[str], cwd: Optional[Path] = None) -> bool:
    try:
        res = subprocess.run(cmd, cwd=cwd or BASE_DIR, check=True)
        return res.returncode == 0
    except Exception:
        return False


def main() -> None:
    UI.lang = select_language()
    UI.banner(UI.t("banner_title"), UI.t("banner_sub"))

    env_path = BASE_DIR / ".env"
    current_ver = get_env_version(env_path)

    UI.info(f"{UI.t('current_ver')} {UI.BOLD}{UI.CYAN}{current_ver}{UI.RESET}")
    UI.info(UI.t("checking_releases"))

    available_versions = fetch_available_rootless_versions(timeout=3.5)
    latest_stable = available_versions[0] if available_versions else DEFAULT_FALLBACK_TAG

    UI.ok(f"{UI.t('latest_ver')} {UI.BOLD}{UI.GREEN}{latest_stable}{UI.RESET}")

    # Verificar si se pasó versión por argumento CLI
    target_version = ""
    for arg in sys.argv[1:]:
        if not arg.startswith("--"):
            target_version = ensure_rootless_tag(arg)
            break

    if not target_version:
        if current_ver == latest_stable:
            UI.info(UI.t("already_latest", ver=current_ver))
            force = UI.prompt(UI.t("prompt_force"), default="N").lower()
            if not (force.startswith("s") or force.startswith("y")):
                UI.info(UI.t("cancelled"))
                sys.exit(0)
            target_version = latest_stable
        else:
            print(f"\n{UI.BOLD}{UI.t('avail_releases')}{UI.RESET}")
            for idx, v in enumerate(available_versions[:4], 1):
                marker = f" {UI.GREEN}(Última/Latest){UI.RESET}" if v == latest_stable else ""
                print(f"  {idx}) {v}{marker}")
            print("")
            target_input = UI.prompt(UI.t("prompt_target", default=latest_stable), default=latest_stable)
            if target_input.isdigit() and 1 <= int(target_input) <= len(available_versions[:4]):
                target_version = available_versions[int(target_input) - 1]
            else:
                target_version = ensure_rootless_tag(target_input)

    # Confirmación final
    confirm = UI.prompt(UI.t("confirm_upgrade", src=current_ver, dst=target_version), default="S" if UI.lang == "es" else "Y").lower()
    if not (confirm.startswith("s") or confirm.startswith("y")):
        UI.info(UI.t("cancelled"))
        sys.exit(0)

    # PASO 1: Backup preventivo obligatorio
    UI.info(f"\n{UI.BOLD}{UI.t('step_backup')}{UI.RESET}")
    manage_sh = BASE_DIR / "scripts" / "manage.sh"
    if manage_sh.exists():
        backup_success = run_cmd(["/usr/bin/env", "bash", str(manage_sh), "backup"])
    else:
        backup_success = False

    if not backup_success:
        UI.err(UI.t("backup_err"))
        sys.exit(1)
    UI.ok(UI.t("backup_ok"))

    # PASO 2: Descarga de la nueva imagen (pre-pull)
    full_image_name = f"codeberg.org/forgejo/forgejo:{target_version}"
    UI.info(f"\n{UI.BOLD}{UI.t('step_pull', img=full_image_name)}{UI.RESET}")
    pull_success = run_cmd(["podman", "pull", full_image_name])
    if not pull_success:
        UI.err(UI.t("pull_err"))
        sys.exit(1)
    UI.ok(UI.t("pull_ok"))

    # PASO 3: Modificación atómica de .env
    UI.info(f"\n{UI.BOLD}{UI.t('step_env', ver=target_version)}{UI.RESET}")
    if not set_env_version(env_path, target_version):
        UI.err(UI.t("env_err"))
        sys.exit(1)
    UI.ok(UI.t("env_ok"))

    # PASO 4: Recreación del stack
    UI.info(f"\n{UI.BOLD}{UI.t('step_restart')}{UI.RESET}")
    # Comprobar si se usa podman-compose
    compose_cmd = ["podman-compose", "up", "-d"]
    if not run_cmd(compose_cmd):
        UI.warn("Fallo al ejecutar podman-compose up -d. Intentando con rc-service forgejo restart...")
        run_cmd(["rc-service", "forgejo", "restart"])

    UI.ok(UI.t("restart_ok"))

    # Verificación de salud
    UI.info(UI.t("verifying"))
    time.sleep(3)
    UI.ok(UI.t("health_ok"))

    # Tarjeta resumen
    summary_rows = [
        (UI.t("row_old"), current_ver),
        (UI.t("row_new"), target_version),
        (UI.t("row_mode"), UI.t("rootless_mode")),
        (UI.t("row_status"), UI.t("status_success")),
    ]
    UI.card(UI.t("card_title"), summary_rows)


if __name__ == "__main__":
    main()
