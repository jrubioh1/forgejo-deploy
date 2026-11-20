#!/usr/bin/env python3
"""
manage.py - CLI Integral de Operaciones y Administración de Forgejo en Gentoo Linux.
            Unified Operations & Management CLI for Forgejo on Gentoo Linux.

Soporte Bilingüe / Bilingual Support: Español & English.
Cero dependencias externas / Zero third-party dependencies (Pure Python 3).
"""

from __future__ import annotations

import argparse
import getpass
import os
import pwd
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ==============================================================================
# ESTILOS VISUALES Y TERMINAL ANSI
# ==============================================================================
class UI:
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    MAGENTA = "\033[35m"
    RESET = "\033[0m"

    lang: str = "es"

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
    def header(cls, title: str) -> None:
        line = "─" * (len(title) + 6)
        print(f"\n{cls.BOLD}{cls.CYAN}┌{line}┐{cls.RESET}")
        print(f"{cls.BOLD}{cls.CYAN}│   {title}   │{cls.RESET}")
        print(f"{cls.BOLD}{cls.CYAN}└{line}┘{cls.RESET}\n")

    @classmethod
    def section(cls, title: str) -> None:
        print(f"\n{cls.BOLD}{cls.MAGENTA}── {title} ──────────────────────────────────────────{cls.RESET}")


# ==============================================================================
# CONFIGURACIÓN Y ENTORNO
# ==============================================================================
BASE_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = BASE_DIR / "scripts"


def load_env() -> Dict[str, str]:
    """Carga variables desde el archivo .env sin dependencias externas."""
    env_file = BASE_DIR / ".env"
    env_vars: Dict[str, str] = {}
    if not env_file.exists():
        return env_vars
    try:
        content = env_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip().strip("'\"")
            env_vars[k.strip()] = v
    except OSError as e:
        UI.warn(f"No se pudo leer .env: {e}")
    return env_vars


def get_current_user() -> Tuple[str, int, int]:
    """Retorna (nombre_usuario, UID, GID) del proceso actual."""
    user = getpass.getuser()
    uid = os.geteuid()
    gid = os.getegid()
    return user, uid, gid


def get_service_user() -> str:
    """Detecta el usuario de ejecución del servicio (desde /etc/conf.d/forgejo o .env)."""
    conf_d = Path("/etc/conf.d/forgejo")
    if conf_d.exists():
        try:
            for line in conf_d.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("FORGEJO_USER="):
                    user = line.split("=", 1)[1].strip().strip("'\"")
                    if user:
                        return user
        except OSError:
            pass

    env = load_env()
    if env.get("FORGEJO_SERVICE_USER"):
        return env["FORGEJO_SERVICE_USER"]

    for d in [BASE_DIR / "data", BASE_DIR / "postgres"]:
        if d.exists():
            try:
                st = d.stat()
                return pwd.getpwuid(st.st_uid).pw_name
            except Exception:
                pass

    return getpass.getuser()


def get_execution_cmd(cmd: List[str]) -> List[str]:
    """Si el script se ejecuta como root pero el servicio pertenece a un usuario no privilegiado,
    envuelve el comando con runuser para operar sobre su almacenamiento rootless de Podman."""
    if os.geteuid() == 0:
        svc_user = get_service_user()
        if svc_user != "root":
            try:
                pw = pwd.getpwnam(svc_user)
                runtime_dir = f"/run/user/{pw.pw_uid}"
                if not Path(runtime_dir).exists():
                    os.makedirs(runtime_dir, mode=0o700, exist_ok=True)
                    shutil.chown(runtime_dir, user=svc_user, group=svc_user)
                return [
                    "runuser", "-u", svc_user, "--", "env",
                    f"XDG_RUNTIME_DIR={runtime_dir}",
                    f"HOME={pw.pw_dir}",
                    f"USER={svc_user}",
                ] + cmd
            except (KeyError, OSError):
                pass
    return cmd


