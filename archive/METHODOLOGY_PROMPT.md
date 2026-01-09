# L Investigation Framework - Debugging Methodology Prompt

## VERSION DÉTAILLÉE

Tu es un expert en debugging de systèmes RAG (Retrieval-Augmented Generation) avec LLM. Voici la méthodologie complète à appliquer:

### 1. DIAGNOSTIC INITIAL - Architecture Multi-Couches

**Principe:** Un système RAG a plusieurs points de défaillance. Toujours diagnostiquer de bas en haut.

**Stack typique:**
```
[Frontend HTML/CSS/JS]
    ↓ HTTP
[Backend API - FastAPI/Flask]
    ↓ Appels
[Pipeline LLM - 4 étapes]
    ├─ Step 1: Intent Parsing (Phi-3/Mistral)
    ├─ Step 2: SQL Execution (SQLite/PostgreSQL)
    ├─ Step 3: Analysis (Claude Haiku API)
    └─ Step 4: Response Formatting (Phi-3/Mistral)
    ↓ Données
[Databases - FTS, Graph, Sessions]
```

**Ordre de diagnostic:**
1. **Data layer** - Les données existent-elles? (`SELECT COUNT(*)`, vérifier FTS)
2. **Query layer** - La recherche SQL fonctionne-t-elle? (test direct SQL)
3. **LLM layer** - Les LLM parsent-ils correctement? (test curl direct)
4. **API layer** - Les routes retournent-elles les bonnes données? (logs uvicorn)
5. **Frontend layer** - Le HTML/CSS match-t-il? (inspect element)

### 2. TESTS ISOLÉS - Jamais Tester le Système Complet d'Abord

**Problème observé:** "Who is Jeffrey Epstein?" ne retournait rien
**Mauvaise approche:** Débugger l'API entière
**Bonne approche:** Tester chaque couche séparément

#### 2.1 Test Data Layer
```bash
# Vérifier que les données existent
sqlite3 /opt/rag/db/sources.db "SELECT COUNT(*) FROM emails;"
# → 13009 ✓

# Vérifier que FTS fonctionne
sqlite3 /opt/rag/db/sources.db "SELECT COUNT(*) FROM emails_fts WHERE emails_fts MATCH 'Jeffrey Epstein';"
# → 1130 ✓

# Tester la query exacte du pipeline
sqlite3 /opt/rag/db/sources.db "
SELECT e.doc_id, e.subject, snippet(emails_fts, 1, '<mark>', '</mark>', '...', 50)
FROM emails_fts
JOIN emails e ON emails_fts.rowid = e.doc_id
WHERE emails_fts MATCH 'Jeffrey Epstein'
LIMIT 5;"
# → Retourne 5 emails ✓
```

**Conclusion:** Data layer OK, problème ailleurs.

#### 2.2 Test LLM Intent Parsing
```bash
# Tester Phi-3 directement (pas via le pipeline)
curl -s http://127.0.0.1:8001/generate -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Parse: Who is Jeffrey Epstein?\nReturn JSON: {\"intent\":\"search\",\"entities\":[...]}",
    "max_tokens": 100,
    "temperature": 0.0
  }'
```

**Problème trouvé:** Phi-3 retournait:
```
"- response: {\"intent\": \"search\", \"entities\": [\"Jeffrey Epstein\"]}\n- answer: ..."
```

Au lieu de JSON pur. Le parser JSON échouait → fallback sur `{"entities": []}` → recherche vide.

**Solution:** Parser multiline avec extraction du premier JSON valide:
```python
for line in response.split('\n'):
    line = line.strip()
    if line.startswith("-"):
        line = line.split(":", 1)[-1].strip()
    if line.startswith("{"):
        try:
            intent = json.loads(line)
            if "intent" in intent and "entities" in intent:
                return intent  # ✓ Premier JSON valide trouvé
        except json.JSONDecodeError:
            continue
```

#### 2.3 Test Response Formatting
**Problème:** Phi-3 ajoutait des artifacts:
```
"<|assistant|> You are to ONLY respond to the following:\n\nRequest: Who is..."
```

**Solution 1 tentée:** Prompts complexes pour guider Phi-3
- **Résultat:** Échec, Phi-3-Mini est trop petit pour suivre des instructions complexes

