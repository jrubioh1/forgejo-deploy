#!/usr/bin/env python3
"""
migrate.py - Asistente Interactivo de Migraciones de Datos para Forgejo.
             Interactive Data Migration Assistant for Forgejo.

Soporte Bilingüe / Bilingual Support: Español & English.
Cero dependencias externas / Zero third-party dependencies (Pure Python 3).
"""

from __future__ import annotations

import getpass
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ==============================================================================
# DICCIONARIO DE LOCALIZACIÓN (I18N)
# ==============================================================================
STRINGS: Dict[str, Dict[str, str]] = {
    "es": {
        "banner_title": "FORGEJO - ASISTENTE DE MIGRACIÓN DE DATOS",
        "banner_sub": "Importación de Repositorios, Wikis y Metadatos",
        "sec_platform": "Plataforma de Origen",
        "opt_gitbucket": "GitBucket (Java/Jetty)",
        "prompt_platform": "Selecciona la plataforma a migrar [1]",
        "sec_gitbucket_config": "Configuración de la Migración desde GitBucket",
        "prompt_gb_dir": "Ruta al directorio de datos de GitBucket",
        "prompt_gb_running": "¿La aplicación GitBucket está actualmente en ejecución? [S/n]",
        "prompt_gb_url": "URL de la instancia en ejecución de GitBucket",
        "prompt_gb_token": "Token de acceso de GitBucket (opcional para incidencias)",
        "prompt_forgejo_url": "URL base de Forgejo",
        "prompt_forgejo_token": "Token de Administrador de Forgejo",
        "token_required_err": "Se requiere un token de administrador de Forgejo para migrar datos.",
        "prompt_dry_run": "¿Deseas ejecutar primero una SIMULACIÓN (--dry-run) sin aplicar cambios? [S/n]",
        "sim_notice": "Iniciando auditoría y simulación sin modificar Forgejo...",
        "live_notice": "Iniciando migración en vivo hacia Forgejo...",
        "ok_done": "Proceso de migración finalizado exitosamente.",
        "err_failed": "El proceso de migración terminó con errores.",
        "hint_live": "Para ejecutar la migración definitiva tras la simulación, vuelve a ejecutar ./migrate.sh y responde 'n' a la simulación.",
    },
    "en": {
        "banner_title": "FORGEJO - DATA MIGRATION ASSISTANT",
        "banner_sub": "Import Repositories, Wikis & Metadata",
        "sec_platform": "Source Platform",
        "opt_gitbucket": "GitBucket (Java/Jetty)",
        "prompt_platform": "Select source platform to migrate [1]",
        "sec_gitbucket_config": "GitBucket Migration Configuration",
        "prompt_gb_dir": "Path to GitBucket data directory",
        "prompt_gb_running": "Is the GitBucket application currently running? [Y/n]",
        "prompt_gb_url": "URL of running GitBucket instance",
        "prompt_gb_token": "GitBucket Personal Access Token (optional for issues)",
        "prompt_forgejo_url": "Forgejo base URL",
        "prompt_forgejo_token": "Forgejo Administrator Access Token",
        "token_required_err": "A Forgejo administrator token is required to migrate data.",
        "prompt_dry_run": "Do you want to run a SIMULATION (--dry-run) first without applying changes? [Y/n]",
        "sim_notice": "Starting audit & simulation without modifying Forgejo...",
        "live_notice": "Starting live migration to Forgejo...",
        "ok_done": "Migration process completed successfully.",
        "err_failed": "Migration process finished with errors.",
        "hint_live": "To run live migration after simulation, run ./migrate.sh again and answer 'n' to simulation.",
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
        width = 72
        print(f"\n{cls.BOLD}{cls.CYAN}┌{'─' * (width - 2)}┐{cls.RESET}")
        print(f"{cls.BOLD}{cls.CYAN}│{title.center(width - 2)}│{cls.RESET}")
        if subtitle:
            print(f"{cls.DIM}{cls.CYAN}│{subtitle.center(width - 2)}│{cls.RESET}")
        print(f"{cls.BOLD}{cls.CYAN}└{'─' * (width - 2)}┘{cls.RESET}\n")

    @classmethod
    def section(cls, title: str) -> None:
        pad = max(2, 66 - len(title))
        print(f"\n{cls.BOLD}{cls.MAGENTA}┌── {title} {'─' * pad}┐{cls.RESET}")

    @classmethod
    def end_section(cls) -> None:
        print(f"{cls.BOLD}{cls.MAGENTA}└{'─' * 70}┘{cls.RESET}")

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
        val = input(prompt_str).strip()
        return val if val else default

    @classmethod
    def prompt_password(cls, text: str) -> str:
        prompt_str = f" {cls.BOLD}{cls.YELLOW}?{cls.RESET} {text}: "
        return getpass.getpass(prompt_str).strip()


def select_language() -> str:
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


def load_env_defaults(base_dir: Path) -> Dict[str, str]:
    env_file = base_dir / ".env"
    data: Dict[str, str] = {}
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                data[k.strip()] = v.strip().strip("'\"")
    return data


def detect_gitbucket_path() -> str:
    candidates = [
        Path.home() / ".gitbucket",
        Path("/var/lib/gitbucket"),
        Path("/var/gitbucket"),
        Path("/opt/gitbucket"),
        Path("/root/.gitbucket"),
    ]
    for c in candidates:
        if c.is_dir() and (c / "repositories").is_dir():
            return str(c)
    return str(Path.home() / ".gitbucket")


def run_gitbucket_migration(base_dir: Path, env_defaults: Dict[str, str]) -> int:
    UI.section(UI.t("sec_gitbucket_config"))

    default_gb_dir = detect_gitbucket_path()
    gb_dir = UI.prompt(UI.t("prompt_gb_dir"), default=default_gb_dir)

    default_forgejo_url = env_defaults.get("FORGEJO_ROOT_URL", "http://127.0.0.1:3000")
    forgejo_url = UI.prompt(UI.t("prompt_forgejo_url"), default=default_forgejo_url)

    forgejo_token = env_defaults.get("FORGEJO_ADMIN_TOKEN", "")
    if not forgejo_token:
        forgejo_token = UI.prompt_password(UI.t("prompt_forgejo_token"))

    # Comprobar si GitBucket está en ejecución para migrar incidencias
    gb_running = UI.prompt(UI.t("prompt_gb_running"), default="S" if UI.lang == "es" else "Y").lower()
    gb_url = ""
    gb_token = ""
    if gb_running.startswith("s") or gb_running.startswith("y"):
        gb_url = UI.prompt(UI.t("prompt_gb_url"), default="http://127.0.0.1:8080/gitbucket")
        gb_token = UI.prompt(UI.t("prompt_gb_token"), default="")

    # Preguntar si simulación
    dry_run = UI.prompt(UI.t("prompt_dry_run"), default="S" if UI.lang == "es" else "Y").lower()
    is_dry_run = dry_run.startswith("s") or dry_run.startswith("y")

    UI.end_section()

    if not forgejo_token and not is_dry_run:
        UI.err(UI.t("token_required_err"))
        return 1

    # Construir comando
    cmd = [
        sys.executable,
        str(base_dir / "scripts" / "migrate_gitbucket.py"),
        "--gitbucket-dir",
        gb_dir,
        "--forgejo-url",
        forgejo_url,
        "--forgejo-token",
        forgejo_token or "dry_run_token",
    ]

    if is_dry_run:
        cmd.append("--dry-run")
        UI.warn(UI.t("sim_notice"))
    else:
        UI.info(UI.t("live_notice"))

    if gb_url:
        cmd.extend(["--gitbucket-url", gb_url])
    if gb_token:
        cmd.extend(["--gitbucket-token", gb_token])

    print("")
    res = subprocess.run(cmd, check=False)

    if res.returncode == 0:
        UI.ok(UI.t("ok_done"))
        if is_dry_run:
            print(f"\n {UI.DIM}{UI.t('hint_live')}{UI.RESET}\n")
    else:
        UI.err(UI.t("err_failed"))

    return res.returncode


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    env_defaults = load_env_defaults(base_dir)

    # 1. Selección de idioma
    UI.lang = select_language()

    UI.banner(
        UI.t("banner_title"),
        UI.t("banner_sub"),
    )

    # 2. Selector de Plataforma (Limpio, sin placeholders)
    UI.section(UI.t("sec_platform"))
    print(f" {UI.CYAN}1){UI.RESET} {UI.BOLD}{UI.t('opt_gitbucket')}{UI.RESET}")
    UI.end_section()

    choice = UI.prompt(UI.t("prompt_platform"), default="1")

    if choice == "1":
        sys.exit(run_gitbucket_migration(base_dir, env_defaults))
    else:
        sys.exit(run_gitbucket_migration(base_dir, env_defaults))


if __name__ == "__main__":
    main()
