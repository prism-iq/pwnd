# L INVESTIGATION FRAMEWORK - MASTER CONTEXT

## P0 - SECURITY (NEVER BREAK)

### Absolute Rules
- Services bind `127.0.0.1` ONLY (never 0.0.0.0)
- SQL: parameterized queries ALWAYS, never f-strings with user input
- No `eval()`, `exec()`, `subprocess` with user input
- LLM proposes, script applies - LLM NEVER executes directly
- Validate ALL inputs before processing
- DB permissions: 600 (owner read/write only)

### Current Security Status
```
PORTS:
- 22/tcp    SSH (key-only, no password)
- 80/tcp    Caddy (public)
- 443/tcp   Caddy (public)
- 8001/tcp  LLM (127.0.0.1 only)
- 8002/tcp  API (127.0.0.1 only)
```

---

## P1 - TECHNICAL CONSTRAINTS (CRITICAL)

### Python/Bash Heredoc Fix
When generating Python code via bash heredocs, NEVER use `\n` in f-strings.
Bash interprets `\n` and breaks the code.

**WRONG:**
```python
prompt = f"Context:\n{context}\n\nQuestion: {q}"
```

**CORRECT:**
```python
NL = chr(10)
prompt = f"Context:{NL}{context}{NL}{NL}Question: {q}"
```

### HTTP Client
Use `httpx.AsyncClient` for async HTTP calls, NOT urllib or requests.

```python
async with httpx.AsyncClient(timeout=180.0) as client:
    response = await client.post(url, json=data)
```

### Heredoc Quoting
Always quote heredoc delimiters to prevent bash interpretation:
```bash
cat > file.py << 'PYEOF'
# code here won't be interpreted by bash
PYEOF
```

---

## P2 - SERVER ENVIRONMENT

```
Server: root@88.99.151.62
OS: Arch Linux
CPU: i7-6700
RAM: 64GB
GPU: None (CPU inference only)

Project: /opt/rag/
Public URL: https://pwnd.icu
```

### Directory Structure (Current)
```
/opt/rag/
├── db/
│   ├── sources.db      # 993MB - raw emails (READ-ONLY)
│   ├── graph.db        # nodes, edges, properties, aliases
│   ├── scores.db       # scores, flags
│   ├── audit.db        # evidence_chain, hypotheses, contradictions
│   └── sessions.db     # conversations, messages, settings
├── llm/
│   └── backend.py      # Mistral 7B server (port 8001)
├── venv/               # Python virtual environment
├── backup/             # DB backups
├── .git/
└── LICENSE
```

### Structure to Create
```
/opt/rag/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── db.py           # DB connections (multi-db)
│   ├── models.py       # Pydantic models
│   ├── search.py       # FTS search functions
│   ├── routes.py       # FastAPI routes
│   ├── llm_client.py   # Mistral + Haiku clients
│   ├── pipeline.py     # Query → LLM → SQL → Haiku → Update flow
│   └── main.py         # FastAPI app
├── static/
│   ├── style.css
│   ├── app.js
│   └── index.html
├── templates/          # Bash generators (source of truth)
│   ├── backend.sh
│   ├── frontend.sh
│   └── services.sh
├── scripts/
│   └── rebuild.sh
└── db/                 # (exists)
```

---

## P3 - DATABASE SCHEMAS

### sources.db (READ-ONLY - Do not modify)
Raw email corpus. 13,009 emails parsed with participants, domains, attachments.

**Key tables:**
- `documents` - doc metadata (id, filename, doc_type, status)
- `emails` - parsed emails (subject, sender, recipients, body_text, date_sent)
- `email_participants` - from/to/cc/bcc with email, name, domain
- `contents` - full text
- `emails_fts` - FTS on subject + body_text
- `domains` - unique domains with occurrence_count

**Stats:**
- documents: 13,010
- emails: 13,009
- email_participants: 31,783
- domains: 2,243
- attachments: 71

