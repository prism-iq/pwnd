# Frontend Upload System - Hot Deploy

**Mise à jour du frontend sans reconstruire**

---

## Problème Résolu

❌ **Avant:** Le frontend était reconstruit à chaque redémarrage des services
✅ **Maintenant:** Upload AJAX direct, mise à jour instantanée, backups automatiques

---

## Quick Start

### 1. Accéder à l'interface d'upload

```
http://localhost/upload.html
```

### 2. Uploader des fichiers

**Méthode 1: Drag & Drop**
- Glisser-déposer les fichiers dans la zone
- Cliquer sur "🚀 Upload All"

**Méthode 2: Sélection manuelle**
- Cliquer sur "📁 Select Files"
- Choisir un ou plusieurs fichiers
- Cliquer sur "🚀 Upload All"

### 3. Vérifier

- Les fichiers sont immédiatement actifs
- Pas de redémarrage nécessaire
- Backups automatiques créés

---

## API Endpoints

### POST `/api/frontend/upload`

Upload d'un seul fichier.

**Paramètres:**
- `file`: UploadFile (multipart/form-data)
- `path`: Optional[str] - Chemin custom (ex: "admin/test.html")

**Réponse:**
```json
{
  "status": "success",
  "filename": "index.html",
  "path": "index.html",
  "size": 9747,
  "timestamp": "2026-01-08T05:00:00"
}
```

**Exemple cURL:**
```bash
curl -X POST http://localhost/api/frontend/upload \
  -F "file=@index.html"
```

---

### POST `/api/frontend/upload/batch`

Upload de plusieurs fichiers en une requête (upload chain).

**Paramètres:**
- `files`: List[UploadFile]

**Réponse:**
```json
{
  "total": 3,
  "success": 3,
  "failed": 0,
  "results": [
    {
      "file": "index.html",
      "success": true,
      "status": "success",
      "path": "index.html",
      "size": 9747
    },
    {
      "file": "style.css",
      "success": true,
      "status": "success",
      "path": "style.css",
      "size": 24326
    },
    {
      "file": "app.js",
      "success": true,
      "status": "success",
      "path": "app.js",
      "size": 19029
    }
  ]
}
```

**Exemple cURL:**
```bash
curl -X POST http://localhost/api/frontend/upload/batch \
  -F "files=@index.html" \
  -F "files=@style.css" \
  -F "files=@app.js"
```

---

### GET `/api/frontend/files`

Liste tous les fichiers du frontend.

**Réponse:**
```json
{
  "count": 8,
  "files": [
    {
      "path": "index.html",
      "name": "index.html",
      "size": 9747,
      "modified": "2026-01-08T04:39:00",
      "extension": ".html"
    },
    ...
  ]
}
```

---

### GET `/api/frontend/backups`

Liste tous les backups créés.

**Réponse:**
```json
{
  "count": 5,
  "backups": [
    {
      "name": "index_20260108_050000.html",
      "size": 9747,
      "created": "2026-01-08T05:00:00"
    },
    ...
  ]
}
```

---

### DELETE `/api/frontend/file?path=<file>`

Supprime un fichier (avec backup automatique).

**Paramètres:**
- `path`: str - Chemin relatif du fichier

**Réponse:**
```json
{
  "status": "deleted",
  "file": "test.html",
  "backup": "test_deleted_20260108_050000.html"
}
```

---

## Sécurité

### Extensions Autorisées

```
.html, .css, .js, .json, .svg, .png, .jpg, .jpeg, .gif, .ico, .txt, .md
```

### Protection Directory Traversal

❌ Bloqué: `../../etc/passwd`
❌ Bloqué: `/etc/passwd`
✅ Autorisé: `admin/config.html`

### Backups Automatiques

Avant chaque upload/suppression:
- Backup créé dans `.backups/`
- Format: `{filename}_{timestamp}{extension}`
- Jamais de perte de données

---

## Cas d'Usage

### 1. Mise à jour du frontend en prod

```bash
# 1. Développer localement
nano static/index.html

# 2. Uploader via interface web
http://localhost/upload.html

# 3. Tester immédiatement
http://localhost/

# Pas de rebuild, pas de redémarrage!
```

### 2. Déploiement multi-fichiers

```bash
# Upload en chaîne via API
curl -X POST http://localhost/api/frontend/upload/batch \
  -F "files=@index.html" \
  -F "files=@style.css" \
  -F "files=@app.js" \
  -F "files=@logo.svg"
```

### 3. Rollback rapide

