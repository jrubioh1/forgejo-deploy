# Deploying Forgejo and PostgreSQL on Gentoo Linux (Hardened / OpenRC)

This guide documents deploying **Forgejo** and **PostgreSQL** on **Gentoo Linux** using **Podman**, **OpenRC**, and the automated orchestration tools included in this repository.

---

## 1. Prerequisites on Gentoo

Install the required packages from Portage:

```bash
# Container runtime and utilities
emerge --ask app-containers/podman app-containers/podman-compose dev-vcs/git app-crypt/gnupg openssl

# (Optional) If using Apache as a Reverse Proxy
emerge --ask www-servers/apache
```

> **Note on SELinux (Gentoo Hardened):**  
> If your kernel has active SELinux (`id -Z` displays a SELinux context), the `:Z` flag on the volumes in `compose.yaml` automatically re-labels the `data/` and `postgres/` directories with the `container_file_t` type.

---

## 2. Interactive Setup and Deployment (`setup.py` / `setup.sh`)

1. Clone the repository on your Gentoo server (e.g. `/opt/forgejo` or your preferred directory):
   ```bash
   git clone https://github.com/jrubioh1/forgejo-deploy.git /opt/forgejo
   cd /opt/forgejo
   ```

2. Run the interactive setup assistant (choose language Spanish or English):
   ```bash
   ./setup.sh
   # Or directly: python3 setup.py --en
   ```

3. The installer guides you through key architectural choices:
   - **Web Access Mode:**
     - **Option 1 (Direct):** Listens on `0.0.0.0:3000`. Direct access at `http://SERVER_IP:3000/`. No reverse proxy needed.
     - **Option 2 (Apache):** Listens on `127.0.0.1:3000`. Prompts for your public domain (e.g. `git.yourdomain.com`).
   - **PostgreSQL Database Mode:**
     - **Option 1 (Local):** Deploys a local PostgreSQL 18 container on this server with automated secure password generation.
     - **Option 2 (Host / Existing SSH Tunnel):** Connects to PostgreSQL already available on the host at `host.containers.internal:5432`.
     - **Option 3 (Remote on another server):** Connects via direct IP or creates a managed SSH tunnel.
   - **Security & OpenRC User (Rootless Podman):**
     - **Option 1 (Recommended):** Creates a dedicated unprivileged system user without login (`forgejo`) with `/sbin/nologin` and subordinate UID/GID ranges in `/etc/subuid` and `/etc/subgid`.
     - **Option 2:** Uses an existing unprivileged user on the system.

---

## 3. Security Model: Privilege Dropping in OpenRC

Even though OpenRC starts as `root` (PID 1) during system boot:
1. **Privilege Dropping:** `/etc/init.d/forgejo` reads configuration from `/etc/conf.d/forgejo` and immediately drops execution to the configured unprivileged user (`forgejo`) using `runuser`.
2. **True Rootless Podman:** The entire container stack runs 100% in user space, with user namespaces and storage in `~/.local/share/containers/storage`.
3. **Hardening in `compose.yaml`:**
   - `security_opt: ["no-new-privileges:true"]`: Prevents privilege escalation via internal SUID binaries.
   - `cap_drop: ["ALL"]`: Drops all Linux kernel capabilities for the Forgejo service.
4. **SELinux Confinement:** Persistent volumes are isolated under SELinux MLS/MCS categories (`container_file_t`).

---

## 4. Managing the OpenRC Service

Once installed by `setup.sh`:

```bash
# Start the stack
rc-service forgejo start

# Stop the stack (30-second graceful timeout for WAL flush)
rc-service forgejo stop

# Quick status check
rc-service forgejo status

# Detailed container health status
rc-service forgejo status_detail

# Enable service at system boot
rc-update add forgejo default
```

Alternatively, you can manage the stack with the CLI:

```bash
./scripts/manage.sh start
./scripts/manage.sh stop
./scripts/manage.sh status
./scripts/manage.sh logs server
```

---

## 5. Clean Reversal and Uninstallation (`--revert`)

If you wish to cleanly revert all system modifications (remove OpenRC service, delete system user, and purge subuid/subgid entries):

```bash
./setup.sh --revert
# Or using manage.sh:
./scripts/manage.sh uninstall
```

The rollback process:
1. Gracefully stops running containers and the `forgejo` service.
2. Removes the service from OpenRC runlevels (`rc-update del forgejo default`).
3. Deletes `/etc/init.d/forgejo` and `/etc/conf.d/forgejo`.
4. Optionally purges the `forgejo` system user and its `/etc/subuid` and `/etc/subgid` entries.
5. **Data Protection:** Repository data in `./data`, database in `./postgres`, and `.env` are NEVER automatically deleted for safety.

---

## 6. First Access & Admin Creation

Once the service is running:

1. Create the first admin user from the terminal:
   ```bash
   ./scripts/manage.sh create-admin
   ```
   Enter the desired username, email, and password.

2. Open your browser at `http://SERVER_IP:3000/` or `https://git.yourdomain.com/` and log in.

---

## 7. Data Migration from External Platforms

To migrate existing repositories, wikis, users, and issues from GitBucket:
```bash
./migrate.sh
# Or: python3 migrate.py --en
```
See the full migration guide at [`docs/en/MIGRATION_GITBUCKET.md`](MIGRATION_GITBUCKET.md).

---

## 8. Hot Zero-Downtime Upgrades (`manage.sh upgrade`)

Forgejo automatically performs forward-only PostgreSQL schema migrations upon startup. To upgrade safely without risking database corruption or unexpected downtime:

```bash
./scripts/manage.sh upgrade
# Or: python3 scripts/upgrade.py --en
```

The upgrade assistant automatically executes:
1. **Dynamic Version Discovery:** Queries Codeberg API and compares your current version against the latest stable releases.
2. **Strict Rootless Guarantee:** Enforces that every tag uses the `-rootless` container variant (e.g. `17.0.2-rootless`).
3. **Mandatory Backup:** Runs an automated snapshot into `./backups/` before touching any configuration. If backup fails, upgrade is aborted.
4. **Pre-Pull Image:** Downloads the new OCI image via `podman pull` with zero downtime while the current service continues running.
5. **Recreation & Schema Migration:** Atomically updates `FORGEJO_VERSION` in `.env` (preserving `.env.bak`), runs `podman-compose up -d`, and checks health status.