### graph.db (Knowledge Graph)
```sql
-- Everything is a node
CREATE TABLE nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,              -- 'person', 'company', 'email', 'flight', etc
    name TEXT NOT NULL,
    name_normalized TEXT,
    source_db TEXT,                  -- 'sources' if from sources.db
    source_id INTEGER,               -- doc_id in sources.db
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    created_by TEXT DEFAULT 'system'
);

-- Dynamic key-value properties
CREATE TABLE properties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    value_type TEXT DEFAULT 'text',
    source_node_id INTEGER REFERENCES nodes(id),
    excerpt TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    created_by TEXT DEFAULT 'system'
);

-- Relationships between nodes
CREATE TABLE edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    to_node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    type TEXT NOT NULL,              -- 'sent_email', 'flew_with', 'paid', etc
    directed INTEGER DEFAULT 1,
    source_node_id INTEGER REFERENCES nodes(id),
    excerpt TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    created_by TEXT DEFAULT 'system',
    UNIQUE(from_node_id, to_node_id, type)
);

-- Alternative names
CREATE TABLE aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    alias_normalized TEXT NOT NULL,
    alias_type TEXT DEFAULT 'aka',
    source_node_id INTEGER REFERENCES nodes(id),
    confidence INTEGER DEFAULT 50,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(node_id, alias_normalized)
);

-- FTS: nodes_fts, aliases_fts (with triggers)
```

### scores.db (Metrics)
```sql
-- Universal scoring for any node or edge
CREATE TABLE scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type TEXT NOT NULL,       -- 'node' or 'edge'
    target_id INTEGER NOT NULL,
    
    -- CERTITUDE
    confidence INTEGER DEFAULT 50,   -- 0-100
    source_count INTEGER DEFAULT 0,
    source_diversity INTEGER DEFAULT 50,
    
    -- IMPORTANCE
    pertinence INTEGER DEFAULT 50,   -- 0-100
    centrality INTEGER DEFAULT 0,    -- calculated
    uniqueness INTEGER DEFAULT 50,
    
    -- SUSPICION
    suspicion INTEGER DEFAULT 0,     -- 0-100
    anomaly INTEGER DEFAULT 0,       -- 0-100
    
    -- TEMPORALITY
    first_seen TEXT,
    last_seen TEXT,
    frequency REAL DEFAULT 0,
    decay REAL DEFAULT 1.0,
    
    -- STATE
    status TEXT DEFAULT 'raw',       -- 'raw', 'analyzed', 'verified', 'refuted'
    needs_review INTEGER DEFAULT 0,
    review_priority INTEGER DEFAULT 0,
    locked INTEGER DEFAULT 0,
    
    conflict_severity INTEGER DEFAULT 0,
    touch_count INTEGER DEFAULT 0,
    updated_at TEXT DEFAULT (datetime('now')),
    
    UNIQUE(target_type, target_id)
);

-- Red flags
CREATE TABLE flags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type TEXT NOT NULL,
    target_id INTEGER NOT NULL,
    flag_type TEXT NOT NULL,         -- 'timing', 'amount', 'pattern', 'association', 'crypto', 'stegano', 'manual'
    description TEXT,
    severity INTEGER DEFAULT 50,
    source_node_id INTEGER,
    created_by TEXT DEFAULT 'system',
    active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);
```

### audit.db (Logs)
```sql
-- Immutable log of all changes
CREATE TABLE evidence_chain (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type TEXT NOT NULL,
    target_id INTEGER NOT NULL,
    action TEXT NOT NULL,            -- 'created', 'confidence_up', 'flagged', etc
    field TEXT,
    old_value TEXT,
    new_value TEXT,
    delta INTEGER,
    reason TEXT NOT NULL,
    source_node_id INTEGER,
    created_by TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

-- LLM-proposed changes awaiting validation
CREATE TABLE hypotheses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    statement TEXT NOT NULL,
    hypothesis_type TEXT DEFAULT 'inference',
    proposed_updates TEXT,           -- JSON
    status TEXT DEFAULT 'pending',   -- 'pending', 'approved', 'rejected'
    session_id TEXT,
    triggered_by TEXT,
    created_by TEXT NOT NULL,
    evaluated_by TEXT,
    evaluation_reason TEXT,
    evaluated_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Conflicting information
CREATE TABLE contradictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ref1_type TEXT NOT NULL,
    ref1_id INTEGER NOT NULL,
    ref2_type TEXT NOT NULL,
    ref2_id INTEGER NOT NULL,
    description TEXT NOT NULL,
    severity INTEGER DEFAULT 50,
    resolution TEXT,
    resolution_reason TEXT,
    resolved_by TEXT,
    resolved_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
```