```bash
# 1. Lister les backups
curl http://localhost/api/frontend/backups

# 2. Restaurer manuellement
cp /opt/rag/static/.backups/index_20260108_040000.html \
   /opt/rag/static/index.html

# 3. Ou re-uploader via interface
```

### 4. Déploiement CI/CD

```yaml
# GitHub Actions exemple
- name: Deploy Frontend
  run: |
    for file in static/*; do
      curl -X POST http://prod.example.com/api/frontend/upload \
        -F "file=@$file"
    done
```

---

## Workflow Recommandé

### Développement Local

1. Modifier fichiers dans `static/`
2. Tester avec rechargement auto du navigateur
3. Quand satisfait, uploader via `upload.html`

### Production

1. Uploader via API ou interface web
2. Vérifier immédiatement (pas de cache)
3. Si problème: rollback depuis backups

---

## Avantages vs Rebuild

| Aspect | Rebuild | Upload AJAX |
|--------|---------|-------------|
| Temps | 30-60s | 1-2s |
| Downtime | Oui (services restart) | Non |
| Backups | Manuel | Automatique |
| Rollback | Difficile | Instantané |
| Multi-fichiers | Batch | Chaîne |

---

## Troubleshooting

### ❌ "File type not allowed"

**Problème:** Extension non autorisée
**Solution:** Vérifier la liste des extensions autorisées (ligne 279 de routes.py)

### ❌ "Invalid path (directory traversal detected)"

**Problème:** Tentative d'accès hors de `/opt/rag/static`
**Solution:** Utiliser chemins relatifs uniquement (ex: "admin/test.html")

### ❌ Upload échoue sans erreur

**Problème:** Permissions du dossier
**Solution:**
```bash
sudo chown -R root:root /opt/rag/static
sudo chmod -R 755 /opt/rag/static
```

### ❌ Fichier uploadé mais pas visible

**Problème:** Cache navigateur
**Solution:** Ctrl+Shift+R (hard refresh)

---

## Architecture

```
┌─────────────┐
│  Browser    │
│  (AJAX)     │
└──────┬──────┘
       │ POST /api/frontend/upload
       ▼
┌─────────────┐
│  FastAPI    │
│  (routes.py)│
└──────┬──────┘
       │
       ├──► Validate extension
       ├──► Check directory traversal
       ├──► Create backup (if exists)
       ├──► Save file
       └──► Return success

┌─────────────────────┐
│  /opt/rag/static/   │
│    ├── index.html   │
│    ├── app.js       │
│    ├── style.css    │
│    └── .backups/    │ ← Backups automatiques
└─────────────────────┘
```

---

## Commandes Utiles

**Lister fichiers uploadés:**
```bash
curl http://localhost/api/frontend/files | jq
```

**Lister backups:**
```bash
curl http://localhost/api/frontend/backups | jq
```

**Upload fichier:**
```bash
curl -X POST http://localhost/api/frontend/upload \
  -F "file=@myfile.html"
```

**Upload multiple (batch):**
```bash
curl -X POST http://localhost/api/frontend/upload/batch \
  -F "files=@file1.html" \
  -F "files=@file2.css"
```

**Supprimer fichier:**
```bash
curl -X DELETE "http://localhost/api/frontend/file?path=test.html"
```

---

## Intégration avec boom.sh

Le système d'upload est **indépendant de boom.sh**.

- `boom.sh` ne touche plus au frontend après installation initiale
- Pas de rebuild des fichiers statiques
- Upload à chaud sans downtime

---

## Monitoring

**Log upload dans interface:**
- Succès/échecs en temps réel
- Taille des fichiers
- Horodatage

**Log serveur (journalctl):**
```bash
sudo journalctl -u l-api -f | grep "frontend"
```

---

## Best Practices

1. **Toujours tester en local avant upload prod**
2. **Utiliser batch upload pour cohérence** (évite états intermédiaires)
3. **Vérifier backups régulièrement** (auto-nettoyage si trop vieux)
4. **Hard refresh navigateur après upload** (Ctrl+Shift+R)
5. **Garder versions dans Git** (backups ≠ version control)

---

## Future Improvements

- [ ] Auto-minification des fichiers uploadés
- [ ] Compression gzip automatique
- [ ] Versioning avec tags
- [ ] Rollback one-click depuis interface
- [ ] Preview avant upload
- [ ] Diff visuel entre versions

---

*"Update fast. Deploy faster. Never rebuild."*

**— L Investigation Framework**
