# Méthodologie de Debugging RAG - Documentation

Cette documentation capture toute la méthodologie apprise lors du debugging du système L Investigation Framework.

## 📁 Fichiers Disponibles

### 1. `METHODOLOGY_PROMPT.md` (19K, 633 lignes) ⭐ VERSION COMPLÈTE
**Utilisation:** Formation approfondie, référence complète

**Contenu:**
- Architecture détaillée du système RAG (4 étapes)
- Méthodologie de diagnostic bottom-up complète
- Exemples concrets de chaque problème rencontré
- Solutions avec code Python complet
- Explication des choix techniques (pourquoi Haiku, pourquoi bypass Phi-3)
- Tests d'isolation pour chaque couche
- Logging stratégique avec exemples
- Prompt engineering (gros vs petits modèles)
- Anti-patterns détaillés
- Workflow de debugging complet
- Version synthétique incluse à la fin

**Quand l'utiliser:**
- Formation d'un nouveau développeur sur le système
- Comprendre EN PROFONDEUR la méthodologie
- Référence lors de problèmes complexes
- Documentation pour l'équipe

---

### 2. `DEBUG_CHEATSHEET.md` (2.5K, 100 lignes) ⚡ VERSION RAPIDE
**Utilisation:** Référence rapide pendant le debugging