**Solution 2 adoptée:** Bypass Phi-3 pour le formatage, faire du string templating en Python:
```python
# Au lieu de demander à Phi-3 de formater, on format nous-mêmes
findings = haiku_json.get("findings", [])
sources = haiku_json.get("sources", [])

response_parts = []
for finding in findings:
    # Post-processing des phrasings problématiques
    finding = finding.replace("LinkedIn profile", "LinkedIn emails")
    finding = finding.replace("Amazon account", "Amazon emails")
    response_parts.append(finding)

response = " ".join(response_parts)
if sources:
    response += f"\n\nSources: {' '.join([f'[{s}]' for s in sources])}"
```

**Principe clé:** Si un LLM est trop petit/instable, utiliser du code déterministe.

### 3. CSS/HTML MISMATCH - Diagnostic Visuel

**Symptôme:** "your discord look like tetris"

**Diagnostic:**
1. Vérifier que le CSS est bien servi:
```bash
curl -s http://127.0.0.1:8002/style.css | head -20
# ✓ CSS Discord présent
```

2. Lire le HTML réel (pas assumer):
```bash
grep -E "class=|id=" /opt/rag/static/index.html | head -30
```

**Problème trouvé:** Mismatch entre CSS et HTML
- CSS avait: `.chat-container`, `#queryInput`, `.input-area`
- HTML avait: `.messages-container`, `#messageInput`, `.input-container`

**Solution:** Mapper EXACTEMENT les classes CSS sur le HTML existant:
```css
/* AVANT (ne fonctionne pas) */
.chat-container { flex: 1; }
#queryInput { padding: 11px; }

/* APRÈS (fonctionne) */
.messages-container { flex: 1; }
#messageInput { padding: 11px; }
```

**Classes manquantes identifiées:**
- `.welcome-screen`, `.example-btn`, `.input-footer`
- `.modal`, `.auto-investigate-banner`
- `.footer-btn`, `.stats-section`

**Méthode:** Extraire TOUTES les classes du HTML, créer CSS pour chacune.

### 4. LOGGING STRATÉGIQUE - Pas de Logs Inutiles

**Mauvaise pratique:**
```python
logging.info("Starting query processing")
logging.info("Query received")
logging.info("Processing...")
```
→ Bruit, aucune valeur diagnostique

**Bonne pratique:**
```python
logging.info(f"Search intent: entities={entities}, search_term='{search_term}'")
logging.info(f"Executing email search with term: '{search_term}', limit: {limit}")
logging.info(f"Email search returned {len(email_results)} results")
```
→ Valeurs concrètes, permet de voir où ça casse

**Logs de warning pour détecter les patterns:**
```python
suspicious_patterns = [
    (r'based on (?:his|her|their) (LinkedIn|Amazon)', 'possessive external service'),
    (r'(?:has|have) an? (LinkedIn|Amazon) (?:account|profile)', 'account reference'),
]

for pattern, description in suspicious_patterns:
    matches = re.findall(pattern, response, re.IGNORECASE)
    if matches:
        logging.warning(f"Suspicious phrasing ({description}): {matches}")
```

### 5. PROMPT ENGINEERING - Simplicité > Complexité

**Échec observé:** Prompts de 30+ lignes pour Phi-3-Mini
```
STRICT RULES:
- ONLY use information from Analysis JSON
- NEVER add external knowledge (NYT, BBC, Netflix...)
- CRITICAL: Email Source Phrasing
  - ✅ CORRECT: "According to LinkedIn email [7837]..."
  - ❌ WRONG: "based on his LinkedIn profile"
...
```

**Résultat:** Phi-3 ignorait tout et générait du HTML:
```
"<div style=\"text-align: justify;\"><p>Analysis:</p>..."
```

**Solution:** Pour les petits modèles, utiliser du code Python au lieu de prompts:

**AVANT (prompt complexe → LLM):**
```python
prompt = f"""Format this analysis. Rules: [30 lignes]...
Analysis: {json}
"""
response = await call_llm(prompt)
```

**APRÈS (code déterministe):**
```python
findings = json.get("findings", [])
response = " ".join(findings)
# Post-process les phrasings problématiques
response = response.replace("LinkedIn profile", "LinkedIn emails")
if sources:
    response += f"\n\nSources: {sources}"
```

**Principe:**
- **Claude Opus/Sonnet:** Peut suivre des instructions complexes
- **Phi-3-Mini/Mistral-7B:** Préférer du code Python + prompts simples
- **GPT-4:** Peut suivre des instructions complexes
- **GPT-3.5/Llama-7B:** Comme Phi-3, rester simple

### 6. HAIKU ANALYSIS - Le Maillon Fort

**Architecture:**
```
Phi-3 (local, rapide, instable) → SQL → Haiku (API, lent, fiable) → Phi-3 (formatage)
```

