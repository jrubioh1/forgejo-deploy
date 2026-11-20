# Despliegue de Forgejo y PostgreSQL en Gentoo Linux (Hardened / OpenRC)

Esta guía documenta el despliegue de **Forgejo** y **PostgreSQL** en **Gentoo Linux** utilizando **Podman**, **OpenRC** y las herramientas de automatización incluidas en este repositorio.

---

## 1. Requisitos Previos en Gentoo

Instala los paquetes necesarios desde Portage:

```bash
# Runtime de contenedores y utilidades
emerge --ask app-containers/podman app-containers/podman-compose dev-vcs/git app-crypt/gnupg openssl

# (Opcional) Si vas a usar Apache como Reverse Proxy
emerge --ask www-servers/apache
```

> **Nota sobre SELinux (Gentoo Hardened):**  
> Si tu kernel tiene SELinux activo (`id -Z` muestra un contexto SELinux), el flag `:Z` en los volúmenes de `compose.yaml` se encargará automáticamente de etiquetar las carpetas `data/` y `postgres/` con el tipo `container_file_t`.

---

## 2. Preparación y Configuración Inicial (`setup.sh`)

1. Clona el repositorio en el servidor Gentoo (en cualquier directorio de tu preferencia, ej. en tu home o `/srv/forgejo-deploy`):
   ```bash
   git clone https://github.com/jrubioh1/forgejo-deploy.git
   cd forgejo-deploy
   ```

2. Ejecuta el asistente interactivo:
   ```bash
   ./setup.sh
   # O directamente: python3 setup.py --es
   ```

3. El instalador te guiará en los siguientes puntos clave:
   - **Acceso Web:**
     - **Opción 1 (Directo):** Escucha en `0.0.0.0:3000`. Accedes directamente mediante `http://IP_SERVIDOR:3000/`. No requiere configurar Apache.
     - **Opción 2 (Con Apache):** Escucha en `127.0.0.1:3000`. Te solicitará el dominio (ej. `git.tudominio.com`).
   - **Base de Datos PostgreSQL:**
     - **Opción 1 (Local):** Despliega el contenedor de PostgreSQL 18 localmente en este servidor. Genera una contraseña segura y aleatoria.
     - **Opción 2 (Host / Túnel Existente):** Conecta a PostgreSQL en `host.containers.internal:5432`.
     - **Opción 3 (Remota):** Conexión directa por red o túnel SSH automático.
   - **Seguridad y Usuario OpenRC (Podman Rootless):**
     - **Opción 1 (Recomendada):** Crea automáticamente un usuario de sistema dedicado sin login (`forgejo`) con `/sbin/nologin` y rangos subordinate en `/etc/subuid` y `/etc/subgid`.
     - **Opción 2:** Utiliza un usuario no privilegiado existente en el sistema.

---

## 3. Modelo de Seguridad: Desescalado de Privilegios en OpenRC

Aunque OpenRC arranca durante el inicio del sistema con privilegios de `root` (PID 1):
1. **Desescalado (*Privilege Dropping*):** El demonio `/etc/init.d/forgejo` lee la configuración en `/etc/conf.d/forgejo` y desescala inmediatamente la ejecución al usuario sin privilegios configurado (`forgejo`) utilizando `runuser`.
2. **Podman Rootless:** Todo el stack de contenedores corre 100% en espacio de usuario, con almacenamiento en `~/.local/share/containers/storage` y namespaces de usuario.
3. **Hardening en `compose.yaml`:**
   - `security_opt: ["no-new-privileges:true"]`: Bloquea elevación vía binarios SUID dentro del contenedor.
   - `cap_drop: ["ALL"]`: Elimina todas las capabilities del kernel para el servicio de Forgejo.
4. **Confinamiento SELinux:** Los volúmenes persistentes se aíslan bajo el contexto MLS/MCS de SELinux (`container_file_t`).

---

## 4. Gestión del Servicio OpenRC

Una vez instalado por `setup.sh`:

```bash
# Iniciar el stack
rc-service forgejo start

# Detener el stack (timeout de 30s para vaciado limpio de WAL en Postgres)
rc-service forgejo stop

# Ver estado rápido
rc-service forgejo status

# Ver estado detallado de salud
rc-service forgejo status_detail

# Habilitar en el arranque del sistema
rc-update add forgejo default
```

Alternativamente, puedes usar el CLI de administración:

```bash
./scripts/manage.sh start
./scripts/manage.sh stop
./scripts/manage.sh status
./scripts/manage.sh logs server
```

---

## 5. Reversión y Desinstalación Limpia (`--revert`)

Si deseas revertir cualquier modificación realizada en el sistema (eliminar el servicio OpenRC, el usuario de sistema y las entradas de subuid/subgid):

```bash
./setup.sh --revert
# O mediante manage.sh:
./scripts/manage.sh uninstall
```

El proceso de reversión:
1. Detiene ordenadamente los contenedores y el servicio `forgejo`.
2. Elimina el servicio de los runlevels de OpenRC (`rc-update del forgejo default`).
3. Borra los archivos `/etc/init.d/forgejo` y `/etc/conf.d/forgejo`.
4. Permite opcionalmente purgar el usuario de sistema `forgejo` y sus entradas en `/etc/subuid` y `/etc/subgid`.
5. **Preserva siempre tus datos:** Los repositorios en `./data`, base de datos en `./postgres` y `.env` NO se borran por seguridad.

---

## 6. Primer Acceso y Creación de Administrador

Una vez que el servicio esté corriendo:

1. Crea el primer usuario administrador desde el terminal:
   ```bash
   ./scripts/manage.sh create-admin
   ```
   Introduce el usuario deseado (ej. `admin`), correo electrónico y contraseña.

2. Abre el navegador web en `http://IP_SERVIDOR:3000/` o `https://git.tudominio.com/` e inicia sesión con las credenciales que acabas de crear.

---

## 7. Automatización de Copias de Seguridad (Cron en Gentoo)

Para programar un volcado consistente diario a las 03:00 AM:

```bash
crontab -e
```

Añade una línea indicando la ruta absoluta donde clonaste el repositorio (ej. `/home/usuario/forgejo-deploy` o `/srv/forgejo-deploy`):
```cron
0 3 * * * /ruta/absoluta/a/forgejo-deploy/scripts/manage.sh backup > /var/log/forgejo-backup.log 2>&1
```

Los respaldos se almacenarán comprimidos en `./backups/` con fecha y hora.

---

## 8. Actualizaciones de Versión en Caliente (`manage.sh upgrade`)

Forgejo aplica automáticamente migraciones a la base de datos de PostgreSQL al arrancar con una versión más moderna (*forward-only auto-migrations*). Para actualizar sin riesgo de corrupción ni tiempo de inactividad innecesario:

```bash
./scripts/manage.sh upgrade
```

El asistente realiza automáticamente:
1. **Detección Dinámica:** Consulta la API pública de Codeberg y compara tu versión actual con las últimas versiones estables publicadas.
2. **Garantía 100% Rootless:** Todo tag utilizado incorpora obligatoriamente la variante `-rootless` (ej. `17.0.2-rootless`).
3. **Backup Preventivo Obligatorio:** Realiza un volcado consistente en `./backups/` antes de tocar nada. Si el backup falla, la actualización se aborta.
4. **Pre-Pull:** Descarga la nueva imagen OCI mediante `podman pull` mientras el servicio sigue activo en producción.
5. **Recreación y Auto-Migración:** Modifica `FORGEJO_VERSION` en `.env` (guardando `.env.bak`), ejecuta `podman-compose up -d` y verifica que las migraciones concluyan con éxito.

---

## 9. Configuración Avanzada y Archivo `app.ini`

### Ubicación Física en el Host
El archivo principal de configuración de Forgejo se encuentra directamente en el sistema de archivos de tu host en:
```bash
./data/custom/conf/app.ini
```

### Precedencia de Configuración (Variables de Entorno vs `app.ini`)
* **Parámetros en `.env` (Puertos, Bind IP, Base de Datos, ROOT_URL):** Tienen prioridad máxima en Forgejo y sobreescriben `app.ini` durante el arranque del contenedor.
* **Ajustes avanzados en `app.ini`:** Todo lo que no esté en `.env` (deshabilitar registro público de usuarios, cuotas de repositorios, servidor SMTP, OAuth2, avatares, etc.) se edita directamente en este archivo.
* Puedes inspeccionarlo o abrirlo en tu editor ejecutando:
  ```bash
  ./manage.py config           # Muestra rutas y variables
  ./manage.py config --show    # Muestra el contenido de app.ini en terminal
  ./manage.py config --edit    # Abre app.ini con el editor del sistema
  ```
* Tras guardar los cambios, reinicia el servicio con `./manage.py restart`.