### sessions.db (Frontend State)
```sql
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    title TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,              -- 'user', 'assistant', 'system'
    content TEXT NOT NULL,
    is_auto INTEGER DEFAULT 0,       -- 1 if LLM auto-generated
    auto_depth INTEGER DEFAULT 0,
    tokens_in INTEGER,
    tokens_out INTEGER,
    model TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE auto_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    status TEXT DEFAULT 'running',   -- 'running', 'completed', 'stopped', 'limit_reached'
    query_count INTEGER DEFAULT 0,
    max_queries INTEGER DEFAULT 20,
    started_at TEXT DEFAULT (datetime('now')),
    stopped_at TEXT
);

CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);
-- Defaults: theme=dark, auto_max_queries=20, language=fr, show_confidence=1, show_sources=1
```

---

## P4 - SYSTEM ARCHITECTURE

### Data Flow
```
USER QUESTION
      ↓
  MISTRAL (local, free)
  - Understands question
  - Generates structured query
      ↓
  {query_type: "relation", entities: [...], filters: [...]}
      ↓
  PYTHON SCRIPT
  - Validates query
  - Executes SQL on graph.db + sources.db
      ↓
  {results: [...], context_snippets: [...]}
      ↓
  HAIKU API (~0.001€/query)
  - Receives: SQL results + schema + scoring rules
  - Returns: structured JSON (not prose)
      ↓
  {
    answer_summary: "...",
    confidence: 78,
    hypotheses: [{statement, proposed_updates, evidence}],
    flags: [{target, flag_type, severity}],
    new_nodes: [...],
    new_edges: [...]
  }
      ↓
  PYTHON SCRIPT
  - Validates proposed changes
  - Applies to graph.db, scores.db
  - Logs to audit.db
      ↓
  MISTRAL (local)
  - Formats response for user
      ↓
USER RESPONSE
```

### Anti-Manipulation Rules
1. **Evidence-based only**: Score changes require new source/evidence
2. **No repetition gaming**: Same question twice = no score change
3. **Counter-evidence required**: Before increasing suspicion, check for contradictions
4. **Source diversity**: 1 source vs 10 different sources = different weight
5. **Decay**: Unconfirmed hypotheses decay over time
6. **Audit trail**: Every change logged with reason

### LLM Separation of Powers
- **Mistral (front)**: Understands user, formats responses. CANNOT modify DB directly.
- **Haiku (back)**: Evaluates hypotheses, decides scores. Doesn't see user pressure.
- **Scripts**: Actually apply changes. Validate everything.

---

## P5 - API ENDPOINTS

### Core
```
GET  /api/health              → {status: "ok"}
GET  /api/stats               → {nodes, edges, sources, ...}
```

### Search
```
GET  /api/search?q=...        → [{id, type, name, snippet, score}]
GET  /api/search/emails?q=... → FTS on sources.db
GET  /api/search/nodes?q=...  → FTS on graph.db
```

### Graph
```
GET  /api/nodes?type=...&limit=...
GET  /api/nodes/{id}
GET  /api/nodes/{id}/edges
GET  /api/nodes/{id}/properties
GET  /api/nodes/{id}/scores
GET  /api/edges?type=...
GET  /api/edges/{id}
```

### Investigation (main endpoint)
```
GET  /api/ask?q=...           → SSE stream
     - Streams: {type: "status", msg: "searching..."}
     - Streams: {type: "chunk", text: "..."}
     - Streams: {type: "sources", ids: [...]}
     - Streams: {type: "updates", changes: [...]}
     - Final:   {type: "done"}
```

### Auto-Investigation
```
POST /api/auto/start          → {session_id, status: "running"}
     body: {conversation_id, max_queries: 20}
POST /api/auto/stop           → {status: "stopped"}
GET  /api/auto/status         → {running, query_count, max_queries}
```

### Sessions
```
GET  /api/conversations
POST /api/conversations
GET  /api/conversations/{id}/messages
GET  /api/settings
PUT  /api/settings
```

---

## P6 - FRONTEND SPEC

### Stack
- Vanilla JS (no framework)
- Single HTML file
- CSS variables for theming
- localStorage for offline persistence
- SSE for streaming responses

### Features
- Dark theme (default)
- Conversation sidebar
- Settings panel
- Auto-investigation toggle with counter (max 20)
- Confidence/suspicion badges on entities
- Source citations (clickable)
- Real-time streaming responses