**Contenu:**
- Checklist de diagnostic (5 étapes)
- Golden rules (Test Isolation, LLM Strategy, Logging, CSS/HTML)
- Quick fixes prêts à copier/coller
- Tableaux de référence (quels modèles, quelle approche)
- Anti-patterns (ce qu'il NE faut PAS faire)
- Pipeline RAG avec latences et coûts
- Checklist "Stuck?"

**Quand l'utiliser:**
- En plein debugging, besoin d'une référence rapide
- Rappel des golden rules
- Copier/coller des quick fixes
- Checklist quand on est bloqué

**Format:** 1 page A4, imprimable, facile à scanner

---

### 3. `PROMPT_READY_TO_USE.txt` (3.7K, 106 lignes) 🤖 COPIER/COLLER
**Utilisation:** Prompt système pour un LLM

**Contenu:**
- Méthodologie de diagnostic condensée
- Règles d'or
- Quick fixes
- Anti-patterns
- Pipeline RAG
- LLM strategy
- Workflow debugging
- Checklist

**Quand l'utiliser:**
- Copier/coller ce texte dans un chat LLM (Claude, GPT-4)
- System prompt pour un agent de debugging
- Partager rapidement la méthodologie (email, Slack)
- Onboarding rapide d'un collaborateur

**Format:** Plain text, optimisé pour être utilisé comme prompt

---

## 🎯 Cas d'Usage

### Scénario 1: Nouveau Bug RAG
1. Ouvrir `DEBUG_CHEATSHEET.md` → Checklist de diagnostic
2. Suivre les 5 étapes (Data → SQL → LLM → API → UI)
3. Si bloqué → "Stuck? Checklist"
4. Si besoin de comprendre pourquoi → `METHODOLOGY_PROMPT.md`

### Scénario 2: Former un Développeur
1. Lire `METHODOLOGY_PROMPT.md` (version détaillée)
2. Pratiquer avec des exemples réels
3. Garder `DEBUG_CHEATSHEET.md` comme référence quotidienne

### Scénario 3: Utiliser un LLM pour Debugger
1. Copier le contenu de `PROMPT_READY_TO_USE.txt`
2. Coller dans Claude/GPT-4 comme system prompt
3. Décrire le bug
4. Le LLM appliquera la méthodologie

### Scénario 4: Code Review
1. Vérifier les anti-patterns dans `DEBUG_CHEATSHEET.md`
2. S'assurer que le code suit les golden rules
3. Vérifier la stratégie LLM (gros vs petit modèle)

---

## 📊 Méthodologie en Bref

### Diagnostic Bottom-Up (Toujours dans cet ordre!)
```
1. Data    → sqlite3 "SELECT COUNT(*)"
2. SQL     → Test query directe
3. LLM     → curl endpoint direct
4. API     → journalctl + curl /health
5. UI      → Inspect HTML vs CSS
```

### Golden Rules
1. **Test Isolation:** UN composant à la fois, jamais le système complet d'abord
2. **Read, Don't Assume:** Lire le code/HTML réel, jamais assumer
3. **Small Models = Code:** Phi-3/Mistral-7B → Code Python > Prompts complexes
4. **Strategic Logs:** Valeurs concrètes (`f"q={q} → {len(r)} results"`)
5. **Restart Properly:** `systemctl restart && sleep 3 && status`

### Quick Fixes Essentiels

**LLM Output Parsing:**
```python
for line in response.split('\n'):
    if line.startswith('{'):
        try:
            return json.loads(line)
        except:
            continue
```

**Bypass LLM Instable:**
```python
response = " ".join(findings)
response = response.replace("bad phrase", "good phrase")
response += f"\n\nSources: {sources}"
```

**CSS/HTML Mismatch:**
```bash
grep 'class=\|id=' index.html  # Lire AVANT d'écrire CSS
```

---

## 🚀 Exemples Concrets (Bugs Résolus)

### Bug 1: "No Results" pour "Who is Jeffrey Epstein?"
- **Symptôme:** API retourne "I couldn't find relevant documents"
- **Diagnostic:** Data OK (13009 emails) → SQL OK (1130 matches) → LLM parsing FAIL
- **Root cause:** Phi-3 retournait `"- response: {...}"` → JSON parser échouait → fallback `entities=[]`
- **Fix:** Multiline JSON parsing avec extraction du premier `{...}` valide
- **Fichier:** `METHODOLOGY_PROMPT.md` Section 2.2

### Bug 2: "Discord Look Like Tetris"
- **Symptôme:** CSS Discord appliqué mais layout cassé
- **Diagnostic:** CSS OK → HTML lu → MISMATCH trouvé
- **Root cause:** CSS `.chat-container` mais HTML `.messages-container`
- **Fix:** Mapper exactement CSS classes sur HTML classes
- **Fichier:** `METHODOLOGY_PROMPT.md` Section 3

### Bug 3: Phi-3 Génère du HTML au lieu de Texte
- **Symptôme:** Response = `"<div style='text-align:justify'>..."`
- **Diagnostic:** Prompt trop complexe pour Phi-3-Mini
- **Root cause:** 50 lignes de règles → Phi-3 confused → hallucination
- **Fix:** Bypass Phi-3, faire du string templating Python
- **Fichier:** `METHODOLOGY_PROMPT.md` Section 5

---

## 💡 Principes Clés Appris

1. **Bottom-Up Debugging:** Toujours commencer par la couche la plus basse (data)
2. **Isolation Testing:** Tester chaque composant séparément avant le système
3. **Model Awareness:** Phi-3 ≠ Mistral ≠ Claude, adapter la stratégie
4. **Cost Optimization:** Local LLM pour parsing/formatage, API pour analyse
5. **Simplicity Wins:** Code Python simple > Prompts complexes pour petits modèles
6. **Monitor Patterns:** Logs de warning pour détecter les phrasings problématiques
7. **Verify Everything:** Ne jamais assumer (CSS matche, model = nom fonction)

---

## 📈 Métriques Système

**Pipeline Optimisé:**
```
Step 1: Intent Parse (Phi-3, 2s, $0)
Step 2: SQL Execute (Python, 0.1s, $0)
Step 3: Analyze (Haiku, 5s, $0.0004)
Step 4: Format (Python, 0ms, $0)

Total: 5-8s latency, $0.0004/query
```

**Cost per 1000 queries:** $0.40

---

## 🔗 Liens Rapides

- **Détails complets:** `/opt/rag/METHODOLOGY_PROMPT.md`
- **Cheatsheet rapide:** `/opt/rag/DEBUG_CHEATSHEET.md`
- **Prompt LLM:** `/opt/rag/PROMPT_READY_TO_USE.txt`
- **Ce README:** `/opt/rag/METHODOLOGY_README.md`

---

**Dernière mise à jour:** 2026-01-08
**Basé sur:** Session de debugging L Investigation Framework
**Système:** RAG 4-step pipeline (Phi-3 + SQLite FTS5 + Claude Haiku)