**Rôle de Haiku:** Analyse structurée en JSON
```python
system_prompt = """You are a document analysis engine.
STRICT RULES:
- ONLY use information from the Data provided
- NEVER reference external sources
- When describing emails FROM linkedin.com: say "from a LinkedIn email" NOT "LinkedIn profile"
"""

prompt = f"""Question: {query}

Data from corpus:
[1] Email #7837: Jeffrey Epstein's invitation...
    From: messages-noreply@linkedin.com | Date: 2019-10-29
    ...https://www.linkedin.com/comm/in/jeffrey-epstein...

Analyze ONLY this data. Return JSON:
{{"findings": ["fact from data"], "sources": [123, 456], "confidence": "high|medium|low"}}
"""

haiku_response = await call_haiku(prompt, system=system_prompt, max_tokens=300)
```

**Pourquoi Haiku et pas Phi-3?**
- Haiku comprend le contexte des emails (FROM linkedin.com vs profil LinkedIn)
- JSON structuré fiable
- Coût acceptable pour analyse (300 tokens = $0.0004)

**Optimisation coûts:**
- Haiku seulement pour l'analyse (Step 3)
- Phi-3 local pour intent parsing (Step 1) et formatage (Step 4)
- Rate limiting: 100 calls/day, $1/day max

### 7. PHRASING FIXES - Post-Processing Intelligent

**Problème:** Haiku disait "based on his LinkedIn profile description"
→ Sonnait comme connaissance externe, pas comme email du corpus

**Solution multi-niveau:**

**Niveau 1 - Prompt Haiku:**
```
**CRITICAL: When describing emails**:
- If email FROM linkedin.com: say "from a LinkedIn email" NOT "LinkedIn profile"
- If email FROM amazon.com: say "from an Amazon email" NOT "Amazon account"
```

**Niveau 2 - Post-processing Python:**
```python
finding = finding.replace("LinkedIn profile", "LinkedIn emails")
finding = finding.replace("Amazon account", "Amazon emails")
finding = finding.replace("based on LinkedIn", "according to LinkedIn emails")
```

**Niveau 3 - Monitoring:**
```python
suspicious_patterns = [
    (r'based on (?:his|her|their) (LinkedIn|Amazon)', 'possessive external service'),
]
for pattern, description in suspicious_patterns:
    if re.search(pattern, response):
        logging.warning(f"Suspicious phrasing: {description}")
```

**Résultat:**
- ❌ "based on his LinkedIn profile description"
- ✓ "according to LinkedIn emails, Jeffrey Epstein..."

### 8. SERVICE RESTART - Toujours Vérifier le Reload

**Commande correcte:**
```bash
systemctl restart l-api.service && sleep 3 && systemctl status l-api.service --no-pager
```

**Pourquoi le sleep?**
- Le service met ~2 secondes à charger Python + libs
- Tester trop tôt = faux négatif

**Vérification complète:**
```bash
# 1. Service status
systemctl status l-api.service

# 2. Listening sur le bon port
ss -tlnp | grep 8002

# 3. Health endpoint
curl -s http://127.0.0.1:8002/api/health

# 4. Test query
curl -s "http://127.0.0.1:8002/api/ask?q=test"
```

### 9. DEBUGGING WORKFLOW - Checklist Complète

Quand un bug RAG apparaît:

```
□ 1. Identifier le symptôme exact
   - "No results" vs "Wrong results" vs "Error 500"

□ 2. Isoler la couche défaillante (bottom-up)
   - [ ] Data exists? → SQL direct
   - [ ] Query works? → Test SQL query
   - [ ] LLM parses? → curl direct
   - [ ] API routes? → Check logs
   - [ ] Frontend? → Inspect HTML

□ 3. Reproduire en isolation
   - Tester CHAQUE composant séparément
   - Jamais tester le système complet d'abord

□ 4. Vérifier les assumptions
   - Lire le code réel, pas assumer
   - Vérifier class names HTML vs CSS
   - Vérifier model utilisé (Phi-3 ≠ Mistral)

□ 5. Ajouter des logs stratégiques
   - Log les valeurs, pas les messages génériques
   - Log AVANT et APRÈS les transformations

□ 6. Fix + Test
   - Fix une chose à la fois
   - Redémarrer le service (avec sleep)
   - Tester le fix en isolation

□ 7. Vérifier les side effects
   - Le fix casse-t-il autre chose?
   - Check logs pour warnings
```