### Layout
```
┌─────────────────────────────────────────────────┐
│ [Logo] L Investigation          [Settings] [?] │
├──────────────┬──────────────────────────────────┤
│              │                                  │
│ Conversations│     Chat Area                    │
│ + New Chat   │                                  │
│              │     [Message]                    │
│ > Chat 1     │     [Message with sources]       │
│   Chat 2     │     [Message]                    │
│   Chat 3     │                                  │
│              │                                  │
│              ├──────────────────────────────────│
│ [Auto: OFF]  │ [________________] [Send]        │
│ [0/20]       │ [Auto-investigate: ○]            │
└──────────────┴──────────────────────────────────┘
```

---

## P7 - SERVICES

### systemd Units

**l-api.service**
```ini
[Unit]
Description=L Investigation API
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/rag
Environment=PATH=/opt/rag/venv/bin:/usr/bin
ExecStart=/opt/rag/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8002
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

**l-llm.service**
```ini
[Unit]
Description=L Investigation LLM Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/rag/llm
ExecStart=/opt/rag/venv/bin/python backend.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Caddy (/etc/caddy/Caddyfile)
```
pwnd.icu {
    reverse_proxy /api/* 127.0.0.1:8002
    reverse_proxy 127.0.0.1:8002
    
    encode gzip
    
    header {
        X-Content-Type-Options nosniff
        X-Frame-Options DENY
        X-XSS-Protection "1; mode=block"
        Referrer-Policy strict-origin-when-cross-origin
        Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"
    }
}
```

---

## P8 - REBUILD WORKFLOW

### Template System
Templates in `/opt/rag/templates/` generate code. They are the SOURCE OF TRUTH.

```bash
./scripts/rebuild.sh                 # Full rebuild + restart
./scripts/rebuild.sh --backend       # Backend only
./scripts/rebuild.sh --frontend      # Frontend only
./scripts/rebuild.sh --services      # Services only
./scripts/rebuild.sh --no-restart    # No service restart
```

### Template Structure
Each template is a bash script that generates files using heredocs:

```bash
#!/bin/bash
# templates/backend.sh
cat > /opt/rag/app/config.py << 'PYEOF'
# Python code here
PYEOF
```

**CRITICAL**: Always use `<< 'PYEOF'` (quoted) to prevent bash interpretation.

---

## P9 - DEPENDENCIES

### Python (in venv)
```
fastapi
uvicorn
httpx
pydantic
python-multipart
```

### System
```
sqlite3 (installed)
caddy (installed)
python 3.x (installed)
```

### LLM
- Mistral 7B GGUF in `/opt/rag/llm/`
- llama-cpp-python or similar backend

---

## P10 - MODULES (crypto & stegano)

### modules/crypto.py
Détection d'anomalies cryptographiques et patterns suspects.

**Fonctions:**
```python
def analyze_entropy(data: bytes) -> dict:
    """
    Calcule l'entropie de Shannon.
    Retourne: {entropy: float, is_anomalous: bool, threshold: 7.5}
    Haute entropie (>7.5) = possiblement chiffré/compressé
    """

def detect_patterns(text: str) -> list[dict]:
    """
    Détecte patterns suspects dans le texte:
    - Codes (A1B2C3, répétitions)
    - Base64 embedded
    - Hex strings
    - Montants récurrents
    - Dates suspectes (patterns temporels)
    Retourne: [{pattern_type, value, count, positions}]
    """

def analyze_amounts(amounts: list[float]) -> dict:
    """
    Analyse liste de montants pour anomalies:
    - Montants ronds suspects
    - Séquences (1000, 2000, 3000)
    - Récurrences exactes
    Retourne: {anomalies: [], recurring: [], round_amounts: []}
    """

def detect_code_words(text: str, known_codes: list = None) -> list[dict]:
    """
    Détecte potentiels mots de code:
    - Mots hors contexte
    - Capitalisation anormale
    - Répétitions suspectes
    Retourne: [{word, frequency, contexts, suspicion_score}]
    """
```

### modules/stegano.py
Détection de données cachées dans fichiers.

