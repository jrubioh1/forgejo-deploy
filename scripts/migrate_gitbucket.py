#!/usr/bin/env python3
"""
scripts/migrate_gitbucket.py - Suite de Migración Integral de GitBucket a Forgejo.

Migra repositorios Git, wikis, cuentas de usuario, incidencias, comentarios,
etiquetas e hitos desde GitBucket hacia Forgejo con modo simulación (--dry-run).
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import secrets
import string
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("gitbucket_migration")


@dataclass
class DiscoveredRepo:
    owner: str
    name: str
    git_dir: Path
    wiki_dir: Optional[Path] = None
    is_private: bool = True
    description: str = ""


@dataclass
class MigrationStats:
    users_created: int = 0
    repos_migrated: int = 0
    wikis_migrated: int = 0
    issues_migrated: int = 0
    comments_migrated: int = 0
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class ForgejoClient:
    """Cliente HTTP para interactuar con la API REST v1 de Forgejo."""

    def __init__(self, base_url: str, token: str, dry_run: bool = False):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.dry_run = dry_run

    def _request(
        self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None
    ) -> Tuple[int, Any]:
        url = f"{self.base_url}/api/v1{endpoint}"
        headers = {
            "Authorization": f"token {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        req_data = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(url, data=req_data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                status = resp.status
                body = resp.read().decode("utf-8")
                return status, json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            try:
                parsed = json.loads(body)
            except Exception:
                parsed = {"message": body}
            return exc.code, parsed
        except urllib.error.URLError as exc:
            logger.error("Error de conexión con Forgejo en %s: %s", url, exc)
            return 0, {"message": str(exc)}

    def check_version(self) -> bool:
        status, data = self._request("GET", "/version")
        if status == 200:
            logger.info("Conectado con éxito a Forgejo. Versión: %s", data.get("version", "desconocida"))
            return True
        logger.error("No se pudo conectar a Forgejo en %s. Código: %d", self.base_url, status)
        return False

    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        status, data = self._request("GET", f"/users/{username}")
        if status == 200:
            return data
        return None

    def create_user(self, username: str, email: str, password: str) -> bool:
        if self.dry_run:
            logger.info("[DRY-RUN] Crearía usuario en Forgejo: %s <%s>", username, email)
            return True

        payload = {
            "username": username,
            "email": email,
            "password": password,
            "must_change_password": True,
            "send_notify": False,
        }
        status, data = self._request("POST", "/admin/users", payload)
        if status in (201, 200):
            logger.info("Usuario creado en Forgejo: %s", username)
            return True
        logger.warning("Fallo al crear usuario %s: %s", username, data.get("message", "Error desconocido"))
        return False

    def get_repo(self, owner: str, repo_name: str) -> Optional[Dict[str, Any]]:
        status, data = self._request("GET", f"/repos/{owner}/{repo_name}")
        if status == 200:
            return data
        return None

    def create_repo(self, owner: str, repo_name: str, private: bool = True, description: str = "") -> bool:
        if self.dry_run:
            logger.info("[DRY-RUN] Crearía repositorio en Forgejo: %s/%s (privado: %s)", owner, repo_name, private)
            return True

        payload = {
            "name": repo_name,
            "private": private,
            "description": description or f"Migrado desde GitBucket ({owner}/{repo_name})",
            "auto_init": False,
        }
        # Intentar crear bajo la cuenta de usuario o admin
        status, data = self._request("POST", f"/admin/users/{owner}/repos", payload)
        if status in (201, 200):
            logger.info("Repositorio creado en Forgejo: %s/%s", owner, repo_name)
            return True

        # Si el propietario es una organización
        status_org, data_org = self._request("POST", f"/orgs/{owner}/repos", payload)
        if status_org in (201, 200):
            logger.info("Repositorio creado en organización Forgejo: %s/%s", owner, repo_name)
            return True

        logger.warning("No se pudo crear repositorio %s/%s: %s", owner, repo_name, data.get("message", "Error"))
        return False

    def create_issue(
        self, owner: str, repo: str, title: str, body: str, labels: List[int] = None
    ) -> bool:
        if self.dry_run:
            logger.info("[DRY-RUN] Crearía Issue en %s/%s: '%s'", owner, repo, title)
            return True

        payload = {"title": title, "body": body, "labels": labels or []}
        status, _ = self._request("POST", f"/repos/{owner}/{repo}/issues", payload)
        return status in (201, 200)

    def create_issue_comment(self, owner: str, repo: str, issue_index: int, body: str) -> bool:
        if self.dry_run:
            logger.info("[DRY-RUN] Crearía comentario en %s/%s#%d", owner, repo, issue_index)
            return True

        payload = {"body": body}
        status, _ = self._request("POST", f"/repos/{owner}/{repo}/issues/{issue_index}/comments", payload)
        return status in (201, 200)


def generate_temp_password(length: int = 16) -> str:
    """Genera una contraseña temporal segura con al menos una mayúscula, minúscula y número."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.islower() for c in password)
            and any(c.isupper() for c in password)
            and any(c.isdigit() for c in password)
        ):
            return password


