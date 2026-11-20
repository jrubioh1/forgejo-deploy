# Arquitectura y Diseño Técnico del Despliegue de Forgejo y Migración desde GitBucket

Este documento detalla la arquitectura interna del sistema, explicando **qué hace cada componente, cómo lo hace a bajo nivel, por qué se diseñó de esta manera y para qué sirve en un entorno de producción en Gentoo Linux**.

---

## 1. Visión General de la Arquitectura

```
                                  SERVIDOR GENTOO LINUX
┌──────────────────────────────────────────────────────────────────────────────────┐
│                                                                                  │
│  [ ORIGEN: GitBucket (Java/Jetty) ]           [ DESTINO: Stack Forgejo ]         │
│  ┌────────────────────────────────┐           ┌────────────────────────────────┐ │
│  │ Proceso: java -jar gitbucket   │           │ Contenedor Podman:             │ │
│  │ Escucha: 0.0.0.0:8080          │           │ codeberg.org/forgejo/forgejo   │ │
│  │                                │           │ ├─ HTTP: :3000                 │ │
│  │ Almacenamiento:                │           │ └─ SSH:  :2222                 │ │
│  │ ├─ repositories/               │           └──────────────┬─────────────────┘ │
│  │ │  ├─ <owner>/<repo>.git       │ MIGRACIÓN                │ Red interna       │
│  │ │  └─ <owner>/<repo>.wiki.git  │ (git mirror              │                   │
│  │ └─ data.mv.db (H2/SQL)         │  + REST API)             ▼                   │
│  │    (Usuarios, Issues, PRs)     │ ─────────> ┌───────────────────────────────┐ │
│  └────────────────────────────────┘            │ PERSISTENCIA:                 │ │
│                                                │ Opción A: Contenedor PG 18    │ │
│                                                │ Opción B: Túnel SSH a PG ext. │ │
│                                                └───────────────────────────────┘ │
│                                                                                  │
│  [ CONTROL Y SERVICIO ]                                                          │
│  ├─ /etc/init.d/forgejo (OpenRC Service: start, stop con gracia 30s)             │
│  ├─ scripts/tunnel-db.sh (Control socket persistente para BD remota)             │
│  └─ scripts/apache-forgejo.conf (VirtualHost opcional con ProxyPass y SSL)       │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Componente a Componente: Qué, Cómo, Por qué y Para qué

### 2.1. `compose.yaml` (Motor de Contenedores Podman)
* **¿Qué hace?**  
  Define y conecta los servicios `db` (PostgreSQL 18) y `server` (Forgejo), gestionando puertos, volúmenes locales y redes.
* **¿Cómo lo hace a bajo nivel?**  
  - **Mecanismo de Perfiles (`profiles: ["local-db"]`):** Por defecto, Compose levanta todos los servicios listados en el archivo. Al asignar el perfil `local-db` al servicio `db`, este pasa a ser condicional. Si la variable de entorno en `.env` contiene `COMPOSE_PROFILES=local-db`, Compose inicia ambos contenedores (`db` + `server`). Si `COMPOSE_PROFILES=` se deja vacío (cuando usamos base de datos remota), Compose descarta el servicio `db` sin crear el contenedor ni reservar memoria/CPU para PostgreSQL local.
  - **Resolución de Red para Base de Datos:**
    - *Modo Local:* Los contenedores comparten la red bridge `forgejo-net`. Forgejo se conecta al DNS interno `db:5432`.
    - *Modo Remoto Directo:* Forgejo se conecta a la IP pública o privada remota (ej. `192.168.1.50:5432`).
    - *Modo Remoto por Túnel SSH:* El túnel SSH en el host abre el puerto en `0.0.0.0:5432`. El contenedor de Forgejo se conecta a través del gateway de Podman usando el nombre nativo `host.containers.internal:5432`.
  - Asigna volúmenes con el flag `:Z` (`./postgres:/var/lib/postgresql/data:Z` y `./data:/var/lib/gitea:Z`), ordenando al subsistema SELinux de Gentoo reetiquetar las carpetas con el tipo `container_file_t`.
  - Configura `stop_grace_period: 30s` en ambos contenedores para que al recibir la señal de parada no se corte abruptamente la comunicación.
* **¿Por qué se diseñó así?**  
  Montar `./postgres` en `/var/lib/postgresql/data` (y no en `/var/lib/postgresql`) es crítico en imágenes oficiales de PostgreSQL: de lo contrario, el entrypoint de inicialización sobrescribe ficheros de configuración del sistema Debian/Alpine base.
* **¿Para qué sirve?**  
  Garantiza portabilidad total: el servicio puede levantarse tanto en un servidor con base de datos propia como en un servidor satélite conectado a una base de datos central.

---

### 2.2. `setup.sh` (Asistente e Instalador de Gentoo)
* **¿Qué hace?**  
  Inspecciona el entorno Gentoo, valida dependencias (`podman`, `podman-compose`, `openssl`), genera las claves criptográficas, crea los directorios con permisos seguros y configura el archivo `.env`.
* **¿Cómo lo hace a bajo nivel?**  
  - Comprueba la cuenta del usuario: si es `root` (UID 0), omite las comprobaciones de `subuid` y fija permisos a `0700`. Si es un usuario normal, verifica `/etc/subuid` y `/etc/subgid`.
  - Genera contraseñas aleatorias criptográficamente seguras usando `openssl rand -hex 20`.
  - Ofrece copiar el script `scripts/forgejo.initd` en `/etc/init.d/forgejo` y fija sus permisos en `0755`.
* **¿Por qué se diseñó así?**  
  Automatiza el 100% de la preparación reduciendo a cero el error humano al configurar puertos, variables y secretos en un sistema operativo como Gentoo.
* **¿Para qué sirve?**  
  Permite desplegar un nodo de Forgejo en menos de 2 minutos simplemente clonando el repositorio y ejecutando `./setup.sh`.

---

### 2.3. `scripts/forgejo.initd` y `scripts/forgejo.confd` (Demonio OpenRC con Desescalado a Rootless)
* **¿Qué hace?**  
  Proporciona integración nativa con el sistema de inicialización OpenRC de Gentoo para arrancar al encender y detenerse ordenadamente al apagar, eliminando el riesgo de ejecutar Podman como `root`.
* **¿Cómo lo hace a bajo nivel?**  
  - **Desescalado de Privilegios (*Privilege Dropping*):**
    OpenRC arranca como PID 1 (`root`), pero lee el usuario configurado en `/etc/conf.d/forgejo` (`FORGEJO_USER="forgejo"`).
    En `start_pre()`, OpenRC asegura la existencia del directorio de runtime `/run/user/<UID>` con permisos `0700` y propiedad del usuario.
    Posteriormente delega la ejecución de `podman-compose` al usuario no privilegiado utilizando:
    ```bash
    runuser -u "${FORGEJO_USER}" -- env \
        XDG_RUNTIME_DIR="${runtime_dir}" \
        HOME="${user_home}" \
        sh -c "cd '${FORGEJO_DIR}' && ${cmd}"
    ```
  - **Podman Rootless:**
    El stack completo de contenedores se ejecuta en modo Rootless real, utilizando User Namespaces (`/etc/subuid` y `/etc/subgid`). Ni el daemon de Podman ni los contenedores poseen capacidades de root en el kernel del host Gentoo.
  - **Hardening en Contenedores:**
    Ambos servicios aplican `security_opt: ["no-new-privileges:true"]` (bloqueo de elevación SUID) y Forgejo aplica `cap_drop: ["ALL"]` (cero capacidades Linux).
  - **`start_pre()`**: Comprueba si `SSH_TUNNEL_ENABLED=true` en `.env`. De ser así, invoca `scripts/tunnel-db.sh start` para asegurar que el túnel hacia la base de datos remota esté abierto antes de que Forgejo intente conectarse.
  - **`stop()` (Control de parada limpio)**:  
    Ejecuta `podman-compose down --timeout 30`. Esto envía primero una señal `SIGTERM` a los procesos internos. PostgreSQL reacciona realizando un volcado ordenado de buffers de memoria a disco (*checkpoint* limpio) y cerrando el WAL (Write-Ahead Log). Forgejo finaliza las peticiones HTTP y operaciones Git activas. Tras la parada de contenedores, si había un túnel SSH abierto, lo cierra limpiamente.
* **¿Por qué se diseñó así?**  
  Si un servidor Gentoo se apaga sin un script OpenRC que controle el `stop`, el kernel mata los procesos con `SIGKILL`, lo que en bases de datos relacionales puede provocar corrupción de índices o transacciones a medio escribir. Y si se ejecuta como root, un escape de contenedor comprometería el host completo.
* **¿Para qué sirve?**  
  Permite que el administrador gestione el servicio con los comandos habituales de Gentoo con la máxima seguridad:
  ```bash
  rc-service forgejo start
  rc-service forgejo stop
  rc-service forgejo restart
  rc-service forgejo status
  rc-update add forgejo default   # Habilitación en el arranque
  ```

---

### 2.4. `scripts/tunnel-db.sh` (Gestor de Túnel SSH para BD Remota)
* **¿Qué hace?**  
  Establece y monitorea un túnel SSH seguro en segundo plano hacia un servidor remoto de PostgreSQL.
* **¿Cómo lo hace a bajo nivel?**  
  - Ejecuta:
    ```bash
    ssh -f -N -T -M -S /run/forgejo-db-tunnel.sock \
        -L 127.0.0.1:5432:127.0.0.1:5432 \
        -i /root/.ssh/id_ed25519 -o ServerAliveInterval=15 user@host_remoto
    ```
  - Parámetros clave:
    - `-f`: Pasa a segundo plano inmediatamente tras autenticarse.
    - `-N`: No ejecuta ningún comando remoto (solo reenvío de puertos).
    - `-M` y `-S`: Crea un *control socket* Unix en `/run/forgejo-db-tunnel.sock`. Esto permite consultar el estado (`ssh -S ... -O check`) y cerrar el proceso de forma instantánea (`ssh -S ... -O exit`).
    - `ServerAliveInterval=15`: Envía paquetes de sondeo cada 15 segundos para mantener abierta la conexión en firewalls y NATs.
* **¿Por qué se diseñó así?**  
  Evita exponer el puerto 5432 de PostgreSQL a internet o a la red corporativa. Todo el tráfico viaja cifrado bajo el protocolo SSH con clave criptográfica asimétrica (Ed25519/RSA).
* **¿Para qué sirve?**  
  Permite separar físicamente el servidor web de Forgejo del servidor de almacenamiento de base de datos sin comprometer la seguridad ni requerir complejas VPNs.

---

### 2.5. `scripts/manage.sh` (Consola de Administración y Backup)
* **¿Qué hace?**  
  Centraliza las operaciones del administrador: control de estado, inspección de logs, backups en caliente y creación de usuarios administradores.
* **¿Cómo lo hace a bajo nivel?**  
  - `manage.sh backup`: Invoca `podman exec -i forgejo-db pg_dump` y comprime la salida con `gzip`. Simultáneamente empaqueta el directorio `data/` con `tar -czf`.
  - `manage.sh create-admin`: Llama a la herramienta CLI interna de Forgejo dentro del contenedor (`forgejo admin user create --admin ...`) sin necesidad de entrar interactivamente por SSH al contenedor.
* **¿Por qué se diseñó así?**  
  Evita que los administradores tengan que memorizar comandos complejos de Podman o acordarse de los nombres de los contenedores.

---

### 2.6. `scripts/apache-forgejo.conf` (Integración con Apache)
* **¿Qué hace?**  
  Configura Apache 2.4 como Reverse Proxy con terminación SSL y enrutamiento de WebSockets.
* **¿Cómo lo hace a bajo nivel?**  
  - `ProxyPreserveHost On`: Pasa la cabecera `Host` original a Forgejo para que los enlaces web y clones HTTP generen las URLs correctas.
  - Reglas de reescritura para WebSockets:
    ```apache
    RewriteCond %{HTTP:Upgrade} =websocket [NC]
    RewriteRule /(.*) ws://127.0.0.1:3000/$1 [P,L]
    ```
    Esto permite que las notificaciones en vivo y la consola web de Forgejo funcionen de forma fluida.
* **¿Por qué se diseñó así?**  
  Aprovecha que el servidor Gentoo ya dispone de Apache escuchando en los puertos estándar 80 y 443, integrando Forgejo bajo un subdominio limpio (`https://git.tudominio.com/`).