### 10. ANTI-PATTERNS - Ce Qu'il NE FAUT PAS Faire

❌ **Assumer que le CSS matche le HTML**
```python
# ❌ Écrire du CSS sans lire le HTML
.chat-container { ... }

# ✓ Lire le HTML d'abord
grep "class=" index.html
# Puis écrire le CSS qui matche
.messages-container { ... }
```

❌ **Prompts complexes pour petits modèles**
```python
# ❌ 50 lignes de règles pour Phi-3-Mini
prompt = """You are an assistant. STRICT RULES:
- Rule 1: ...
- Rule 2: ...
[40 more lines]
"""

# ✓ Code Python simple
response = " ".join(findings)
response = response.replace("bad", "good")
```

❌ **Tester le système complet en premier**
```bash
# ❌ Commencer par tester l'API entière
curl "http://localhost:8002/api/ask?q=test"
# → Impossible de savoir où ça casse

# ✓ Tester bottom-up
sqlite3 db.db "SELECT * FROM emails LIMIT 1"  # Data?
curl http://localhost:8001/generate  # LLM?
curl http://localhost:8002/api/health  # API?
```

❌ **Logs inutiles**
```python
# ❌ Bruit
logging.info("Starting...")
logging.info("Processing...")

# ✓ Valeur diagnostique
logging.info(f"Query: '{query}' → entities: {entities} → {len(results)} results")
```

❌ **Ignorer les modèles réellement utilisés**
```python
# ❌ Assumer Mistral parce que c'est dans le nom de fonction
await call_mistral(prompt)  # En réalité = Phi-3!

# ✓ Vérifier backend.py, config.py
grep "MODEL_PATH\|model=" backend.py
# → Phi-3-mini-4k-instruct-q4.gguf
```

### 11. ARCHITECTURE FINALE - Pipeline 4 Étapes Optimisé

```python
async def process_query(query: str) -> AsyncGenerator[Dict, None]:
    """
    Step 1: Intent Parsing (Phi-3 local, ~2s, $0)
    → {"intent": "search", "entities": ["Jeffrey Epstein"]}
    """
    intent = await parse_intent_mistral(query)  # En réalité Phi-3
    # Fix: Parser multiline avec extraction JSON

    """
    Step 2: SQL Execution (Python, <100ms, $0)
    → [{id: 7837, subject: "...", snippet: "..."}, ...]
    """
    sql_results = execute_sql_by_intent(intent, limit=10)
    # Fix: Ajouter logs pour debug

    """
    Step 3: Analysis (Haiku API, ~5s, $0.0004)
    → {"findings": [...], "sources": [7837, 7796], "confidence": "medium"}
    """
    haiku_analysis = await analyze_haiku(query, sql_results)
    # Fix: Prompt explicite "from a LinkedIn email" pas "LinkedIn profile"

    """
    Step 4: Formatting (Python, <1ms, $0)
    → "According to LinkedIn emails, Jeffrey Epstein..."
    """
    response = await format_response_mistral(query, haiku_analysis)
    # Fix: Bypass Phi-3, faire du string templating Python

    yield {"type": "chunk", "text": response}
```

**Coûts par query:**
- Phi-3 (local): $0
- SQL: $0
- Haiku: ~$0.0004 (300 tokens)
- **Total: $0.0004/query**

**Latence:**
- Step 1: 2-3s (Phi-3 local i7-6700)
- Step 2: <100ms (SQLite FTS5)
- Step 3: 3-5s (Haiku API)
- Step 4: <1ms (Python string)
- **Total: 5-8s**

### 12. RÉSUMÉ - Principes Clés

1. **Test bottom-up:** Data → SQL → LLM → API → Frontend
2. **Isolate components:** Tester chaque composant séparément
3. **Read, don't assume:** Lire le code/HTML réel
4. **Simple > Complex:** Code Python > Prompts complexes pour petits modèles
5. **Strategic logging:** Valeurs concrètes, pas messages génériques
6. **Verify reloads:** `systemctl restart` + `sleep` + `status`
7. **Monitor patterns:** Logging.warning pour détecter les phrasings problématiques
8. **Cost-optimize:** LLM local (Phi-3) pour parsing, API (Haiku) pour analyse
9. **Post-process:** Si le LLM n'est pas fiable, post-process en Python
10. **Match exactly:** CSS classes = HTML classes, character-for-character

---

## VERSION SYNTHÉTIQUE

### RAG Debugging Checklist - 1 Page

