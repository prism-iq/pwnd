# Erreurs et Problèmes

> Journal des erreurs rencontrées, leur analyse et leur résolution.
> Les erreurs sont aussi stockées dans `synthesis.errors` en base.
>
> Une erreur est un symptôme, pas la maladie.
> Une correction locale, c'est un pansement.
> Une correction systémique, c'est un vaccin.

---

## Protocol

Pour chaque erreur:
1. **Corriger** l'occurrence immédiate
2. **Chercher** toutes les occurrences similaires
3. **Corriger** toutes les occurrences trouvées
4. **Valider** en amont pour empêcher la récurrence
5. **Documenter** ici + en base

---

## Erreurs Systémiques (Historique)

### PATTERN: Bare Except Clauses
- **Symptôme:** `except:` sans type d'exception
- **Fix:** Remplacé par exceptions spécifiques + logging
- **Fichiers:** routes.py, db.py, main.py, pipeline.py, llm_client.py
- **Status:** RÉSOLU

### PATTERN: Hardcoded Paths
- **Symptôme:** `/opt/rag` hardcodé partout
- **Fix:** Créé `app/config.py` avec BASE_DIR
- **Status:** RÉSOLU

### PATTERN: World-Writable Directories
- **Symptôme:** Répertoires 777
- **Fix:** Audit complet, correction à 755
- **Status:** RÉSOLU

### PATTERN: Exposed Services
- **Symptôme:** Services internes sur 0.0.0.0
- **Fix:** UFW + localhost only
- **Status:** RÉSOLU

---

## Erreurs Session Sci-Hub (2026-01-10)

### Extraction PDF bruitée
- **Symptôme:** Titre extrait = fragment de figure au lieu du vrai titre
- **Exemple:** DOI 10.1126/science.1127647 → "larized nearly vertically" au lieu de "Reducing the Dimensionality..."
- **Cause:** pdftotext -layout ne gère pas bien les layouts multi-colonnes
- **Solution proposée:** Utiliser métadonnées OpenAlex pour titre/auteurs
- **Status:** CONTOURNÉ

### Circuits Tor qui expirent
- **Symptôme:** `find_scihub_domain()` retourne None après quelques minutes
- **Cause:** Circuits Tor ont durée de vie limitée
- **Solution proposée:** Reconnecter automatiquement ou utiliser `stem`
- **Status:** CONTOURNÉ (redémarrer Tor avant batch)

### Sci-Hub 403 sans Tor
- **Symptôme:** 403 Forbidden sur sci-hub.st/.se/.ru
- **Cause:** IP blacklistée ou pays bloqué
- **Solution:** Tor systématique
- **Status:** RÉSOLU

### Extraction de claims insuffisante
- **Symptôme:** 0 claims extraites de papers réels
- **Cause:** Patterns regex trop simples pour texte scientifique bruité
- **Solution proposée:** Utiliser LLM (Phi-3/Haiku) pour extraction intelligente
- **Status:** OUVERT - priorité critique

---

## Erreurs Historiques (API/UI)

### /api/query 404
- **Cause:** Endpoint manquant
- **Fix:** Ajouté POST endpoint
- **Status:** RÉSOLU

### Field name mismatch (query vs q)
- **Cause:** UI et Pydantic model désynchronisés
- **Fix:** Aligné sur `{q: query}`
- **Status:** RÉSOLU

### Async/sync mismatch
- **Cause:** await sur fonction sync
- **Fix:** `loop.run_in_executor()`
- **Status:** RÉSOLU

### LLM response type assumption
- **Cause:** Assumé string, reçu dict
- **Fix:** Type checking explicite
- **Status:** RÉSOLU

---

## Template

```markdown
### Nom du Pattern/Erreur
- **Symptôme:**
- **Cause:**
- **Solution:**
- **Status:** OUVERT / CONTOURNÉ / RÉSOLU
```

---

*Les erreurs sont des opportunités d'apprentissage.*