---

### 2.7. `scripts/migrate_gitbucket.py` (La Suite de Migración)
* **¿Qué hace?**  
  Transfiere automáticamente repositorios Git, wikis, usuarios e incidencias desde GitBucket hacia Forgejo.
* **¿Cómo lo hace a bajo nivel?**  
  1. **Descubrimiento Local:** Lee directamente el directorio `repositories/` de GitBucket. Cada repositorio bare (`<owner>/<repo>.git`) y wiki (`<repo>.wiki.git`) es indexado.
  2. **Creación de Cuentas:** Para cada propietario, comprueba en la API de Forgejo (`GET /api/v1/users/{owner}`) si existe. Si no, lo crea con una contraseña aleatoria de 16 caracteres y `must_change_password=True`. Exporta la lista a `credentials_report.csv` con permisos `0600`.
  3. **Replicación Git (`git push --mirror`):**  
     A diferencia de un `git push` normal, `--mirror` clona de forma idéntica **todas las ramas remotas, ramas locales, tags, notas y referencias internas**. Ningún commit, autor o hash SHA se modifica.
  4. **Metadatos e Incidencias:** Si GitBucket está corriendo, consulta su API compatible `/api/v3/repos/{owner}/{repo}/issues` e inserta los issues y comentarios en Forgejo, preservando la fecha y autor original en el cuerpo.
  5. **Simulación (`--dry-run`):** Ejecuta todo el flujo en modo lectura, reportando exactamente qué se migraría sin escribir en Forgejo.
