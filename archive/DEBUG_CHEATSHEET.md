# RAG Debugging - Cheatsheet Ultra-Synthétique

## Ordre de Diagnostic
```
1. Data    → sqlite3 "SELECT COUNT(*)"
2. SQL     → Test query directe
3. LLM     → curl endpoint direct
4. API     → journalctl -u service
5. UI      → Inspect element HTML vs CSS
```

## Golden Rules

### 🔍 Test Isolation
```bash
❌ curl /api/ask?q=test                    # Système complet
✓  sqlite3 db "SELECT * FROM ..."         # Data layer
✓  curl localhost:8001/generate           # LLM layer
✓  curl localhost:8002/api/health         # API layer
```

### 🤖 LLM Strategy
| Model | Approach |
|-------|----------|
| Claude Opus, GPT-4 | Prompts complexes OK |
| Phi-3, Mistral-7B, Llama-7B | **Code Python > Prompts** |

### 📝 Logging
```python
❌ logging.info("Processing...")
✓  logging.info(f"q='{query}' → {len(results)} results")
```

### 🎨 CSS/HTML
```bash
grep 'class=\|id=' index.html  # Lire AVANT d'écrire CSS
```

### 🔄 Service Restart
```bash
systemctl restart srv && sleep 3 && systemctl status srv
#                        ^^^^^^^^ CRITIQUE
```

## Quick Fixes

### Intent Parsing (LLM retourne du bruit)
```python
for line in response.split('\n'):
    if line.startswith('-'):
        line = line.split(':', 1)[-1].strip()
    if line.startswith('{'):
        try:
            return json.loads(line)
        except:
            continue
```

### Response Formatting (Bypass LLM instable)
```python
# Au lieu de prompt complexe → LLM
findings = haiku_json.get("findings", [])
response = " ".join(findings)
response = response.replace("LinkedIn profile", "LinkedIn emails")
response += f"\n\nSources: {sources}"
```

### CSS Mismatch
```python
# HTML: <div class="messages-container">
# CSS:  .messages-container { }  ← Match EXACT
```

## Anti-Patterns
- ❌ Assumer (CSS matche, model = nom fonction)
- ❌ Prompts 50 lignes pour Phi-3
- ❌ Tester système complet d'abord
- ❌ Oublier `sleep` après restart

## Pipeline RAG Typique
```
Intent (Phi-3, 2s, $0) → SQL (0.1s, $0) → Analyze (Haiku, 5s, $0.0004) → Format (Python, 0ms, $0)
```

## Stuck? Checklist
1. [ ] Read actual code (don't assume)
2. [ ] Test ONE component isolated
3. [ ] Add logs with VALUES
4. [ ] Check ACTUAL model running
5. [ ] Simplify (code > prompts)
6. [ ] Restart with `sleep 3`

## Cost Optimization
- Local LLM: Intent parsing + formatage → **$0**
- API LLM: Analyse ONLY → **$0.0004/query**
- Total: **~$0.0004/query** (200 queries = $0.08)

---

**Méthodologie complète:** `/opt/rag/METHODOLOGY_PROMPT.md`
