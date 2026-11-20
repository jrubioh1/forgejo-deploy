# Manual Operativo de Migración: GitBucket hacia Forgejo

Este documento detalla el procedimiento completo para transferir de forma íntegra todos los repositorios Git, wikis, cuentas de usuario e incidencias desde una instancia en ejecución de **GitBucket** (Java/Jetty) hacia **Forgejo**.

---

## 1. Lista de Verificación Previa a la Migración

Antes de comenzar el volcado de datos:
- [ ] **Modo Solo Lectura:** Notifica a los desarrolladores y detén las confirmaciones (*pushes*) en GitBucket para evitar inconsistencias durante la migración.
- [ ] **Localizar Directorio de GitBucket:** Localiza la ruta donde GitBucket almacena los repositorios (habitualmente `~/.gitbucket/repositories` o `/var/lib/gitbucket/repositories`).
- [ ] **Generar Token de Administrador en Forgejo:**
  1. Accede a Forgejo con la cuenta administradora (`http://servidor:3000` o tu dominio).
  2. Ve a **Configuración de Usuario** (icono de perfil superior derecho) -> **Aplicaciones**.
  3. En **Tokens de acceso personal**, introduce un nombre (ej. `migracion`) y selecciona todos los permisos (`all` o `admin`, `repo`, `user`).
  4. Haz clic en **Generar token** y copia la cadena generada.

---

## 2. Fase 1: Auditoría y Simulación (`--dry-run`)

Ejecuta el script en modo de simulación. En este modo **no se escribe absolutamente nada** en Forgejo; solo se escanea el disco y se audita qué repositorios y usuarios se han descubierto:

```bash
python3 scripts/migrate_gitbucket.py \
    --dry-run \
    --gitbucket-dir ~/.gitbucket \
    --forgejo-url http://127.0.0.1:3000 \
    --forgejo-token "PEGAR_TU_TOKEN_AQUI"
```

### ¿Qué debes revisar en la salida?
- Que la cantidad de repositorios encontrados coincida con tus proyectos en GitBucket.
- Que se detecten correctamente los nombres de propietarios y organizaciones.
- Si existen repositorios wiki (`.wiki.git`), confirma que aparecen marcados para migración.

---

## 3. Fase 2: Ejecución de la Migración en Vivo

Una vez validada la simulación, ejecuta la migración real:

```bash
python3 scripts/migrate_gitbucket.py \
    --gitbucket-dir ~/.gitbucket \
    --gitbucket-url http://127.0.0.1:8080/gitbucket \
    --forgejo-url http://127.0.0.1:3000 \
    --forgejo-token "PEGAR_TU_TOKEN_AQUI" \
    --credentials-file credentials_report.csv
```

> **Parámetros opcionales útiles:**
> - `--skip-issues`: Si solo deseas transferir el código fuente y las wikis sin incidencias ni comentarios.
> - `--skip-wikis`: Si no utilizas la funcionalidad de Wiki en GitBucket.

---

## 4. Fase 3: Gestión de Credenciales y Usuarios Migrados

Debido a que GitBucket almacena las contraseñas con algoritmos hash irreversibles con salt (PBKDF2):
1. El script crea cada usuario en Forgejo con una **contraseña temporal aleatoria y segura de 16 caracteres**.
2. Marca la cuenta con el atributo `must_change_password=True`.
3. Almacena las contraseñas generadas en el archivo local `credentials_report.csv`:
   ```csv
   Usuario,Email,Contraseña Temporal
   juan,juan@migrated.local,K8#xP9$qL2vM5@wZ
   maria,maria@migrated.local,T4!mN8*rB1yQ6#aC
   ```
4. Este archivo queda protegido automáticamente con permisos `0600` (solo legible por `root`/propietario).
5. **Acción del Administrador:** Entrega a cada desarrollador su contraseña temporal. En su primer inicio de sesión en Forgejo, el sistema les obligará de inmediato a definir su contraseña definitiva.

---

## 5. Fase 4: Verificación Post-Migración

1. **Integridad de Código:**
   - Abre un repositorio en la interfaz web de Forgejo.
   - Comprueba que la lista de ramas (`branches`), etiquetas (`tags`) y autores de commits coincidan exactamente con GitBucket.
2. **Wikis:**
   - Si el repositorio contenía wiki, navega a la pestaña **Wiki** en Forgejo y valida que las páginas en Markdown se muestren correctamente.
3. **Incidencias:**
   - Comprueba que los issues migrados tengan sus descripciones y comentarios originales.

---

## 6. Fase 5: Actualización de Remotos Git en los Clientes

Indica a los desarrolladores que actualicen la URL del remoto `origin` en sus clones locales:

### Clonado por SSH (Puerto 2222):
```bash
git remote set-url origin ssh://git@git.tudominio.com:2222/propietario/repositorio.git
```

### Clonado por HTTPS:
```bash
git remote set-url origin https://git.tudominio.com/propietario/repositorio.git
```
*(o `http://servidor:3000/propietario/repositorio.git` si se utiliza el modo de acceso directo).*