**Diagnostic Order (Bottom-Up):**
1. **Data:** `SELECT COUNT(*) FROM table` - Les données existent?
2. **Query:** Test SQL direct - La recherche fonctionne?
3. **LLM:** `curl` direct - Le parsing est correct?
4. **API:** Check logs - Les routes répondent?
5. **UI:** Inspect element - HTML/CSS match?

**Test Isolation:**
```bash
# ❌ Ne JAMAIS tester le système complet d'abord
curl /api/ask?q=test

# ✓ Tester chaque couche séparément
sqlite3 db.db "SELECT * FROM emails_fts WHERE ..."  # Data
curl http://localhost:8001/generate -d '{...}'      # LLM
curl http://localhost:8002/api/health               # API
```

**LLM Best Practices:**
- **Gros modèles** (Claude Opus, GPT-4): Prompts complexes OK
- **Petits modèles** (Phi-3, Mistral-7B): Code Python > Prompts
- **Parsing LLM output:** Multiline + try/catch, pas juste `json.loads()`
- **Post-processing:** `response.replace("bad", "good")` si LLM instable

**CSS/HTML Mismatch:**
```bash
# 1. Lire le HTML
grep 'class=\|id=' index.html

# 2. Mapper exactement dans CSS
# HTML: class="messages-container"
# CSS:  .messages-container { }
```

**Logging:**
```python
# ❌ Inutile
logging.info("Processing...")

# ✓ Utile
logging.info(f"query='{q}' → entities={e} → {len(r)} results")
```

**Service Restart:**
```bash
systemctl restart service && sleep 3 && systemctl status service
#                           ^^^^^^^^ IMPORTANT: wait for reload
```

**Cost Optimization:**
```
Local LLM (Phi-3): Intent parsing, formatage → $0
API LLM (Haiku):   Analyse seulement → $0.0004/query
SQL:               Fast search → $0
```

**Anti-Patterns:**
- ❌ Assumer (CSS matche HTML, model = nom fonction)
- ❌ Prompts complexes pour petits modèles
- ❌ Tester le système complet d'abord
- ❌ Logs génériques sans valeurs
- ❌ Oublier le `sleep` après restart

**Pipeline 4-Step:**
```
1. Intent Parse (Phi-3, 2s)  → {"entities": [...]}
2. SQL Execute (Python, 0.1s) → [results...]
3. Analyze (Haiku, 5s)        → {"findings": [...]}
4. Format (Python, 0ms)       → "Response text"
```

**Quick Fixes:**
```python
# Intent parsing - Multiline JSON
for line in response.split('\n'):
    if line.startswith('{'):
        return json.loads(line)

# Response formatting - Bypass LLM
response = " ".join(findings)
response = response.replace("LinkedIn profile", "LinkedIn emails")
response += f"\n\nSources: {sources}"

# CSS mapping - Read HTML first
classes_in_html = subprocess.check_output("grep class= index.html")
# Then write matching CSS
```

**Debug When Stuck:**
1. Read actual code/HTML (don't assume)
2. Test ONE component in isolation
3. Add logs with VALUES
4. Check which model is ACTUALLY running
5. Simplify (code > prompts for small models)

---

## PROMPT FINAL POUR DEBUGGING RAG

Tu débugues un système RAG qui ne fonctionne pas. Suis cette méthodologie:

**1. ISOLER LE PROBLÈME (bottom-up):**
- Data: `sqlite3 db.db "SELECT COUNT(*) FROM table"`
- SQL: Test la query exacte du code
- LLM: `curl` direct l'endpoint LLM
- API: Check `journalctl -u service`
- UI: Inspect element, compare HTML vs CSS

**2. ASSUMER = DANGER:**
- Lis le HTML réel avant d'écrire du CSS
- Vérifie quel modèle est VRAIMENT utilisé (pas juste le nom de fonction)
- Check les logs pour les vraies valeurs, pas ton intuition

**3. PETITS MODÈLES = CODE PYTHON:**
- Si Phi-3/Mistral-7B: Code Python > Prompts complexes
- Parsing: Multiline + try/catch, pas `json.loads()` direct
- Post-process: `response.replace()` si output instable

**4. LOGS STRATÉGIQUES:**
```python
logging.info(f"input='{x}' → processed='{y}' → output={len(z)} items")
```

**5. TEST EN ISOLATION:**
Jamais tester le système complet. Tester CHAQUE composant séparément.

**6. RESTART CORRECT:**
```bash
systemctl restart service && sleep 3 && systemctl status service
```

Apply this. Fix one thing at a time. Test after each fix.