**Fonctions:**
```python
def check_image(filepath: str) -> dict:
    """
    Analyse image pour stéganographie:
    - LSB analysis
    - EOF data
    - Metadata excessif
    - Dimensions anormales
    Retourne: {has_hidden_data: bool, confidence: float, method_suspected: str}
    """

def check_attachment(filepath: str, content_type: str) -> dict:
    """
    Analyse attachment générique:
    - Mismatch extension/content
    - Embedded files
    - Streams cachés
    Retourne: {suspicious: bool, findings: [], entropy: float}
    """

def extract_metadata(filepath: str) -> dict:
    """
    Extrait et analyse metadata:
    - EXIF (images)
    - PDF metadata
    - Office doc properties
    Retourne: {metadata: {}, anomalies: [], hidden_fields: []}
    """
```

### Intégration des modules
Les modules retournent des **FAITS**, pas des jugements. Le LLM interprète.

```python
# Dans pipeline.py
from modules import crypto, stegano

async def analyze_source(source_id: int):
    # Get source data
    source = get_source(source_id)
    
    # Run crypto analysis
    patterns = crypto.detect_patterns(source.content)
    amounts = crypto.analyze_amounts(extract_amounts(source.content))
    
    # Flag if anomalies found
    for pattern in patterns:
        if pattern['count'] > 3:
            create_flag(
                target_type='node',
                target_id=source_node_id,
                flag_type='pattern',
                description=f"Pattern {pattern['pattern_type']}: {pattern['value']}",
                severity=min(pattern['count'] * 10, 100)
            )
```

---

## P11 - UNIVERSAL NODE PHILOSOPHY

### Everything is a Node
Chaque élément de l'enquête = un node. Pas de tables spécifiques rigides.

```python
# Exemples de nodes
Node(type="person", name="Jeffrey Epstein")
Node(type="person", name="Donald Trump")
Node(type="company", name="Amazon")
Node(type="email", name="email:12345", source_id=12345)
Node(type="flight", name="Flight NYC-VI 2003-04-12")
Node(type="amount", name="$1,247.00")
Node(type="phone", name="+1-555-0123")
Node(type="subscription", name="newsletter:dailynews.vi")
Node(type="pattern", name="weekly_payment_1000")
```

### Everything Can Be Evidence
Même les trucs banals. Le LLM connecte les points.

```
44 mentions Amazon = peut-être rien
44 mentions Amazon + même montant + même jour du mois = pattern suspect
```

### Universal Metrics on Everything
Chaque node ET chaque edge a:
```python
{
    # Certitude
    "confidence": 0-100,      # Cette info est-elle vraie?
    "source_count": int,      # Combien de sources
    "source_diversity": 0-100,# Sources variées ou même origine?
    
    # Importance
    "pertinence": 0-100,      # Utile à l'enquête?
    "centrality": 0-100,      # Combien de connexions (auto-calculé)
    "uniqueness": 0-100,      # Rare ou banal?
    
    # Suspicion
    "suspicion": 0-100,       # C'est louche?
    "anomaly": 0-100,         # Dévie du pattern normal?
    
    # Temporal
    "first_seen": datetime,
    "last_seen": datetime,
    "decay": float            # Poids décroit si pas confirmé
}
```

### Evidence Chain (Traçabilité)
Chaque changement de score est loggé avec raison:
```python
{
    "target": "node:trump",
    "field": "suspicion",
    "old_value": 40,
    "new_value": 55,
    "delta": +15,
    "reason": "Vol commun avec Epstein confirmé par flight log",
    "source_node_id": 12345,  # L'email/doc qui prouve
    "created_by": "haiku"
}
```

---

## P12 - ANTI-MANIPULATION RULES

### The Problem
Un utilisateur malveillant pose 100x la même question biaisée → score monte artificiellement → conclusions fausses.

### Solution: Separation of Powers
```
┌─────────────────────────────────────────────────┐
│  USER                                           │
│    ↓                                            │
│  MISTRAL (local, gratuit)                       │
│  - Comprend la question                         │
│  - Formule des HYPOTHÈSES                       │
│  - NE PEUT PAS modifier les scores              │
│    ↓                                            │
│  hypotheses queue (audit.db)                    │
│    ↓                                            │
│  HAIKU (API, ~0.001€/query)                     │
│  - Ne voit PAS les questions user               │
│  - Voit: hypothèses + données + résumé global   │
│  - Évalue: nouveau? basé sur quoi? contre-preuve?│
│  - SEUL autorisé à modifier scores              │
│    ↓                                            │
│  graph.db / scores.db enrichis                  │
└─────────────────────────────────────────────────┘
```

