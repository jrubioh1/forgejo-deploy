# Guía de Diagnóstico y Resolución de Incidencias (Troubleshooting)

Este manual aborda los problemas más comunes al operar **Forgejo** en Gentoo Linux y proporciona procedimientos claros para su diagnóstico y resolución.

---

## 1. Problemas de Red y Puertos

### 1.1. El puerto 3000 o 2222 ya está en uso
* **Síntoma:** Al arrancar el stack, Podman muestra el error:  
  `Error: rootlessport: bind: address already in use`
* **Diagnóstico:**
  Comprueba qué proceso del servidor Gentoo está ocupando el puerto:
  ```bash
  ss -tlpn | grep -E ':(3000|2222)'
  ```
* **Solución:**
  Edita el archivo `.env` y cambia los puertos a valores libres:
  ```bash
  FORGEJO_HTTP_PORT=3001
  FORGEJO_SSH_PORT=2223
  ```
  Reinicia el servicio:
  ```bash
  ./scripts/manage.sh restart
  ```

---

## 2. Base de Datos y Túnel SSH

### 2.1. Forgejo no puede conectar a la base de datos local
* **Síntoma:** Los logs muestran `[FATAL] Failed to initialize ORM engine: dial tcp ... connection refused`.
* **Diagnóstico:**
  Comprueba si el contenedor de PostgreSQL está corriendo y si responde:
  ```bash
  podman ps | grep forgejo-db
  podman exec -it forgejo-db pg_isready -U forgejo -d forgejo
  ```
* **Solución:**
  Revisa los logs específicos de PostgreSQL:
  ```bash
  ./scripts/manage.sh logs db
  ```
  Si el volumen `./postgres` tiene permisos incorrectos, asegúrate de que pertenezca a `root` con permisos `0700` y etiqueta SELinux:
  ```bash
  chcon -R -t container_file_t ./postgres
  ```

### 2.2. Fallo en el Túnel SSH hacia la Base de Datos Remota
* **Síntoma:** `tunnel-db.sh` no logra establecer la conexión o se cae intermitentemente.
* **Diagnóstico:**
  Comprueba el estado del socket del túnel:
  ```bash
  ./scripts/tunnel-db.sh status
  ```
  Prueba la conexión SSH manual con modo detallado (`-vvv`):
  ```bash
  ssh -vvv -i /root/.ssh/id_ed25519 -p 22 root@servidor-bd.remoto.com
  ```
* **Solución:**
  1. Verifica que la clave pública esté en `~/.ssh/authorized_keys` del servidor remoto.
  2. Asegúrate de que el puerto local 5432 no esté siendo usado por un PostgreSQL nativo en Gentoo (`/etc/init.d/postgresql stop` si existe).

---

## 3. Permisos y SELinux en Gentoo Linux

### 3.1. Error de permisos en `./data` (Permission Denied al crear repositorios)
* **Diagnóstico:**
  En Gentoo Hardened, revisa si SELinux ha bloqueado el acceso:
  ```bash
  ausearch -m avc -ts recent 2>/dev/null || true
  ```
* **Solución:**
  Reaplica los contextos SELinux recomendados para contenedores:
  ```bash
  chcon -R -t container_file_t ./data ./postgres
  chmod -R 700 ./data ./postgres
  ```
  Asegúrate de que en `compose.yaml` los volúmenes tengan el sufijo `:Z`.

---

## 4. Problemas en la Migración desde GitBucket

### 4.1. Error 401 o 403 al llamar a la API de Forgejo
* **Causa:** El token de acceso proporcionado a `migrate_gitbucket.py` no tiene suficientes permisos.
* **Solución:**  
  Genera un nuevo token desde la cuenta `admin` en **Configuración de Usuario -> Aplicaciones** marcando todos los permisos (`all`), o al menos:
  - `admin:read`, `admin:write`
  - `repo:read`, `repo:write`
  - `user:read`, `user:write`

### 4.2. Repositorios de gran tamaño tardan mucho o fallan por timeout
* **Solución:**
  Si un repositorio supera varios gigabytes, puedes aumentar el timeout en `scripts/migrate_gitbucket.py` (parámetro `timeout` en `push_git_mirror`) o empujarlo manualmente a través de la red local:
  ```bash
  cd /ruta/gitbucket/repositories/propietario/repo.git
  git push --mirror http://TOKEN@127.0.0.1:3000/propietario/repo.git
  ```

---

## 5. Inspección Rápida de Logs

Para ver los registros en tiempo real en cualquier momento:

```bash
# Todos los logs del stack:
./scripts/manage.sh logs

# Solo logs de Forgejo:
./scripts/manage.sh logs server

# Solo logs de PostgreSQL:
./scripts/manage.sh logs db
```
