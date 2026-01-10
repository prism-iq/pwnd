# Errors - Systemic Immunity

> Une erreur est un symptôme, pas la maladie.
> Une correction locale, c'est un pansement.
> Une correction systémique, c'est un vaccin.
>
> Tu n'es pas un correcteur de bugs. Tu es un système immunitaire.

---

## Protocol

Pour chaque erreur:
1. **Corriger** l'occurrence immédiate
2. **Chercher** toutes les occurrences similaires (grep, ast, patterns)
3. **Corriger** toutes les occurrences trouvées
4. **Valider** en amont pour empêcher la récurrence
5. **Documenter** ici: erreur, cause racine, fix systémique

---

## Systemic Fixes (2026-01-10)

### PATTERN: Bare Except Clauses

**Symptôme:** `except:` sans type d'exception spécifique

**Cause racine:** Habitude de coder vite, pas de linter enforçant les règles

**Recherche systémique:**
```bash
grep -rn "except:" --include="*.py" | grep -v "except.*:" | wc -l
# Trouvé: 35+ occurrences dans 12 fichiers
```

**Fichiers affectés:** routes.py, db.py, main.py, pipeline.py, llm_client.py, workers.py, hot_reload.py, multi_phi3.py

**Fix systémique:**
- Remplacé TOUS les `except:` par des exceptions spécifiques avec logging
- Pattern: `except (SpecificError, OtherError) as e: log.error(...)`

**Validation en amont:** TODO: ruff/flake8 avec règle E722, pre-commit hook

**Commit:** 7b03b76

---

### PATTERN: Hardcoded Paths

**Symptôme:** `/opt/rag` hardcodé partout

**Cause racine:** Développement single-machine, pas de pensée déploiement

**Recherche systémique:**
```bash
grep -rn "/opt/rag" --include="*.py" | wc -l
# Trouvé: 20+ occurrences
```

**Fix systémique:**
- Créé `app/config.py` avec BASE_DIR, STATIC_DIR, MIND_DIR, DATA_DIR, LLM_DIR
- Remplacé TOUS les chemins hardcodés
- Variable RAG_BASE_DIR pour déploiement flexible

**Commit:** e40c1b3

---

### PATTERN: World-Writable Directories

**Symptôme:** Répertoires avec permissions 777

**Recherche systémique:**
```bash
find /opt/rag -type d -perm 777
```

**Fix:** Audit complet, correction à 755

---

### PATTERN: Exposed Services

**Symptôme:** Services internes accessibles depuis l'extérieur (0.0.0.0)

**Fix systémique:**
- UFW activé avec deny incoming
- Seulement 22/80/443 autorisés
- Services internes via localhost uniquement

**Commit:** cbdb77e

---

## Local Fixes (Historical)

### ERROR: /api/query endpoint not found
**Symptom:** UI POST to `/api/query` returned 404
**Root cause:** Only GET `/api/ask` existed in routes.py
**Fix:** Added new POST endpoint
**Lesson:** When changing UI, verify corresponding backend endpoints exist

---

### ERROR: Field name mismatch
**Symptom:** Query endpoint received empty query
**Root cause:** UI sent `{query: ...}`, Pydantic model expected `{q: ...}`
**Fix:** Changed UI to send `{q: query}`
**Lesson:** Always verify request/response schemas match between frontend and backend

---

### ERROR: Async/sync mismatch
**Symptom:** `TypeError: object function can't be used in 'await' expression`
**Root cause:** `search_corpus_scored` is synchronous, called with await
**Fix:** Used `loop.run_in_executor(None, sync_func, args)`
**Lesson:** Check function signatures before awaiting. Use executor for sync functions in async context.

---

### ERROR: LLM response type assumption
**Symptom:** `TypeError: 'dict' object is not subscriptable as string`
**Root cause:** Assumed `call_haiku()` returns string, actually returns Dict
**Fix:** Added type checking: `if isinstance(result, dict): ...`
**Lesson:** Never assume return types. Check actual implementation or use type hints.

---

### ERROR: Empty search results
**Symptom:** Queries returned no documents despite database having 15K+ docs
**Root cause:** Old search hit `emails` table, documents are in `contents` table
**Fix:** Created new search function using `contents_fts` FTS index
**Lesson:** Verify which tables contain the data you're searching

---

### ERROR: LLM 400 Bad Request
**Symptom:** Search returns results, but LLM synthesis fails with 400
**Root cause:** Anthropic account has no credits
**Fix:** Removed LLM synthesis from API - return search results directly. Claude Opus handles synthesis in conversation.
**Lesson:** Don't depend on external paid APIs for core functionality. Use local fallbacks.

---

## Template

```markdown
### PATTERN: Nom du Pattern

**Symptôme:** Ce qui s'est manifesté
**Cause racine:** Pourquoi ça a pu arriver

**Recherche systémique:**
- Commande utilisée
- Occurrences trouvées
- Fichiers affectés

**Fix systémique:**
- Actions prises sur TOUTES les occurrences
- Validation en amont ajoutée

**Commit:** hash
```