### Rules Implemented in Code
```python
# 1. Evidence-based only
def update_score(target, field, new_value, evidence_source_id):
    if evidence_source_id is None:
        raise ValueError("Cannot update score without evidence")
    
    # Check if this evidence was already used
    existing = get_evidence_chain(target, source_id=evidence_source_id)
    if existing:
        return  # Same evidence = no change

# 2. Counter-evidence required
def increase_suspicion(target, delta, evidence):
    # Before increasing, search for contradicting evidence
    counter = search_counter_evidence(target, evidence)
    if counter:
        delta = delta * 0.5  # Reduce impact
        log_contradiction(target, evidence, counter)

# 3. Source diversity weighting
def calculate_confidence(target):
    sources = get_sources_for(target)
    unique_authors = set(s.author for s in sources)
    diversity = len(unique_authors) / len(sources)
    return base_confidence * diversity

# 4. Decay over time
def apply_decay():
    """Run periodically"""
    old_hypotheses = get_hypotheses(status='pending', age_days > 7)
    for h in old_hypotheses:
        h.confidence *= 0.9  # 10% decay per week
```

---

## P13 - HAIKU BUREAUCRAT ROLE

### What Haiku Does (Batch Processing)
Haiku est un **bureaucrate**. Il compte, classe, structure. ZERO jugement initial.

```python
# Haiku batch job sur sources.db
async def process_email_batch(email_ids: list[int]):
    for email_id in email_ids:
        email = get_email(email_id)
        
        # 1. Extract entities (NER basique)
        entities = extract_entities(email.body_text)
        for entity in entities:
            create_or_get_node(type=entity.type, name=entity.name)
        
        # 2. Count mentions (pas de jugement)
        for node in mentioned_nodes:
            increment_mention_count(node)
        
        # 3. Create edges (factuel)
        create_edge(from=sender_node, to=recipient_node, type="emailed")
        
        # 4. Flag technical anomalies (pas d'interprétation)
        entropy = crypto.analyze_entropy(email.body_text)
        if entropy['is_anomalous']:
            create_flag(target=email_node, flag_type='crypto', 
                       description=f"High entropy: {entropy['entropy']}")
```

### What Haiku Evaluates (Per Query)
Quand Mistral propose une hypothèse, Haiku évalue:

```python
# Input pour Haiku
{
    "hypothesis": "Trump a voyagé avec Epstein",
    "proposed_changes": [
        {"target": "node:trump", "field": "suspicion", "delta": +20}
    ],
    "evidence_cited": ["flight_log:123"],
    "current_scores": {"trump.suspicion": 40},
    "counter_evidence_found": [],
    "similar_past_hypotheses": []
}

# Output de Haiku (structured JSON, pas de prose)
{
    "approved": true,
    "adjusted_delta": +15,  # Réduit car evidence single-source
    "reason": "Flight log confirms, but single source",
    "new_flags": [],
    "contradictions_noted": []
}
```

---

## P14 - MISSION

### Immediate Tasks
1. Create `/opt/rag/app/` with all Python modules
2. Create `/opt/rag/static/` with frontend
3. Create `/opt/rag/templates/` with generators
4. Create `/opt/rag/scripts/rebuild.sh`
5. Test all endpoints
6. Verify security (no exposed ports)

### Quality Checklist
- [ ] All SQL uses parameterized queries
- [ ] All user input is validated
- [ ] Services bind 127.0.0.1 only
- [ ] DB files are 600 permissions
- [ ] FTS triggers work correctly
- [ ] SSE streaming works
- [ ] Auto-investigation stops at 20 queries
- [ ] Evidence chain logs all changes

### DO NOT
- Modify sources.db
- Use `eval()` or `exec()` with user input
- Expose internal ports
- Trust LLM output without validation
- Use `\n` in heredoc Python f-strings
- Generate SQL from LLM output directly

---

## QUICK REFERENCE

### Server Access
```bash
ssh root@88.99.151.62
cd /opt/rag
source venv/bin/activate
```

### Status Check
```bash
systemctl status l-api l-llm caddy --no-pager
ss -tlnp | grep -E "800[12]|80|443"
```

### Logs
```bash
journalctl -u l-api -f
journalctl -u l-llm -f
```

### DB Quick Access
```bash
sqlite3 /opt/rag/db/graph.db ".tables"
sqlite3 /opt/rag/db/sources.db "SELECT COUNT(*) FROM emails"
```