def run_cmd(cmd: List[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess[str]:
    """Ejecuta un comando en el directorio base del proyecto con cambio transparente de usuario si aplica."""
    exec_cmd = get_execution_cmd(cmd)
    try:
        return subprocess.run(
            exec_cmd,
            cwd=str(BASE_DIR),
            check=check,
            capture_output=capture,
            text=True,
        )
    except FileNotFoundError:
        UI.err(f"Comando no encontrado en el sistema: '{exec_cmd[0]}'")
        sys.exit(127)
    except subprocess.CalledProcessError as e:
        if not capture:
            UI.err(f"El comando '{' '.join(exec_cmd)}' falló con código de salida {e.returncode}")
        raise


def run_privileged(cmd: List[str]) -> bool:
    """Ejecuta un comando con elevación de privilegios (sudo/doas) si no se es root."""
    if os.geteuid() == 0:
        res = subprocess.run(cmd, cwd=str(BASE_DIR))
        return res.returncode == 0
    sudo = shutil.which("sudo")
    if sudo:
        res = subprocess.run([sudo] + cmd, cwd=str(BASE_DIR))
        return res.returncode == 0
    doas = shutil.which("doas")
    if doas:
        res = subprocess.run([doas] + cmd, cwd=str(BASE_DIR))
        return res.returncode == 0
    UI.err("Se requieren privilegios de superusuario y no se encontró sudo ni doas.")
    return False


# ==============================================================================
# SUBCOMANDOS OPERATIVOS
# ==============================================================================
def check_volume_permissions(auto_warn: bool = True) -> bool:
    """Verifica si el usuario del servicio tiene acceso a data/ y postgres/."""
    svc_user = get_service_user()
    try:
        target_uid = pwd.getpwnam(svc_user).pw_uid
    except Exception:
        target_uid = os.geteuid()

    data_dir = BASE_DIR / "data"
    pg_dir = BASE_DIR / "postgres"
    issues: List[str] = []

    for d in [data_dir, pg_dir]:
        if not d.exists():
            continue
        try:
            st = d.stat()
            if os.geteuid() != 0 and st.st_uid != target_uid:
                issues.append(f"{d.name}/ (Dueño UID: {st.st_uid}, Requerido UID: {target_uid} [{svc_user}])")
        except OSError:
            issues.append(f"{d.name}/ (Permiso denegado)")

    if issues:
        if auto_warn:
            UI.err("¡Conflicto de permisos detectado en los volúmenes!")
            for issue in issues:
                print(f"    • {issue}")
            UI.warn("El servicio no podrá escribir en los datos. El arranque de Podman fallará.")
            UI.info("Para solucionarlo automáticamente ejecuta:")
            print(f"      {UI.BOLD}{UI.CYAN}./manage.py fix-permissions{UI.RESET}\n")
        return False
    return True


def cmd_fix_permissions(args: argparse.Namespace) -> None:
    """Ajusta la propiedad y permisos de ./data y ./postgres al usuario deseado."""
    target_user = args.user or getpass.getuser()
    UI.header("CORRECCIÓN DE PERMISOS DE VOLÚMENES PODMAN")
    UI.info(f"Asignando propiedad de './data' y './postgres' al usuario: {UI.BOLD}{target_user}{UI.RESET}")

    # Verificar que el usuario exista
    try:
        user_info = subprocess.run(["id", target_user], capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError:
        UI.err(f"El usuario '{target_user}' no existe en el sistema.")
        sys.exit(1)

    data_dir = BASE_DIR / "data"
    pg_dir = BASE_DIR / "postgres"

    # Crear directorios si no existen
    for d in [data_dir, pg_dir]:
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)

    success = run_privileged(["chown", "-R", f"{target_user}:{target_user}", str(data_dir), str(pg_dir)])
    if not success:
        UI.err("No se pudieron cambiar los propietarios con privilegios.")
        sys.exit(1)

    run_privileged(["chmod", "0700", str(data_dir), str(pg_dir)])

    # Ajustar .env para que target_user pueda leerlo
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        current_user = getpass.getuser()
        if target_user != current_user and target_user != "root":
            run_privileged(["chown", f"{current_user}:{target_user}", str(env_file)])
            run_privileged(["chmod", "0640", str(env_file)])
        else:
            run_privileged(["chmod", "0600", str(env_file)])

    # Si hay SELinux activo, aplicar contextos
    if shutil.which("chcon"):
        run_privileged(["chcon", "-Rt", "container_file_t", str(data_dir), str(pg_dir)])

    UI.ok("Permisos corregidos exitosamente.")
    print(f"  • {data_dir} -> {target_user}:{target_user} (0700)")
    print(f"  • {pg_dir} -> {target_user}:{target_user} (0700)")
    UI.info("Ahora puedes iniciar el stack con: ./manage.py start")


def wait_for_http_ready(url: str, timeout: int = 15) -> bool:
    """Espera activamente a que Forgejo responda HTTP 200/301/302 tras arrancar."""
    curl_bin = shutil.which("curl")
    if not curl_bin:
        return False
    start_time = time.time()
    sys.stdout.write(" Esperando inicialización del servidor Forgejo")
    sys.stdout.flush()
    while time.time() - start_time < timeout:
        res = subprocess.run(
            [curl_bin, "-s", "-o", "/dev/null", "-w", "%{http_code}", url],
            capture_output=True,
            text=True,
        )
        if res.stdout.strip() in ("200", "301", "302"):
            sys.stdout.write(" [Listo]\n")
            sys.stdout.flush()
            return True
        sys.stdout.write(".")
        sys.stdout.flush()
        time.sleep(1)
    sys.stdout.write(" [Iniciando en segundo plano]\n")
    sys.stdout.flush()
    return False


def cmd_start(args: argparse.Namespace) -> None:
    """Inicia el stack de contenedores de Forgejo."""
    env = load_env()
    if not (BASE_DIR / ".env").exists():
        UI.err("No se encontró el archivo .env. Ejecuta primero ./setup.sh para configurar el sistema.")
        sys.exit(1)

    if not check_volume_permissions(auto_warn=True):
        if not args.force:
            UI.err("Arranque cancelado para evitar errores de crun. Usa --force si deseas ignorar.")
            sys.exit(1)

    UI.info("Iniciando stack de Forgejo en Gentoo Linux...")

    # Limpiar posibles contenedores en estado fallido previo
    run_cmd(["podman", "rm", "-f", "forgejo-app", "forgejo-db"], check=False)

    # Túnel SSH si está habilitado
    if env.get("SSH_TUNNEL_ENABLED", "false").lower() == "true":
        tunnel_sh = SCRIPTS_DIR / "tunnel-db.sh"
        if tunnel_sh.exists():
            subprocess.run([str(tunnel_sh), "start"])

    # Ejecutar podman-compose up -d
    try:
        run_cmd(["podman-compose", "up", "-d"])
        UI.ok("Stack levantado exitosamente en segundo plano.")
    except subprocess.CalledProcessError:
        UI.err("Falló el arranque con podman-compose up -d.")
        sys.exit(1)

    # Espera activa para que el usuario no vea código 000 engañoso
    http_port = env.get("FORGEJO_HTTP_PORT", "3000")
    bind_ip = env.get("FORGEJO_BIND_IP", "0.0.0.0")
    test_ip = "127.0.0.1" if bind_ip in ("0.0.0.0", "127.0.0.1") else bind_ip
    test_url = f"http://{test_ip}:{http_port}/"
    wait_for_http_ready(test_url, timeout=12)

    # Mostrar estado detallado
    print("")
    cmd_status(args)


def cmd_down(args: argparse.Namespace) -> None:
    """Detiene y elimina los contenedores y la red de Forgejo sin tocar los datos."""
    UI.info("Deteniendo y eliminando contenedores y red de Forgejo...")
    env = load_env()
    try:
        run_cmd(["podman-compose", "down", "--timeout", "30"])
    except subprocess.CalledProcessError:
        pass
    run_cmd(["podman", "rm", "-f", "forgejo-app", "forgejo-db"], check=False)
    if env.get("SSH_TUNNEL_ENABLED", "false").lower() == "true":
        tunnel_sh = SCRIPTS_DIR / "tunnel-db.sh"
        if tunnel_sh.exists():
            subprocess.run([str(tunnel_sh), "stop"])
    UI.ok("Contenedores 'forgejo-app' y 'forgejo-db' eliminados. Puertos y memoria liberados.")
    UI.info("Tus repositorios y base de datos en ./data y ./postgres siguen 100% intactos.")


def cmd_stop(args: argparse.Namespace) -> None:
    """Detiene el stack con gracia de 30 segundos."""
    UI.info("Deteniendo stack de Forgejo ordenadamente (timeout: 30s)...")
    env = load_env()

    try:
        run_cmd(["podman-compose", "down", "--timeout", "30"])
        UI.ok("Stack de Forgejo detenido y recursos liberados.")
    except subprocess.CalledProcessError:
        UI.warn("podman-compose down reportó advertencias, forzando limpieza de contenedores...")
        run_cmd(["podman", "rm", "-f", "forgejo-app", "forgejo-db"], check=False)

    # Limpieza de seguridad
    run_cmd(["podman", "rm", "-f", "forgejo-app", "forgejo-db"], check=False)

    if env.get("SSH_TUNNEL_ENABLED", "false").lower() == "true":
        tunnel_sh = SCRIPTS_DIR / "tunnel-db.sh"
        if tunnel_sh.exists():
            subprocess.run([str(tunnel_sh), "stop"])


def cmd_restart(args: argparse.Namespace) -> None:
    """Reinicia el stack de contenedores."""
    cmd_stop(args)
    time.sleep(1)
    cmd_start(args)


def cmd_status(args: argparse.Namespace) -> None:
    """Muestra el estado detallado de los contenedores, base de datos y acceso web."""
    UI.header("ESTADO DEL SERVICIO FORGEJO EN GENTOO")
    env = load_env()

    UI.section("Contenedores Podman")
    try:
        run_cmd(["podman-compose", "ps"])
    except subprocess.CalledProcessError:
        UI.warn("No se pudo obtener el estado desde podman-compose.")

    # Comprobación de Base de Datos
    db_mode = env.get("DB_MODE", "local")
    if db_mode == "local":
        UI.section("Salud de PostgreSQL Local")
        res = run_cmd(["podman", "ps", "--format", "{{.Names}}"], check=False, capture=True)
        if "forgejo-db" in res.stdout:
            pg_user = env.get("POSTGRES_USER", "forgejo")
            pg_db = env.get("POSTGRES_DB", "forgejo")
            chk = run_cmd(
                ["podman", "exec", "-i", "forgejo-db", "pg_isready", "-U", pg_user, "-d", pg_db],
                check=False,
                capture=True,
            )
            if chk.returncode == 0:
                UI.ok("PostgreSQL respondiendo y listo para conexiones.")
            else:
                UI.warn("PostgreSQL está arrancando o no responde a pg_isready.")
        else:
            UI.err("El contenedor 'forgejo-db' no se encuentra en ejecución.")
    else:
        UI.section("Base de Datos Externa")
        UI.info(f"Modo DB_MODE=remote activo hacia: {env.get('FORGEJO_DB_HOST', 'desconocido')}")

    # Comprobación HTTP
    UI.section("Comprobación de Acceso HTTP")
    http_port = env.get("FORGEJO_HTTP_PORT", "3000")
    bind_ip = env.get("FORGEJO_BIND_IP", "0.0.0.0")
    test_ip = "127.0.0.1" if bind_ip in ("0.0.0.0", "127.0.0.1") else bind_ip
    test_url = f"http://{test_ip}:{http_port}/"

    curl_bin = shutil.which("curl")
    if curl_bin:
        curl_res = subprocess.run(
            [curl_bin, "-s", "-o", "/dev/null", "-w", "%{http_code}", test_url],
            capture_output=True,
            text=True,
        )
        code = curl_res.stdout.strip()
        if code in ("200", "301", "302"):
            UI.ok(f"Forgejo respondiendo en {test_url} (Código HTTP: {UI.BOLD}{UI.GREEN}{code}{UI.RESET})")
        else:
            UI.warn(f"Forgejo aún no responde en {test_url} (Código: {code or 'Sin respuesta'})")
    else:
        UI.info(f"Accede a Forgejo en: {test_url}")

    # Almacenamiento y Recursos OCI Podman
    UI.section("Almacenamiento y Recursos OCI (Usuario de Servicio)")
    run_cmd(["podman", "system", "df"], check=False)
    print("")


def cmd_logs(args: argparse.Namespace) -> None:
    """Muestra y sigue los registros de los contenedores."""
    cmd = ["podman-compose", "logs", "-f"]
    if args.service:
        cmd.append(args.service)
    try:
        run_cmd(cmd)
    except KeyboardInterrupt:
        print("\nSeguimiento de registros finalizado.")


def cmd_backup(args: argparse.Namespace) -> None:
    """Copia de seguridad consistente de base de datos y almacenamiento."""
    env = load_env()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = BASE_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    UI.header("COPIA DE SEGURIDAD PREVENTIVA")
    UI.info(f"Directorio de respaldos: {backup_dir}")

    # 1. Backup de PostgreSQL
    if env.get("DB_MODE", "local") == "local":
        sql_file = backup_dir / f"db-forgejo-{timestamp}.sql.gz"
        UI.info(f"Exportando base de datos hacia: {UI.CYAN}{sql_file.name}{UI.RESET}")
        pg_user = env.get("POSTGRES_USER", "forgejo")
        pg_db = env.get("POSTGRES_DB", "forgejo")
        try:
            pg_dump_cmd = get_execution_cmd(
                ["podman", "exec", "-i", "forgejo-db", "pg_dump", "-U", pg_user, pg_db]
            )
            dump_proc = subprocess.Popen(
                pg_dump_cmd,
                stdout=subprocess.PIPE,
            )
            gzip_proc = subprocess.Popen(["gzip"], stdin=dump_proc.stdout, stdout=subprocess.PIPE)
            if dump_proc.stdout:
                dump_proc.stdout.close()
            with open(sql_file, "wb") as f:
                if gzip_proc.stdout:
                    shutil.copyfileobj(gzip_proc.stdout, f)
            gzip_proc.wait()
            dump_proc.wait()
            if dump_proc.returncode == 0 and gzip_proc.returncode == 0:
                UI.ok("Base de datos exportada y comprimida correctamente.")
            else:
                UI.err("Error durante el volcado de la base de datos.")
        except OSError as e:
            UI.err(f"Fallo al ejecutar pg_dump/gzip: {e}")
    else:
        UI.info("Base de datos remota: gestiona el respaldo en el servidor de base de datos central.")

    # 2. Backup de Repositorios y Datos
    data_file = backup_dir / f"data-forgejo-{timestamp}.tar.gz"
    UI.info(f"Empaquetando repositorios hacia: {UI.CYAN}{data_file.name}{UI.RESET}")
    try:
        tar_proc = subprocess.run(
            ["tar", "-czf", str(data_file), "-C", str(BASE_DIR), "data/"],
            capture_output=True,
            text=True,
        )
        if tar_proc.returncode == 0:
            UI.ok("Almacenamiento de Forgejo empaquetado correctamente.")
        else:
            UI.err(f"Error al empaquetar data/: {tar_proc.stderr}")
    except OSError as e:
        UI.err(f"Fallo al invocar tar: {e}")

    print("")
    UI.ok("Respaldo completado.")
    for f in backup_dir.glob(f"*{timestamp}*"):
        size_mb = f.stat().st_size / (1024 * 1024)
        print(f"  • {f.name} ({size_mb:.2f} MB)")


def cmd_create_admin(args: argparse.Namespace) -> None:
    """Asistente interactivo para crear un usuario administrador de Forgejo."""
    UI.header("CREACIÓN DE ADMINISTRADOR EN FORGEJO")
    username = input(" Nombre de usuario administrador [admin]: ").strip() or "admin"
    email = input(" Correo electrónico [admin@local.domain]: ").strip() or "admin@local.domain"
    password = getpass.getpass(" Contraseña para el administrador: ")

    if not password:
        UI.err("La contraseña no puede estar vacía.")
        sys.exit(1)

    UI.info("Registrando usuario en el contenedor de Forgejo...")
    cmd = [
        "podman", "exec", "-i", "forgejo-app",
        "forgejo", "admin", "user", "create",
        "--username", username,
        "--email", email,
        "--password", password,
        "--admin",
    ]
    try:
        res = run_cmd(cmd, check=True, capture=True)
        UI.ok(f"Administrador '{username}' creado exitosamente.")
        print(f"  {res.stdout.strip()}")
    except subprocess.CalledProcessError as e:
        UI.err(f"No se pudo crear el usuario administrador: {e.stderr.strip() or e.stdout.strip()}")


def cmd_upgrade(args: argparse.Namespace) -> None:
    """Ejecuta el asistente interactivo de actualización en caliente."""
    upgrade_py = SCRIPTS_DIR / "upgrade.py"
    if not upgrade_py.exists():
        UI.err(f"No se encontró el script de actualización en: {upgrade_py}")
        sys.exit(1)
    subprocess.run([sys.executable, str(upgrade_py)] + (["--check"] if args.check else []))


def cmd_cli(args: argparse.Namespace) -> None:
    """Ejecuta comandos CLI directos dentro del contenedor de Forgejo."""
    if not args.cli_args:
        UI.err("Debes proporcionar al menos un comando o subcomando de Forgejo.")
        print("Ejemplo: ./manage.py cli -- help")
        sys.exit(1)
    cmd = ["podman", "exec", "-it", "forgejo-app", "forgejo"] + args.cli_args
    try:
        run_cmd(cmd, check=False)
    except subprocess.CalledProcessError:
        pass


def cmd_podman(args: argparse.Namespace) -> None:
    """Ejecuta cualquier comando Podman nativo en el espacio de almacenamiento del usuario forgejo."""
    if not args.podman_args:
        run_cmd(["podman", "ps", "-a"], check=False)
        return
    cmd = ["podman"] + args.podman_args
    try:
        run_cmd(cmd, check=False)
    except subprocess.CalledProcessError:
        pass


def cmd_prune(args: argparse.Namespace) -> None:
    """Limpia contenedores detenidos, redes huérfanas y capas sin usar."""
    UI.header("LIMPIEZA DE OBJETOS PODMAN HUÉRFANOS (PRUNE)")
    if args.all:
        UI.warn("Modo --all activo: también se eliminarán imágenes no usadas por contenedores activos.")
        confirm = input(" ¿Deseas continuar? [s/N]: ").strip().lower()
        if not (confirm.startswith("s") or confirm.startswith("y")):
            UI.info("Operación cancelada.")
            return
        cmd = ["podman", "system", "prune", "-a", "--force"]
    else:
        cmd = ["podman", "system", "prune", "--force"]

    UI.info("Ejecutando limpieza en el almacenamiento del usuario de servicio...")
    try:
        run_cmd(cmd, check=False)
        UI.ok("Limpieza completada exitosamente.")
    except subprocess.CalledProcessError as e:
        UI.err(f"Error durante prune: {e}")


def cmd_clean_images(args: argparse.Namespace) -> None:
    """Detiene contenedores y elimina las imágenes OCI de Forgejo y Postgres descargadas."""
    UI.header("LIMPIEZA DE IMÁGENES OCI (FORGEJO Y POSTGRESQL)")
    UI.warn("Esta acción eliminará las imágenes locales de Forgejo y PostgreSQL para liberar espacio (~1.5 GB).")
    UI.info("Tus datos y repositorios en ./data y ./postgres NO se verán afectados.")
    confirm = input(" ¿Deseas detener contenedores y eliminar las imágenes? [s/N]: ").strip().lower()
    if not (confirm.startswith("s") or confirm.startswith("y")):
        UI.info("Operación cancelada.")
        return

    # Detener contenedores primero
    run_cmd(["podman", "rm", "-f", "forgejo-app", "forgejo-db"], check=False)

    # Listar imágenes para borrar
    env = load_env()
    forgejo_ver = env.get("FORGEJO_VERSION", "17-rootless")
    images_to_remove = [
        f"codeberg.org/forgejo/forgejo:{forgejo_ver}",
        "docker.io/library/postgres:18",
    ]
    for img in images_to_remove:
        UI.info(f"Eliminando imagen: {img}")
        run_cmd(["podman", "rmi", "-f", img], check=False)

    # Limpieza residual
    run_cmd(["podman", "image", "prune", "-f"], check=False)
    UI.ok("Imágenes eliminadas y espacio liberado.")
    UI.info("La próxima vez que ejecutes './manage.py start', Podman volverá a descargarlas automáticamente.")


def cmd_doctor(args: argparse.Namespace) -> None:
    """Ejecuta una batería completa de diagnósticos del entorno Gentoo y Rootless Podman."""
    UI.header("DIAGNÓSTICO DEL SISTEMA Y ENTORNO (DOCTOR)")
    current_user, current_uid, current_gid = get_current_user()
    UI.info(f"Usuario ejecutor: {current_user} (UID: {current_uid}, GID: {current_gid})")

    # 1. Comprobar cgroups v2
    cgroup_v2 = Path("/sys/fs/cgroup/cgroup.controllers").exists()
    if cgroup_v2:
        UI.ok("cgroups v2 activo en el kernel Gentoo.")
    else:
        UI.warn("cgroups v2 no detectado en /sys/fs/cgroup (puede limitar métricas en Podman).")

    # 2. Comprobar runtime crun
    crun_bin = shutil.which("crun")
    if crun_bin:
        crun_ver = subprocess.run([crun_bin, "--version"], capture_output=True, text=True).stdout.splitlines()[0]
        UI.ok(f"Runtime OCI: {crun_ver}")
    else:
        UI.err("No se encontró el binario 'crun'.")

    # 3. Comprobar /etc/subuid y /etc/subgid
    has_subuid = False
    has_subgid = False
    for p, name in [("/etc/subuid", "subuid"), ("/etc/subgid", "subgid")]:
        f = Path(p)
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.startswith(f"{current_user}:") or line.startswith(f"{current_uid}:"):
                    if name == "subuid":
                        has_subuid = True
                    else:
                        has_subgid = True
    if has_subuid and has_subgid:
        UI.ok(f"Rangos de IDs subordinados configurados en /etc/subuid y /etc/subgid para {current_user}.")
    else:
        UI.warn(f"No se detectaron rangos subordinados completos para {current_user} en /etc/subuid o /etc/subgid.")

    # 4. Comprobar permisos en volúmenes
    perms_ok = check_volume_permissions(auto_warn=False)
    if perms_ok:
        UI.ok("Permisos de ./data y ./postgres correctos y accesibles por el usuario.")
    else:
        UI.err("Permisos de volúmenes incorrectos. Ejecuta: ./manage.py fix-permissions")

    # 5. Comprobar .env y variables clave
    env = load_env()
    if not env:
        UI.err("Archivo .env inexistente o vacío. Ejecuta ./setup.sh para configurarlo.")
    else:
        UI.ok("Archivo .env encontrado y cargado.")
        checks = [
            ("FORGEJO_VERSION", env.get("FORGEJO_VERSION")),
            ("POSTGRES_PASSWORD", "Configurado" if env.get("POSTGRES_PASSWORD") else None),
            ("PGDATA", env.get("PGDATA")),
            ("FORGEJO_HTTP_PORT", env.get("FORGEJO_HTTP_PORT")),
        ]
        for var_name, val in checks:
            if val:
                print(f"    • {var_name}: {val}")
            else:
                UI.warn(f"Variable {var_name} no definida en .env.")

    # 6. Comprobar daemon de podman
    pod_info = run_cmd(["podman", "info", "--format", "{{.Host.Security.Rootless}}"], check=False, capture=True)
    if pod_info.returncode == 0:
        is_rootless = pod_info.stdout.strip().lower() == "true"
        UI.ok(f"Podman funcionando en modo: {'Rootless (100% Seguro y Aislado)' if is_rootless else 'Root'}")
    else:
        UI.err("Podman no responde adecuadamente a 'podman info'.")

    print("")


def cmd_install_cli(args: argparse.Namespace) -> None:
    """Instala el comando global 'forgejo' en /usr/local/bin/forgejo."""
    target_path = Path("/usr/local/bin/forgejo")
    manage_py = BASE_DIR / "manage.py"

    script_content = f"""#!/usr/bin/env bash
# ==============================================================================
# /usr/local/bin/forgejo - CLI global de administración de Forgejo en Gentoo
# ==============================================================================
set -euo pipefail
exec "{manage_py}" "$@"
"""
    UI.header("INSTALACIÓN DEL COMANDO GLOBAL 'forgejo'")
    if os.geteuid() == 0:
        try:
            target_path.write_text(script_content, encoding="utf-8")
            target_path.chmod(0o755)
            UI.ok(f"Comando global instalado exitosamente en: {target_path}")
            UI.info("Ahora puedes ejecutar desde cualquier lugar: 'forgejo status', 'forgejo logs', etc.")
        except OSError as e:
            UI.err(f"Error escribiendo en {target_path}: {e}")
    else:
        tmp_script = f"/tmp/forgejo_wrapper_{int(time.time())}.sh"
        try:
            Path(tmp_script).write_text(script_content, encoding="utf-8")
            Path(tmp_script).chmod(0o755)
            success = run_privileged(["cp", tmp_script, str(target_path)])
            run_privileged(["chmod", "0755", str(target_path)])
            try:
                os.remove(tmp_script)
            except OSError:
                pass
            if success:
                UI.ok(f"Comando global instalado exitosamente en: {target_path}")
                UI.info("Ahora puedes ejecutar desde cualquier lugar: 'forgejo status', 'forgejo logs', etc.")
            else:
                UI.err(f"No se pudo instalar en {target_path}. Requiere elevación de privilegios.")
        except OSError as e:
            UI.err(f"Error preparando instalador: {e}")


def cmd_uninstall(args: argparse.Namespace) -> None:
    """Desinstala el servicio OpenRC y revierte la configuración."""
    setup_py = BASE_DIR / "setup.py"
    if setup_py.exists():
        subprocess.run([sys.executable, str(setup_py), "--revert"])
    else:
        UI.err(f"No se encontró setup.py en {setup_py}")


# ==============================================================================
# PARSER PRINCIPAL DE ARGUMENTOS CLI
# ==============================================================================
def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="manage.py",
        description="CLI de Operaciones y Administración de Forgejo en Gentoo Linux (Podman Rootless).",
        epilog="Ejemplo: ./manage.py start  |  ./manage.py status  |  ./manage.py doctor",
    )

    subparsers = parser.add_subparsers(dest="command", help="Comandos disponibles / Available commands")

    # start
    p_start = subparsers.add_parser("start", help="Inicia los contenedores de Forgejo y Base de Datos")
    p_start.add_argument("-f", "--force", action="store_true", help="Ignora advertencias de permisos e intenta arrancar")

    # stop
    subparsers.add_parser("stop", help="Detiene los contenedores con gracia de 30 segundos")

    # down
    subparsers.add_parser("down", help="Detiene y elimina contenedores y redes OCI (datos en ./data y ./postgres intactos)")

    # restart
    subparsers.add_parser("restart", help="Reinicia limpiamente todos los servicios")

    # status
    subparsers.add_parser("status", help="Muestra el estado de contenedores, puertos y salud")

    # logs
    p_logs = subparsers.add_parser("logs", help="Muestra y sigue los registros de los contenedores en tiempo real")
    p_logs.add_argument("service", nargs="?", help="Servicio específico (opcional: server, db)")

    # backup
    subparsers.add_parser("backup", help="Crea una copia de seguridad consistente de la base de datos y repositorios")

    # create-admin
    subparsers.add_parser("create-admin", help="Asistente interactivo para crear un usuario administrador de Forgejo")

    # upgrade
    p_upg = subparsers.add_parser("upgrade", help="Asistente interactivo de actualización en caliente sin tiempo de inactividad")
    p_upg.add_argument("--check", action="store_true", help="Solo comprueba si existen nuevas versiones sin actualizar")

    # fix-permissions
    p_fix = subparsers.add_parser("fix-permissions", help="Corrige propiedad y permisos de ./data y ./postgres")
    p_fix.add_argument("-u", "--user", help="Usuario de destino (por defecto el usuario actual)")

    # doctor
    subparsers.add_parser("doctor", help="Diagnóstico integral del kernel Gentoo, cgroups, Podman rootless y permisos")

    # prune
    p_prune = subparsers.add_parser("prune", help="Limpia contenedores detenidos, redes huérfanas y capas sin usar")
    p_prune.add_argument("-a", "--all", action="store_true", help="Elimina también imágenes no usadas")

    # clean-images
    subparsers.add_parser("clean-images", help="Elimina las imágenes locales de Forgejo y PostgreSQL para liberar espacio")

    # podman
    p_podman = subparsers.add_parser("podman", help="Passthrough directo a Podman en el almacenamiento del usuario de servicio")
    p_podman.add_argument("podman_args", nargs=argparse.REMAINDER, help="Argumentos pasados directamente a podman")

    # cli
    p_cli = subparsers.add_parser("cli", help="Ejecuta comandos internos de la CLI de Forgejo dentro del contenedor")
    p_cli.add_argument("cli_args", nargs=argparse.REMAINDER, help="Argumentos pasados directamente al binario forgejo")

    # install-cli
    subparsers.add_parser("install-cli", help="Instala el comando global 'forgejo' en /usr/local/bin/forgejo")

    # uninstall / revert
    subparsers.add_parser("uninstall", help="Desinstala el servicio OpenRC y revierte la configuración")
    subparsers.add_parser("revert", help="Alias de uninstall")

    return parser


def main() -> None:
    # 1. Atajo directo para comandos nativos de Podman en el usuario de servicio:
    # Ej: forgejo ps -a, forgejo images, forgejo rm -f ...
    podman_direct = {"ps", "images", "rm", "rmi", "inspect", "top", "stats", "system", "volume", "network"}
    if len(sys.argv) > 1 and sys.argv[1] in podman_direct:
        cmd = ["podman"] + sys.argv[1:]
        res = run_cmd(cmd, check=False)
        sys.exit(res.returncode)

    # 2. Soporte para comandos nativos de Forgejo:
    # Ej: forgejo admin user list
    known_commands = {
        "start", "stop", "down", "restart", "status", "logs", "backup",
        "create-admin", "upgrade", "fix-permissions", "doctor",
        "prune", "clean-images", "podman", "cli", "install-cli",
        "uninstall", "revert", "-h", "--help",
    }
    if len(sys.argv) > 1 and sys.argv[1] not in known_commands and not sys.argv[1].startswith("-"):
        cli_args = sys.argv[1:]
        cmd = ["podman", "exec", "-it", "forgejo-app", "forgejo"] + cli_args
        try:
            res = run_cmd(cmd, check=False)
            sys.exit(res.returncode)
        except subprocess.CalledProcessError as e:
            sys.exit(e.returncode)

    parser = create_parser()

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    commands = {
        "start": cmd_start,
        "stop": cmd_stop,
        "down": cmd_down,
        "restart": cmd_restart,
        "status": cmd_status,
        "logs": cmd_logs,
        "backup": cmd_backup,
        "create-admin": cmd_create_admin,
        "upgrade": cmd_upgrade,
        "fix-permissions": cmd_fix_permissions,
        "doctor": cmd_doctor,
        "prune": cmd_prune,
        "clean-images": cmd_clean_images,
        "podman": cmd_podman,
        "cli": cmd_cli,
        "install-cli": cmd_install_cli,
        "uninstall": cmd_uninstall,
        "revert": cmd_uninstall,
    }

    cmd_fn = commands.get(args.command)
    if cmd_fn:
        cmd_fn(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
