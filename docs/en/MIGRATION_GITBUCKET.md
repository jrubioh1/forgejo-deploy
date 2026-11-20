# Migration Manual: GitBucket to Forgejo

This document outlines the end-to-end procedure for migrating all Git repositories, wikis, user accounts, and issues from a running **GitBucket** (Java/Jetty) instance into **Forgejo**.

---

## 1. Pre-Migration Checklist

Before initiating data migration:
- [ ] **Read-Only Mode:** Inform developers and pause code pushes to GitBucket to avoid inconsistencies.
- [ ] **Locate GitBucket Directory:** Find the directory where GitBucket stores bare repositories (usually `~/.gitbucket/repositories` or `/var/lib/gitbucket/repositories`).
- [ ] **Generate Forgejo Administrator Token:**
  1. Log in to Forgejo with your admin account (`http://SERVER_IP:3000` or your domain).
  2. Navigate to **User Settings** -> **Applications**.
  3. Under **Personal Access Tokens**, create a token (e.g. `migration`) with all permissions (`all` or `admin`, `repo`, `user`).
  4. Copy the generated token string.

---

## 2. Interactive Migration Assistant (`migrate.py` / `migrate.sh`)

Run the dedicated bilingual migration assistant:

```bash
./migrate.sh
# Or directly in English: python3 migrate.py --en
```

### Interactive Steps:
1. Select source platform: `1) GitBucket (Java/Jetty)`.
2. Verify or enter the path to the GitBucket data directory (`~/.gitbucket`).
3. Enter your Forgejo base URL and Administrator Token.
4. Indicate whether the GitBucket app is running (to extract issues, milestones, and labels via its REST API).
5. Choose whether to perform a **SIMULATION (`--dry-run`)** first.

---

## 3. Simulation Mode (`--dry-run`)

Running with simulation active performs a read-only audit:
- Scans `repositories/` for `<owner>/<repo>.git` and `<repo>.wiki.git`.
- Lists discovered user accounts and repositories.
- Validates token authentication and API reachability.
- Displays a formatted Unicode metrics summary table with zero modifications to Forgejo.

---

## 4. Live Migration & User Credentials

When running live:
1. Repositories and wikis are transferred using `git push --mirror`, preserving 100% of commit history, branches, tags, authors, and signatures.
2. User accounts are provisioned in Forgejo with secure 16-character temporary passwords and flagged with `must_change_password=True`.
3. Generated temporary passwords are saved into `credentials_report.csv` (protected with `0600` permissions):
   ```csv
   Usuario,Email,Contraseña Temporal
   john,john@migrated.local,K8#xP9$qL2vM5@wZ
   mary,mary@migrated.local,T4!mN8*rB1yQ6#aC
   ```
4. Distribute temporary credentials to users. On their first login to Forgejo, they will be prompted to set their permanent password.

---

## 5. Developer Client Remote Update

Instruct developers to update their local Git clone remotes:

### SSH (Port 2222):
```bash
git remote set-url origin ssh://git@git.yourdomain.com:2222/owner/repo.git
```

### HTTPS:
```bash
git remote set-url origin https://git.yourdomain.com/owner/repo.git
```