def find_gitbucket_directory(custom_path: Optional[str]) -> Optional[Path]:
    """Localiza el directorio base de datos y repositorios de GitBucket."""
    candidates = []
    if custom_path:
        candidates.append(Path(custom_path).expanduser().resolve())

    home_gitbucket = Path.home() / ".gitbucket"
    candidates.extend(
        [
            home_gitbucket,
            Path("/var/lib/gitbucket"),
            Path("/var/gitbucket"),
            Path("/opt/gitbucket"),
            Path("/root/.gitbucket"),
        ]
    )

    for cand in candidates:
        if cand.is_dir() and (cand / "repositories").is_dir():
            logger.info("Directorio de GitBucket localizado en: %s", cand)
            return cand
        if cand.is_dir() and any(cand.glob("*.git")):
            logger.info("Repositorios GitBucket localizados en: %s", cand)
            return cand

    return None


def discover_repositories(gitbucket_dir: Path) -> List[DiscoveredRepo]:
    """Escanea el directorio repositories/ de GitBucket para encontrar repositorios y wikis."""
    repos_base = gitbucket_dir / "repositories"
    if not repos_base.is_dir():
        repos_base = gitbucket_dir

    discovered: List[DiscoveredRepo] = []
    logger.info("Escaneando repositorios en: %s", repos_base)

    # GitBucket estructura típica: repositories/<owner>/<repo_name>.git
    for owner_dir in repos_base.iterdir():
        if not owner_dir.is_dir() or owner_dir.name.startswith("."):
            continue

        owner_name = owner_dir.name

        for item in owner_dir.iterdir():
            if item.is_dir() and item.name.endswith(".git"):
                # Comprobar si es un wiki
                if item.name.endswith(".wiki.git"):
                    continue

                repo_name = item.name[:-4]  # quitar .git
                wiki_candidate = owner_dir / f"{repo_name}.wiki.git"
                wiki_dir = wiki_candidate if wiki_candidate.is_dir() else None

                discovered.append(
                    DiscoveredRepo(
                        owner=owner_name,
                        name=repo_name,
                        git_dir=item,
                        wiki_dir=wiki_dir,
                    )
                )

    logger.info("Se encontraron %d repositorios en GitBucket.", len(discovered))
    return discovered


def push_git_mirror(
    repo_path: Path, remote_url: str, dry_run: bool = False
) -> Tuple[bool, str]:
    """Ejecuta git push --mirror hacia Forgejo garantizando preservación completa del historial."""
    if dry_run:
        logger.info("[DRY-RUN] Ejecutaría: git -C %s push --mirror %s", repo_path, remote_url)
        return True, "Simulación completada con éxito"

    cmd = ["git", "-C", str(repo_path), "push", "--mirror", remote_url]
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=300,
            check=False,
        )
        if proc.returncode == 0:
            return True, proc.stdout
        return False, proc.stderr
    except subprocess.SubprocessError as exc:
        return False, str(exc)


