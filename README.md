# forgejo-deploy: Forgejo & PostgreSQL on Gentoo Linux

[![GitHub Repo](https://img.shields.io/badge/GitHub-jrubioh1%2Fforgejo--deploy-181717.svg?logo=github)](https://github.com/jrubioh1/forgejo-deploy)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![Gentoo](https://img.shields.io/badge/OS-Gentoo_Linux-purple.svg)](https://www.gentoo.org/)
[![Forgejo](https://img.shields.io/badge/App-Forgejo_v17-orange.svg)](https://forgejo.org/)
[![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL_18-blue.svg)](https://www.postgresql.org/)
[![Podman](https://img.shields.io/badge/Container-Podman_Rootless-red.svg)](https://podman.io/)
[![Bilingual](https://img.shields.io/badge/Language-Español_%7C_English-green.svg)](#)

[🇪🇸 Español](#-guía-en-español) | [🇬🇧 English](#-english-guide)

---

## 🇪🇸 Guía en Español

Solución de nivel de producción y arquitectura desacoplada para desplegar **Forgejo** con **PostgreSQL 18** en **Gentoo Linux** y migrar datos desde **GitBucket** u otras plataformas.

### Características Principales:
1. **100% Rootless Obligatorio:** Contenedores OCI bajo usuario sin privilegios, namespaces (`subuid`/`subgid`) y desescalado en OpenRC.
2. **Control Total de Puertos e IPs de Enlace:** Personaliza puertos HTTP, SSH Git y PostgreSQL local (evitando colisiones en el host).
3. **Detección Dinámica de Versiones y Actualizaciones:** Asistente interactivo que consulta la API de Codeberg, realiza backup preventivo y actualiza sin caída de servicio (`./scripts/manage.sh upgrade`).
4. **Módulo Independiente de Migración:** Importa repositorios Git, wikis, cuentas e incidencias desde GitBucket (`./migrate.sh`).
5. **Reversión Limpia y Bidireccional:** Desinstala el servicio OpenRC y limpia usuarios sin tocar tus datos (`./setup.sh --revert`).

### Arranque Rápido en 3 Pasos:
```bash
# 1. Clonar el repositorio y configurar infraestructura (Asistente TUI bilingüe):
git clone https://github.com/jrubioh1/forgejo-deploy.git
cd forgejo-deploy
./setup.sh

# 2. Iniciar el servicio y crear el administrador:
./manage.py start       # O también: ./manage.sh start / rc-service forgejo start
./manage.py create-admin

# 3. Migrar datos desde GitBucket (opcional):
./migrate.sh
```

### Operaciones y Mantenimiento:
```bash
# Ayuda y lista de todos los comandos disponibles:
./manage.py --help

# Diagnóstico integral del sistema (cgroups, runtime, permisos):
./manage.py doctor

# Estado detallado de los contenedores y uso de almacenamiento:
./manage.py status

# Detener y destruir contenedores OCI (datos en ./data y ./postgres intactos):
./manage.py down

# Limpiar contenedores detenidos, capas y redes huérfanas:
./manage.py prune        # Añade --all para incluir imágenes sin usar

# Eliminar imágenes locales de Forgejo y Postgres para liberar espacio (~1.5 GB):
./manage.py clean-images

# Passthrough directo a cualquier comando Podman en el almacenamiento de forgejo:
./manage.py podman ps -a
./manage.py podman system df

# Instalar el comando global 'forgejo' en el sistema (/usr/local/bin/forgejo):
./manage.py install-cli

# Corregir permisos de volúmenes si cambias de usuario:
./manage.py fix-permissions

# Actualizar versión de Forgejo (detección en vivo + backup preventivo):
./manage.py upgrade

# Desinstalar y revertir todas las modificaciones del sistema:
./manage.py uninstall   # O: ./setup.sh --revert
```

### Documentación en Español:
- [Arquitectura e Internals](docs/ARCHITECTURE.md)
- [Guía de Despliegue en Gentoo](docs/DEPLOYMENT_GENTOO.md)
- [Manual de Migración desde GitBucket](docs/MIGRATION_GITBUCKET.md)
- [Resolución de Incidencias](docs/TROUBLESHOOTING.md)

---

## 🇬🇧 English Guide

Production-ready, decoupled deployment and migration stack for **Forgejo** with **PostgreSQL 18** on **Gentoo Linux**.

### Key Features:
1. **Mandatory 100% Rootless:** OCI containers executed under an unprivileged user with user namespaces and OpenRC privilege dropping.
2. **Full Port & Bind IP Customization:** Customize HTTP, SSH Git, and PostgreSQL host ports and bind interfaces (preventing port collisions).
3. **Dynamic Version Discovery & Hot Upgrades:** Interactive assistant querying Codeberg API, creating automated backups, and updating with zero downtime (`./scripts/manage.sh upgrade`).
4. **Standalone Migration Engine:** Seamlessly import bare Git repositories, wikis, users, and issues from GitBucket (`./migrate.sh`).
5. **Clean Rollback & Uninstallation:** Revert system services and clean up accounts while keeping data safe (`./setup.sh --revert`).

### Quickstart in 3 Steps:
```bash
# 1. Clone repository and configure infrastructure (Bilingual TUI wizard):
git clone https://github.com/jrubioh1/forgejo-deploy.git
cd forgejo-deploy
./setup.sh

# 2. Start service and create admin user:
rc-service forgejo start
./scripts/manage.sh create-admin

# 3. Migrate data from GitBucket (optional):
./migrate.sh
```

### English Documentation:
- [Gentoo Production Deployment Guide](docs/en/DEPLOYMENT_GENTOO.md)
- [GitBucket Migration Manual](docs/en/MIGRATION_GITBUCKET.md)

---

## Estructura del Repositorio / Repository Layout

```
forgejo-deploy/
├── .gitignore                    # Reglas de exclusión estrictas / Strict ignore rules
├── LICENSE                       # Licencia GNU General Public License v3.0 (GPLv3)
├── setup.py                      # Asistente de despliegue bilingüe / Bilingual deployment wizard
├── setup.sh                      # Wrapper ejecutable / Shell launcher for setup.py
├── migrate.py                    # Asistente de migración bilingüe / Bilingual migration assistant
├── migrate.sh                    # Wrapper ejecutable / Shell launcher for migrate.py
├── compose.yaml                  # Orquestación Podman / Podman Compose orchestration
├── .env.example                  # Plantilla de entorno / Environment template
├── README.md                     # Documentación bilingüe / Bilingual documentation
├── scripts/
│   ├── manage.sh                 # CLI de operaciones / Operations CLI
│   ├── upgrade.py                # Asistente de actualización en caliente / Hot upgrade assistant
│   ├── forgejo_version.py        # Gestor de versiones y validador Rootless / Version manager & Rootless validator
│   ├── migrate_gitbucket.py      # Motor de migración GitBucket / GitBucket migration engine
│   ├── tunnel-db.sh              # Gestor de túnel SSH / SSH tunnel manager
│   ├── forgejo.initd             # Demonio OpenRC / OpenRC service daemon
│   ├── forgejo.confd             # Configuración OpenRC desacoplada / OpenRC decoupled config
│   └── apache-forgejo.conf       # VirtualHost Apache 2.4 con WebSockets
└── docs/
    ├── ARCHITECTURE.md           # Arquitectura profunda / Deep architecture & internals
    ├── DEPLOYMENT_GENTOO.md      # Guía de producción en Gentoo (ES)
    ├── MIGRATION_GITBUCKET.md    # Manual de migración GitBucket (ES)
    ├── TROUBLESHOOTING.md        # Diagnóstico de incidencias (ES)
    └── en/
        ├── DEPLOYMENT_GENTOO.md  # Gentoo Deployment Guide (EN)
        └── MIGRATION_GITBUCKET.md# GitBucket Migration Manual (EN)
```

---

## ⚖️ Licencia / License

Este proyecto se distribuye bajo la licencia **GNU General Public License v3.0 (GPLv3)**. Consulta el archivo [`LICENSE`](LICENSE) para más detalles.

- **Forgejo:** Licenciado bajo la [GNU General Public License v3.0 o posterior (GPL-3.0-or-later)](https://codeberg.org/forgejo/forgejo/src/branch/forgejo/LICENSE).
- **PostgreSQL:** Licenciado bajo [The PostgreSQL Licence](https://www.postgresql.org/about/licence/).
