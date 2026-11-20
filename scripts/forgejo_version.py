#!/usr/bin/env python3
"""
scripts/forgejo_version.py - Gestor de versiones y normalización estricta de tags Rootless.
                            Forgejo version manager & strict Rootless tag normalizer.

Pure Python 3 standard library.
"""

from __future__ import annotations

import json
import re
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple

CODEBERG_RELEASES_API = "https://codeberg.org/api/v1/repos/forgejo/forgejo/releases?limit=20"
DEFAULT_FALLBACK_TAG = "17-rootless"


def ensure_rootless_tag(tag: str) -> str:
    """Garantiza que cualquier tag utilice obligatoriamente la variante -rootless."""
    cleaned = tag.strip().lstrip("v")
    if not cleaned.endswith("-rootless"):
        cleaned = f"{cleaned}-rootless"
    return cleaned


def _parse_semver(version_str: str) -> Tuple[int, int, int]:
    """Convierte una cadena tipo 17.0.2 en una tupla de enteros (17, 0, 2) para ordenación."""
    # Eliminar sufijo -rootless u otros si los tuviera
    base = version_str.split("-")[0].lstrip("v")
    parts = base.split(".")
    major = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
    minor = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    patch = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    return (major, minor, patch)


def fetch_available_rootless_versions(timeout: float = 3.0) -> List[str]:
    """
    Consulta la API pública de Codeberg y devuelve una lista ordenada de tags estables con -rootless.
    En caso de error de red o timeout, devuelve una lista de fallback segura sin bloquear la ejecución.
    """
    req = urllib.request.Request(
        CODEBERG_RELEASES_API,
        headers={"User-Agent": "ForgejoGentooManager/1.0", "Accept": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                discovered: List[str] = []

                for item in data:
                    if not item.get("prerelease") and not item.get("draft"):
                        tag_name = item.get("tag_name", "").strip()
                        if tag_name:
                            discovered.append(tag_name)

                # Ordenar descendentemente por SemVer
                discovered.sort(key=_parse_semver, reverse=True)

                # Convertir a tags rootless garantizados
                rootless_tags: List[str] = []
                for tag in discovered:
                    rtag = ensure_rootless_tag(tag)
                    if rtag not in rootless_tags:
                        rootless_tags.append(rtag)

                if rootless_tags:
                    return rootless_tags
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        # Fallback offline controlado
        pass

    return [DEFAULT_FALLBACK_TAG]


def get_env_version(env_path: Path) -> str:
    """Lee el archivo .env y extrae la versión configurada de Forgejo (por defecto DEFAULT_FALLBACK_TAG)."""
    if not env_path.exists():
        return DEFAULT_FALLBACK_TAG

    try:
        content = env_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            line_strip = line.strip()
            if line_strip.startswith("FORGEJO_VERSION="):
                val = line_strip.split("=", 1)[1].strip('"\'; ')
                if val:
                    return ensure_rootless_tag(val)
    except OSError:
        pass

    return DEFAULT_FALLBACK_TAG


def set_env_version(env_path: Path, new_version: str) -> bool:
    """
    Actualiza atómicamente FORGEJO_VERSION en .env garantizando -rootless
    y preservando un respaldo en .env.bak.
    """
    safe_version = ensure_rootless_tag(new_version)
    if not env_path.exists():
        return False

    bak_path = env_path.with_suffix(".bak")
    try:
        shutil.copy(env_path, bak_path)
    except OSError:
        return False

    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
        found = False
        new_lines: List[str] = []

        for line in lines:
            if line.strip().startswith("FORGEJO_VERSION="):
                new_lines.append(f"FORGEJO_VERSION={safe_version}")
                found = True
            else:
                new_lines.append(line)

        if not found:
            # Si no existía, insertarla en la sección de configuración
            new_lines.append(f"FORGEJO_VERSION={safe_version}")

        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        return True
    except OSError:
        # Restaurar backup si hubo fallo
        if bak_path.exists():
            shutil.copy(bak_path, env_path)
        return False


if __name__ == "__main__":
    versions = fetch_available_rootless_versions()
    print("Versiones Rootless disponibles:")
    for v in versions[:5]:
        print(f"  • {v}")