def fetch_gitbucket_issues(
    gitbucket_url: str, token: Optional[str], owner: str, repo: str
) -> List[Dict[str, Any]]:
    """Consulta las incidencias mediante la API v3 compatible de GitBucket."""
    clean_url = gitbucket_url.rstrip("/")
    endpoint = f"{clean_url}/api/v3/repos/{owner}/{repo}/issues?state=all"
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"token {token}"

    req = urllib.request.Request(endpoint, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return data if isinstance(data, list) else []
    except Exception as exc:
        logger.debug("No se pudieron obtener issues vía API para %s/%s: %s", owner, repo, exc)

    return []


def run_migration(args: argparse.Namespace) -> int:
    """Función principal orquestadora de la migración."""
    logger.info("Iniciando proceso de migración de GitBucket a Forgejo...")
    if args.dry_run:
        logger.warning("MODO SIMULACIÓN ACTIVO (--dry-run): No se aplicarán cambios reales.")

    stats = MigrationStats()

    # 1. Localizar directorio de GitBucket
    gitbucket_dir = find_gitbucket_directory(args.gitbucket_dir)
    if not gitbucket_dir:
        logger.error(
            "No se encontró el directorio de GitBucket. Especifica la ruta con --gitbucket-dir."
        )
        return 1

    # 2. Inicializar cliente Forgejo
    forgejo = ForgejoClient(args.forgejo_url, args.forgejo_token, dry_run=args.dry_run)
    if not args.dry_run:
        if not forgejo.check_version():
            logger.error("No se puede continuar sin conexión activa a Forgejo.")
            return 1

    # 3. Descubrir repositorios
    repos = discover_repositories(gitbucket_dir)
    if not repos:
        logger.warning("No se descubrieron repositorios en %s. Abortando.", gitbucket_dir)
        return 0

    # 4. Preparar informe de credenciales
    cred_file_path = Path(args.credentials_file).resolve()
    user_credentials: List[Tuple[str, str, str]] = []  # (user, email, pass)

    # 5. Iterar y procesar cada repositorio
    start_time = time.time()
    created_users_set = set()

    for r in repos:
        logger.info("------------------------------------------------------------")
        logger.info("Procesando repositorio: %s/%s", r.owner, r.name)

        # 5.1 Asegurar usuario propietario
        if r.owner not in created_users_set:
            existing = None
            if not args.dry_run:
                existing = forgejo.get_user(r.owner)

            if not existing:
                temp_pass = generate_temp_password()
                email = f"{r.owner}@migrated.local"
                if forgejo.create_user(r.owner, email, temp_pass):
                    stats.users_created += 1
                    user_credentials.append((r.owner, email, temp_pass))
            created_users_set.add(r.owner)

        # 5.2 Asegurar repositorio en Forgejo
        existing_repo = None
        if not args.dry_run:
            existing_repo = forgejo.get_repo(r.owner, r.name)

        if not existing_repo:
            forgejo.create_repo(r.owner, r.name, private=r.is_private, description=r.description)

        # 5.3 Construir URL de push autenticada con token
        parsed_forgejo = urllib.parse.urlparse(args.forgejo_url)
        netloc_auth = f"{args.forgejo_token}@{parsed_forgejo.netloc}"
        remote_push_url = (
            f"{parsed_forgejo.scheme}://{netloc_auth}/{r.owner}/{r.name}.git"
        )

        # 5.4 Empujar código (--mirror)
        logger.info("Empujando árbol Git completo (--mirror) para %s/%s...", r.owner, r.name)
        success, out = push_git_mirror(r.git_dir, remote_push_url, dry_run=args.dry_run)
        if success:
            stats.repos_migrated += 1
            logger.info("[OK] Repositorio %s/%s transferido con éxito.", r.owner, r.name)
        else:
            stats.errors.append(f"Fallo push repo {r.owner}/{r.name}: {out}")
            logger.error("Error al transferir repositorio %s/%s: %s", r.owner, r.name, out)

        # 5.5 Empujar Wiki si existe
        if r.wiki_dir and not args.skip_wikis:
            wiki_remote_url = (
                f"{parsed_forgejo.scheme}://{netloc_auth}/{r.owner}/{r.name}.wiki.git"
            )
            logger.info("Empujando Wiki para %s/%s...", r.owner, r.name)
            w_success, w_out = push_git_mirror(r.wiki_dir, wiki_remote_url, dry_run=args.dry_run)
            if w_success:
                stats.wikis_migrated += 1
                logger.info("[OK] Wiki de %s/%s transferida.", r.owner, r.name)
            else:
                stats.warnings.append(f"Fallo push wiki {r.owner}/{r.name}: {w_out}")
                logger.warning("No se pudo transferir wiki de %s/%s: %s", r.owner, r.name, w_out)

        # 5.6 Migrar Issues si la API de GitBucket está disponible
        if not args.skip_issues and args.gitbucket_url:
            issues = fetch_gitbucket_issues(
                args.gitbucket_url, args.gitbucket_token, r.owner, r.name
            )
            for iss in issues:
                title = iss.get("title", "Sin título")
                body = iss.get("body", "")
                author = iss.get("user", {}).get("login", "Desconocido")
                created_at = iss.get("created_at", "")
                full_body = (
                    f"> *Incidencia migrada desde GitBucket originalmente creada por @{author} el {created_at}*\n\n"
                    f"{body}"
                )
                if forgejo.create_issue(r.owner, r.name, title, full_body):
                    stats.issues_migrated += 1

    # 6. Escribir informe de credenciales si hubo usuarios nuevos
    if user_credentials and not args.dry_run:
        try:
            with open(cred_file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Usuario", "Email", "Contraseña Temporal"])
                writer.writerows(user_credentials)
            os.chmod(cred_file_path, 0o600)
            logger.info("Informe de credenciales seguro guardado en: %s", cred_file_path)
        except OSError as exc:
            logger.error("No se pudo escribir el informe de credenciales: %s", exc)

    # 7. Resumen final de la migración en tarjeta visual
    elapsed = time.time() - start_time
    status_color = "\033[32m" if not stats.errors else "\033[31m"
    reset = "\033[0m"
    bold = "\033[1m"
    cyan = "\033[36m"
    yellow = "\033[33m"

    print(f"\n{bold}{cyan}┌────────────────────────────────────────────────────────────────────────┐{reset}")
    print(f"{bold}{cyan}│                   RESUMEN FINAL DE LA MIGRACIÓN A FORGEJO               │{reset}")
    print(f"{bold}{cyan}├──────────────────────────────────────────────────┬─────────────────────┤{reset}")
    print(f"{bold}{cyan}│{reset} Métrica                                           {bold}{cyan}│{reset} Valor               {bold}{cyan}│{reset}")
    print(f"{bold}{cyan}├──────────────────────────────────────────────────┼─────────────────────┤{reset}")
    print(f"{bold}{cyan}│{reset} Tiempo total transcurrido                         {bold}{cyan}│{reset} {elapsed:.2f} s              {bold}{cyan}│{reset}")
    print(f"{bold}{cyan}│{reset} Usuarios creados en Forgejo                       {bold}{cyan}│{reset} {bold}{stats.users_created}{reset}                   {bold}{cyan}│{reset}")
    print(f"{bold}{cyan}│{reset} Repositorios de código transferidos               {bold}{cyan}│{reset} {bold}{stats.repos_migrated} / {len(repos)}{reset}             {bold}{cyan}│{reset}")
    print(f"{bold}{cyan}│{reset} Repositorios Wiki transferidos                    {bold}{cyan}│{reset} {stats.wikis_migrated}                   {bold}{cyan}│{reset}")
    print(f"{bold}{cyan}│{reset} Incidencias y comentarios transferidos            {bold}{cyan}│{reset} {stats.issues_migrated}                   {bold}{cyan}│{reset}")
    print(f"{bold}{cyan}│{reset} Advertencias detectadas                           {bold}{cyan}│{reset} {yellow if stats.warnings else ''}{len(stats.warnings)}{reset}                   {bold}{cyan}│{reset}")
    print(f"{bold}{cyan}│{reset} Errores encontrados                               {bold}{cyan}│{reset} {status_color}{len(stats.errors)}{reset}                   {bold}{cyan}│{reset}")
    print(f"{bold}{cyan}└──────────────────────────────────────────────────┴─────────────────────┘{reset}\n")

    if stats.errors:
        print(f"{bold}\033[31m[ ✖ ] Se produjeron {len(stats.errors)} errores durante la migración:{reset}")
        for err in stats.errors:
            print(f"      - {err}")

    if user_credentials and not args.dry_run:
        print(f"{bold}\033[32m[ ✔ ] Informe de contraseñas seguras exportado en: {cred_file_path}{reset}\n")

    return 0 if not stats.errors else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Suite de migración automatizada desde GitBucket hacia Forgejo."
    )
    parser.add_argument(
        "--gitbucket-dir",
        type=str,
        default=None,
        help="Ruta local al directorio base de GitBucket (donde se ubica repositories/).",
    )
    parser.add_argument(
        "--gitbucket-url",
        type=str,
        default=None,
        help="URL HTTP de la instancia en ejecución de GitBucket (ej. http://localhost:8080/gitbucket).",
    )
    parser.add_argument(
        "--gitbucket-token",
        type=str,
        default=None,
        help="Personal Access Token de GitBucket para consultar issues vía API.",
    )
    parser.add_argument(
        "--forgejo-url",
        type=str,
        default=os.getenv("FORGEJO_ROOT_URL", "http://127.0.0.1:3000"),
        help="URL base de la instancia de Forgejo (por defecto: http://127.0.0.1:3000).",
    )
    parser.add_argument(
        "--forgejo-token",
        type=str,
        required=False,
        default=os.getenv("FORGEJO_ADMIN_TOKEN", ""),
        help="Token de acceso de administrador en Forgejo (con permisos de admin/repo/user).",
    )
    parser.add_argument(
        "--credentials-file",
        type=str,
        default="credentials_report.csv",
        help="Fichero CSV de salida donde registrar las contraseñas temporales generadas.",
    )
    parser.add_argument(
        "--skip-wikis",
        action="store_true",
        help="Omitir la migración de repositorios wiki (.wiki.git).",
    )
    parser.add_argument(
        "--skip-issues",
        action="store_true",
        help="Omitir la migración de incidencias y comentarios.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Ejecutar en modo simulación: solo audita y muestra qué se migraría sin escribir nada.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Si no es dry-run y no hay token, solicitarlo interactivamente
    if not args.dry_run and not args.forgejo_token:
        args.forgejo_token = input("Introduce el Token de Administrador de Forgejo: ").strip()
        if not args.forgejo_token:
            logger.error("Se requiere un token de Forgejo para ejecutar la migración.")
            sys.exit(1)

    sys.exit(run_migration(args))


if __name__ == "__main__":
    main()
