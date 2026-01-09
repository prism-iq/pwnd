# Claude Context - L Investigation Framework

**Last Updated:** 2026-01-08
**Version:** 1.0.0
**Public URL:** https://pwnd.icu
**Repository:** /opt/rag

---

## Quick Context for Future Claude Sessions

When you resume work on this project, here's what you need to know:

### What This Is

L Investigation Framework is an OSINT investigation platform that combines:
- **13,009 emails** (948MB corpus, 2007-2021) in SQLite FTS
- **Graph database** (14,437 nodes, 3,034 edges) for entity relationships
- **Dual-LLM pipeline**: Phi-3-Mini 4K (intent parsing) + Claude Haiku (analysis)
- **Auto-investigation**: Recursive query chaining based on AI-suggested questions
- **Real-time SSE streaming**: FastAPI → Browser with live updates

### Architecture

```
Browser (https://pwnd.icu)
  ↓ SSE Stream
FastAPI (127.0.0.1:8002) ← Caddy (0.0.0.0:80/443)
  ↓
Phi-3-Mini 4K (127.0.0.1:8001) - Intent parsing (2-3s)
  ↓
SQLite (sources.db, graph.db, sessions.db)
  ↓
Claude Haiku API - Analysis (3-5s)
```

### File Structure

```
/opt/rag/
├── app/                    # FastAPI application
│   ├── main.py            # App entry point
│   ├── routes.py          # API endpoints
│   ├── pipeline.py        # 4-step LLM flow
│   ├── db.py              # SQLite connection pool
│   └── llm_client.py      # Mistral + Haiku clients
├── static/                # Frontend
│   ├── index.html         # Main UI
│   ├── app.js             # Frontend logic (598 lines)
│   └── style.css          # Dark theme (1212 lines)
├── db/
│   ├── sources.db         # Emails (948MB, 13k emails)
│   ├── graph.db           # Entities (3.7MB, 14k nodes)
│   └── sessions.db        # Conversations
├── llm/
│   └── Phi-3-mini-4k-instruct-q4.gguf  # Phi-3-Mini model (2.4GB, NOT in git)
├── scripts/
│   ├── rebuild.sh         # Restart all services
│   ├── extract_entities.sh # Haiku NER (~$1.63 cost)
│   └── migrate_to_postgres.sh # SQLite → PostgreSQL
├── config/
│   └── llm_tuning.yaml    # Performance settings
└── docs/                  # You are here
```

### Database Schema

**sources.db:**
```sql
emails (doc_id, message_id, subject, date_sent, sender_email,
        sender_name, recipients_to, body_text, body_html, ...)
emails_fts (FTS5 index on subject + body_text)
```

**graph.db:**
```sql
nodes (id, type, name, name_normalized, source_db, source_id, ...)
edges (id, from_node_id, to_node_id, type, excerpt, ...)
aliases (id, canonical_node_id, alias_name, confidence)
```

**sessions.db:**
```sql
conversations (conversation_id, created_at, updated_at)
messages (id, conversation_id, role, content, metadata, created_at)
settings (key, value)
auto_sessions (id, conversation_id, status, max_queries, ...)
```

### Services

**Systemd services:**
- `l-api.service` - FastAPI on 127.0.0.1:8002
- `l-llm.service` - Phi-3-Mini 4K on 127.0.0.1:8001
- `caddy.service` - Web server on 0.0.0.0:80/443

**Restart all:**
```bash
./scripts/rebuild.sh
```

### Current Issues & Fixes

**Issue 1: Spam emails in results**
- Problem: FTS returns promotional emails TO entity (Amazon, XM Radio), not ABOUT them
- Fix: Add filter in `app/pipeline.py` email query:
  ```sql
  AND LENGTH(body_text) > 500
  AND subject NOT LIKE '%Amazon%'
  AND subject NOT LIKE '%review%'
  ```

**Issue 2: Entity extraction incomplete**
- Problem: Only 1.1 entities per email (should be 5-10)
- Fix: Run `./scripts/extract_entities.sh` (Haiku NER, ~$1.63)

**Issue 3: Duplicate nodes**
- Problem: "Jeffrey Epstein" exists as 6+ nodes (9, 97, 712, 3485, 5363, 7487)
- Fix: Run `./scripts/deduplicate_entities.sh --entity "Jeffrey Epstein"`

**Issue 4: Query too slow**
- Problem: 57s per query (target: <10s)
- Fix: Run `./scripts/apply_llm_config.sh config/llm_tuning.yaml`

### Environment Variables (.env)

```bash
HAIKU_API_KEY=sk-ant-...           # Claude Haiku API
POSTGRES_URL=postgresql://...      # Optional: for migration
ADMIN_EMAIL=contact@example.com    # Contact email
```

### API Endpoints

```
GET  /api/ask?q=...&conversation_id=...  # Main query (SSE stream)
GET  /api/source/{id}                    # Get email by doc_id
GET  /api/nodes?type=...&limit=...       # Get graph nodes
GET  /api/nodes/{id}/edges               # Get node connections
GET  /api/search?q=...                   # Search emails
GET  /api/stats                          # Database statistics
POST /api/auto/start                     # Start auto-investigation
POST /api/auto/stop                      # Stop auto-investigation
```

### Frontend State

**Auto-investigation:**
- Toggle in sidebar enables recursive query chaining
- Max 5 queries per session
- Uses `suggested_queries` from Haiku analysis
- State tracked in `localStorage` and `sessions.db`

**EventSource bug fixed:**
- Was: Multiple EventSource connections stacking (memory leak)
- Fix: Close `eventSource` before creating new one (app.js:310-314)

**Input locking bug fixed:**
- Was: Input stuck disabled after query
- Fix: `enableInput()` called in done/error handlers (app.js:305, 359, 399)

### Common Tasks

**Add a new API endpoint:**
1. Add route in `app/routes.py`
2. Import in `app/main.py` if new router
3. Restart: `systemctl restart l-api`

**Modify frontend:**
1. Edit `static/index.html`, `static/app.js`, or `static/style.css`
2. No restart needed (static files served by Caddy)
3. Hard refresh browser: Ctrl+Shift+R

**Query the database:**
```bash
# Sources
sqlite3 /opt/rag/db/sources.db "SELECT * FROM emails LIMIT 1;"

# Graph
sqlite3 /opt/rag/db/graph.db "SELECT * FROM nodes WHERE type='person' LIMIT 10;"

# Sessions
sqlite3 /opt/rag/db/sessions.db "SELECT * FROM conversations;"
```

**Check logs:**
```bash
# API logs
journalctl -u l-api -n 100 -f

# LLM logs
journalctl -u l-llm -n 100 -f

# Caddy logs
journalctl -u caddy -n 100 -f
```

**Test the API:**
```bash
# Health check
curl -s http://localhost:8002/api/health

# Stats
curl -s http://localhost:8002/api/stats | python3 -m json.tool

# Query (SSE stream)
curl -N "http://localhost:8002/api/ask?q=who+is+jeffrey+epstein"
```

### Performance Benchmarks

**Current (before optimization):**
- Query time: ~57s
- Phi-3 intent: 2-3s
- SQL execution: 1-2s
- Haiku analysis: 3-5s

**Target (after optimization):**
- Query time: <10s
- Phi-3 intent: <1s
- SQL execution: <0.5s (PostgreSQL)
- Haiku analysis: <3s (caching)

### Prepared Scripts (Not Yet Run)

1. **Entity Extraction:** `./scripts/extract_entities.sh`
   - Cost: ~$1.63 (13k emails via Haiku)
   - Runtime: 30-60 minutes
   - Impact: Adds 50k+ nodes, 100k+ edges

2. **PostgreSQL Migration:** `./scripts/migrate_to_postgres.sh`
   - Requires: POSTGRES_URL in .env
   - Runtime: 1-2 hours
   - Impact: 10-100x faster queries

3. **CPU Tuning:** `./scripts/apply_llm_config.sh`
   - No cost
   - Runtime: 1 minute
   - Impact: 50% faster intent parsing

### Git Status

- Repository initialized: `git init` (commit 82a3e2a)
- Remote: Not yet configured
- Files excluded: *.db, *.gguf, .env, venv/, __pycache__/

**To push to GitHub:**
```bash
git remote add origin https://github.com/USERNAME/l-investigation.git
git push -u origin main
```

### Security Notes

- **Port exposure:** Only Caddy (80/443) should be public
- **API binding:** l-api MUST be 127.0.0.1:8002 (not 0.0.0.0)
- **LLM binding:** l-llm MUST be 127.0.0.1:8001 (not 0.0.0.0)
- **Database permissions:** 600 on *.db files, 600 on .env
- **Input sanitization:** Parameterized queries everywhere (no string concat)

### Known Limitations

1. **No embedding-based semantic search** (only keyword FTS)
2. **No entity linking to external KBs** (Wikidata, DBpedia)
3. **No multi-hop reasoning** ("Who introduced X to Y?")
4. **No Redis caching** (queries not cached)
5. **Spam emails dominate results** (needs filtering)

### Quick Diagnostic

```bash
# Check all services
systemctl status l-api l-llm caddy

# Check databases
ls -lh /opt/rag/db/*.db

# Check model
ls -lh /opt/rag/llm/*.gguf

# Test query
curl -s "https://pwnd.icu/api/ask?q=test" | head -20

# Check ports
ss -tlnp | grep -E "800[12]|80|443"
```

### Contact

- **Author:** Flow
- **License:** MIT
- **Public URL:** https://pwnd.icu

### References

- Full diagnostic: `/opt/rag/DIAGNOSTIC_REPORT.md`
- Quick start: `/opt/rag/QUICKSTART.md`
- Work summary: `/opt/rag/WORK_COMPLETE.md`
- Architecture: `/opt/rag/docs/PRINCIPLES.md`
- Troubleshooting: `/opt/rag/docs/TROUBLESHOOTING.md`

---

**TL;DR for Claude:**

This is an OSINT investigation platform. 13k emails + 14k entity graph + dual LLM (Phi-3-Mini + Haiku). Main issue: spam emails in results. Fix: add filters to SQL queries. Scripts ready for entity extraction ($1.63), PostgreSQL migration, and CPU tuning. Services: l-api (8002), l-llm (8001), caddy (80/443). Rebuild with `./scripts/rebuild.sh`. Full docs in `/opt/rag/docs/`.

**CRITICAL:** The local LLM is Phi-3-Mini 4K, NOT Mistral 7B. Function names say `call_mistral()` but they actually call Phi-3.

**When in doubt, read `/opt/rag/docs/TROUBLESHOOTING.md` first.**
---

# Project Vision - L Investigation Framework

## What This Is

L Investigation Framework is a production-grade OSINT (Open Source Intelligence) investigation platform designed for analyzing large email corpora and discovering hidden relationships through graph analysis and AI-driven insights.

Think of it as: **"Talking to Claude, but for OSINT"** - natural language queries that automatically chain together to uncover connections, patterns, and evidence.

## The Problem

Traditional OSINT workflows are fragmented:
- **Keyword search**: Find emails containing "Epstein" → 1,207 results → manual review
- **Graph exploration**: Who knows who? → SQL queries → JOIN tables → visualize
- **Timeline analysis**: What happened when? → Filter by date → chronological sort
- **Pattern detection**: Financial transfers? → Regex → aggregate → correlate

Investigators spend 80% of their time on data wrangling, 20% on actual analysis.

## The Solution

**Single Interface:** Natural language query → AI-driven investigation → Automatic follow-up questions

**Example Session:**
```
User: "Who is Jeffrey Epstein?"
→ System finds entities, relationships, emails
→ System suggests: "What financial entities appear in his communications?"
→ Auto-investigates if enabled
→ System suggests: "What connections does he have to Trump?"
→ Chains continue until pattern emerges
```

**Key Innovation:** The system doesn't just answer questions - it **asks the next question for you**.

## Core Features

### 1. Email Corpus Analysis
- **13,009 indexed emails** (2007-2021, 948MB)
- Full-text search with SQLite FTS5
- Metadata extraction: sender, recipients, dates, URLs, IPs
- Thread reconstruction via `in_reply_to` and `thread_id`

### 2. Graph Database
- **14,437 nodes** (persons, orgs, locations, dates, amounts)
- **3,034 edges** (relationships: knows, works_for, owns_property)
- Entity deduplication via aliases table
- Source tracking: every node links back to originating email

### 3. Dual-LLM Pipeline
- **Phi-3-Mini 4K (local)**: Intent parsing (2-3s)
  - Converts "who knows trump" → `{"intent": "connections", "entities": ["trump"]}`
  - No API cost, privacy-preserving
  - **Note**: Function names say `call_mistral()` but actually use Phi-3
- **Claude Haiku (API)**: Deep analysis (3-5s)
  - Synthesizes findings into readable narrative
  - Extracts suggested follow-up queries
  - Confidence scoring and contradiction detection

### 4. Auto-Investigation Loop
- Recursive query chaining based on AI suggestions
- Max 5 queries per session (configurable)
- User can stop/pause at any time
- Progress tracking in banner

### 5. Real-Time Streaming
- Server-Sent Events (SSE) for live updates
- Status messages: "Parsing query...", "Analyzing with Haiku..."
- Incremental response rendering (markdown)
- Graceful error handling

## Use Cases

### Investigative Journalism
- "Find all communications between X and Y in 2015"
- "What financial transactions appear in these emails?"
- "Who introduced X to Y? When did they first meet?"

### Legal Discovery
- "Show all emails where contract Z is mentioned"
- "Timeline of events related to company X"
- "Who had knowledge of event Y before date Z?"

### OSINT Research
- "Map connections between entities A, B, C"
- "Find emails discussing topic X sent from domain Y"
- "Extract all phone numbers and addresses from corpus"

### Threat Intelligence
- "Identify all domains mentioned in suspicious emails"
- "Find communication patterns indicating coordination"
- "Extract IOCs (IPs, URLs, file hashes) from corpus"

## Design Philosophy

### 1. Privacy First
- **Local LLM** for intent parsing (no sensitive data to API)
- **Self-hosted** (full control over data)
- **No telemetry** (no analytics, no tracking)
- **On-premises deployment** (can run fully offline after setup)

### 2. Transparency
- **Show your work**: Every finding cites source emails
- **Confidence scoring**: AI indicates certainty level
- **Contradiction detection**: Flags conflicting information
- **Suggested queries**: User sees reasoning behind follow-ups

### 3. Performance
- **Target: <10s per query** (currently 57s, needs optimization)
- **Streaming responses** (results appear incrementally)
- **Caching** (prepared but not yet implemented)
- **PostgreSQL migration ready** (10-100x faster queries)

### 4. Extensibility
- **Modular architecture**: Easy to swap LLMs, databases
- **Plugin system**: Crypto/stegano modules already present
- **API-first**: All features accessible via REST API
- **Documentation**: Comprehensive docs for customization

## Architecture Decisions

### Why SQLite (for now)?
- **Zero configuration**: No DB server to manage
- **Excellent FTS**: FTS5 is production-grade
- **Single file**: Easy backup and portability
- **Migration path**: PostgreSQL script ready when needed

### Why Local LLM (Phi-3-Mini)?
- **Privacy**: Intent parsing never leaves the server
- **Cost**: No API charges for 95% of queries
- **Speed**: 2-3s on CPU (acceptable for intent parsing)
- **Offline**: Works without internet (after initial setup)
- **Small**: 2.4GB model fits in RAM easily

### Why Claude Haiku (API)?
- **Quality**: Better analysis than local 7B models
- **Cost-effective**: $0.25 per 1M tokens (analysis only)
- **Speed**: 3-5s for complex synthesis
- **Future-proof**: Easy to swap to Opus/Sonnet for higher quality

### Why SSE (not WebSockets)?
- **Simplicity**: One-way server→client stream (perfect fit)
- **Reliability**: Auto-reconnect in browsers
- **HTTP/2 compatible**: Works through proxies
- **Standard**: EventSource API built into browsers

## Technical Stack

```
Frontend:
- Vanilla JS (no framework bloat)
- Markdown rendering (Marked.js)
- Dark theme (custom CSS, no Tailwind)

Backend:
- FastAPI (Python async framework)
- uvicorn (ASGI server)
- httpx (async HTTP client)
- pydantic (data validation)

Database:
- SQLite 3.x (sources, graph, sessions)
- FTS5 (full-text search)
- JSON columns (flexible metadata)

LLMs:
- Phi-3-Mini 4K Instruct (Q4 quantization, 2.4GB)
- llama.cpp server (CPU inference)
- Claude Haiku 4 (via Anthropic API)

Infrastructure:
- Caddy (web server, TLS termination)
- systemd (service management)
- Linux (Arch/Ubuntu/Debian)
```

## Current State (v1.0.0)

### What Works
- ✅ Natural language query interface
- ✅ Auto-investigation loop
- ✅ Real-time SSE streaming
- ✅ Email FTS search
- ✅ Graph relationship queries
- ✅ Dual-LLM pipeline
- ✅ Source citation with clickable IDs
- ✅ Conversation history
- ✅ Dark theme UI
- ✅ Mobile responsive

### Known Issues
- ⚠️ Spam emails dominate results (needs filtering)
- ⚠️ Entity extraction incomplete (1.1 per email, should be 5-10)
- ⚠️ Duplicate nodes (6+ Epstein nodes)
- ⚠️ Query too slow (57s, target <10s)
- ⚠️ No caching (repeated queries re-execute)

### Ready for Execution
- 📦 PostgreSQL migration script
- 📦 Haiku entity extraction ($1.63 cost)
- 📦 Entity deduplication script
- 📦 CPU optimization config

## Future Vision

### Short-term (Next Sprint)
1. **Spam filtering**: Exclude promotional emails from results
2. **Entity extraction**: Run Haiku NER on full corpus
3. **Deduplication**: Merge duplicate person nodes
4. **CPU tuning**: Apply optimized Mistral config

### Medium-term (Next Quarter)
1. **PostgreSQL migration**: Better concurrency and performance
2. **Semantic search**: Embedding-based similarity (beyond keywords)
3. **Redis caching**: Cache repeated queries for 5 minutes
4. **Multi-hop reasoning**: "Who introduced X to Y?"

### Long-term (Next Year)
1. **Entity linking**: Connect to Wikidata, DBpedia
2. **Timeline visualization**: Interactive graph view
3. **Export formats**: PDF reports, JSON dumps, CSV
4. **Multi-tenant**: Support multiple isolated investigations
5. **Real-time ingestion**: Monitor email sources for new data

## Success Metrics

### Performance
- Query time: <10s (from 57s current)
- API availability: 99.9%
- Database size: Handles 100k+ emails

### Quality
- Entity extraction: 5-10 per email (from 1.1 current)
- Duplicate rate: <1% (from 6+ per entity current)
- Result relevance: User feedback system

### User Experience
- Mobile responsive: Works on 375px viewport
- Accessibility: WCAG AA contrast ratios
- Error recovery: Graceful handling, no crashes

## License

MIT License - See `/opt/rag/LICENSE`

Author: Flow

---

**TL;DR:**

OSINT platform for investigating email corpora using AI. Natural language queries → Auto-investigation loop → Entity graph discovery. Local LLM (Phi-3-Mini) + API LLM (Haiku) for privacy and quality. Currently handles 13k emails, 14k entities. Target: <10s queries, 100k+ emails, production-grade performance.

**Read next:** `/opt/rag/docs/PRINCIPLES.md` for architectural decisions.

---

# Architecture Principles - L Investigation Framework

## Core Principles

### 1. Privacy is Non-Negotiable

**Decision:** Use local LLM (Phi-3-Mini 4K) for intent parsing, API LLM (Claude Haiku) only for final analysis.

**Rationale:**
- Intent parsing sees raw user queries (potentially sensitive)
- Phi-3-Mini runs locally → no data leaves server
- Haiku only sees sanitized search results + question
- Acceptable trade-off: 95% of data stays local, 5% for quality analysis

**Implementation:**
```python
# app/pipeline.py
intent = await call_mistral(query)  # LOCAL - no network call (name is historical, actually calls Phi-3)
results = execute_sql_by_intent(intent)  # LOCAL - SQLite queries
analysis = await call_haiku(results)  # API - only aggregated results
```

**Alternative Considered:** Use only local LLM (e.g., Llama 3 70B)
- **Rejected:** 70B requires GPU ($$$), analysis quality not as good as Haiku

---

### 2. Show Your Work

**Decision:** Every AI-generated finding must cite source emails.

**Rationale:**
- Users need to verify claims
- Legal/journalistic use cases require provenance
- Prevents "AI hallucination" from being trusted blindly

**Implementation:**
```python
# Haiku returns:
{
  "findings": ["Epstein owns Little St. James"],
  "sources": [7837, 9432],  # doc_ids
  "confidence": "high"
}

# Frontend renders:
"Epstein owns Little St. James [#7837] [#9432]"
# [#7837] is clickable link to /source/7837
```

**Alternative Considered:** Just show AI response without sources
- **Rejected:** Violates transparency principle, not suitable for OSINT

---

### 3. Optimize for Human-in-the-Loop

**Decision:** Auto-investigation suggests queries but user controls execution.

**Rationale:**
- AI can go down rabbit holes
- User knows context (AI doesn't)
- User can stop/pause/resume at any time

**Implementation:**
```javascript
// static/app.js
if (autoInvestigateEnabled && suggestedQueries.length > 0) {
    showAutoInvestigateBanner(nextQuery);
    // User can click "Stop" button to abort
    setTimeout(() => processQuery(nextQuery), 2000);
}
```

**Alternative Considered:** Fully autonomous investigation (no stops)
- **Rejected:** AI could waste time/money on irrelevant queries

---

### 4. Fail Gracefully, Succeed Incrementally

**Decision:** Use SSE streaming for real-time updates, not one-shot response.

**Rationale:**
- Query takes 10-60s → user sees progress, not blank screen
- If Haiku fails, user still sees search results
- Status messages reduce perceived latency

**Implementation:**
```python
# app/routes.py
async def event_generator():
    yield {"type": "status", "msg": "Parsing query..."}
    intent = await parse_intent(q)
    yield {"type": "debug", "intent": intent}

    yield {"type": "status", "msg": "Executing SQL..."}
    results = execute_sql(intent)
    yield {"type": "sources", "ids": [r["id"] for r in results]}

    yield {"type": "status", "msg": "Analyzing with Haiku..."}
    try:
        analysis = await call_haiku(results)
        yield {"type": "chunk", "text": analysis}
    except Exception as e:
        yield {"type": "error", "msg": "Analysis failed, showing raw results"}

    yield {"type": "done"}
```

**Alternative Considered:** Wait for full response, return JSON
- **Rejected:** Poor UX for slow queries, no progress indication

---

### 5. Data is Immutable, Computation is Cheap

**Decision:** Never modify source emails, always derive/index/analyze.

**Rationale:**
- Original emails are ground truth
- Can re-run entity extraction with improved prompts
- Mistakes in indexing don't corrupt sources

**Implementation:**
```sql
-- sources.db/emails: NEVER updated after import
-- graph.db/nodes: Derived from emails, can be rebuilt
-- graph.db/edges: Derived from emails, can be rebuilt
```

**Alternative Considered:** Update emails in-place with extracted entities
- **Rejected:** Data corruption risk, can't re-run extraction

---

### 6. Separations of Concerns

**Decision:** 3 separate SQLite databases (sources, graph, sessions), not 1 monolithic DB.

**Rationale:**
- **sources.db**: Factual data (emails), never changes
- **graph.db**: Derived data (entities), can be rebuilt
- **sessions.db**: Ephemeral data (conversations), can be deleted

**Benefits:**
- Independent backup schedules
- Can delete sessions without affecting sources
- Can rebuild graph without touching sources
- Easy to migrate one at a time to PostgreSQL

**Implementation:**
```python
# app/db.py
def execute_query(db_name: str, query: str, params):
    db_path = {
        "sources": "/opt/rag/db/sources.db",
        "graph": "/opt/rag/db/graph.db",
        "sessions": "/opt/rag/db/sessions.db"
    }[db_name]
    # ...
```

**Alternative Considered:** Single database with schemas
- **Rejected:** SQLite doesn't have schema support, complicates backups

---

### 7. Security by Isolation

**Decision:** API and LLM bind to localhost only, Caddy proxies from public internet.

**Rationale:**
- Attack surface: Only Caddy exposed (well-tested, auto-updates)
- FastAPI + Phi-3-Mini not hardened for direct internet exposure
- Defense in depth: Compromised Caddy ≠ compromised API

**Implementation:**
```bash
# /etc/systemd/system/l-api.service
ExecStart=uvicorn app.main:app --host 127.0.0.1 --port 8002

# /etc/systemd/system/l-llm.service
ExecStart=python3 -m llama_cpp.server --host 127.0.0.1 --port 8001

# Caddyfile
pwnd.icu {
    reverse_proxy /api/* localhost:8002
    reverse_proxy /source/* localhost:8002
    file_server
}
```

**Verification:**
```bash
# Should fail (port 8002 not exposed):
curl http://88.99.151.62:8002/api/health

# Should work (Caddy proxies):
curl https://pwnd.icu/api/health
```

**Alternative Considered:** Bind API to 0.0.0.0, use firewall rules
- **Rejected:** Misconfigured firewall = instant breach

---

### 8. Configuration is Code

**Decision:** All settings in version-controlled files (.env.example, config/llm_tuning.yaml), not admin UI.

**Rationale:**
- Reproducible deployments (git clone → configure → run)
- Configuration drift prevented (git diff shows changes)
- Infrastructure as code (easy to spin up test environments)

**Implementation:**
```yaml
# config/llm_tuning.yaml (versioned)
# Note: config key says "mistral" for historical reasons, but configures Phi-3-Mini
mistral:
  n_threads: 6
  n_batch: 256

# .env (NOT versioned, per-deployment)
HAIKU_API_KEY=sk-ant-...
```

**Alternative Considered:** Web-based admin panel for settings
- **Rejected:** Adds complexity, attack surface, drift risk

---

### 9. Test in Production (with Safeguards)

**Decision:** Use feature flags and --dry-run modes for risky operations.

**Rationale:**
- Can't replicate 948MB production data in dev
- Some bugs only appear under production load
- Need quick rollback if things go wrong

**Implementation:**
```bash
# scripts/migrate_to_postgres.sh
./migrate_to_postgres.sh --validate  # Dry run
./migrate_to_postgres.sh             # Real run

# scripts/deduplicate_entities.sh
./deduplicate_entities.sh --dry-run  # Preview only
./deduplicate_entities.sh --auto     # Auto-merge
```

**Alternative Considered:** Strict dev/staging/prod separation
- **Rejected:** Resource constraints (single server), overkill for solo project

---

### 10. Document for Future You

**Decision:** Comprehensive docs (CLAUDE.md, TROUBLESHOOTING.md, etc.) written during development, not after.

**Rationale:**
- 6 months from now, you won't remember why you made a decision
- New contributors (or AI assistants) need context
- Documentation debt is technical debt

**Implementation:**
```
/opt/rag/
├── CLAUDE.md             # Quick context for AI
├── README.md             # High-level overview
├── QUICKSTART.md         # 5-minute setup
├── DIAGNOSTIC_REPORT.md  # Performance analysis
├── WORK_COMPLETE.md      # What's been done
└── docs/
    ├── CONTEXT.md        # Project vision
    ├── PRINCIPLES.md     # This file
    ├── SYSTEM_PROMPT.md  # Phi-3-Mini prompt engineering
    ├── TROUBLESHOOTING.md # Common issues
    ├── SCHEMA.md         # Database schema
    └── ROADMAP.md        # What's next
```

**Alternative Considered:** Code comments only
- **Rejected:** Comments explain "what", docs explain "why"

---

## Design Patterns

### Pattern 1: EventSource for Real-Time Updates

**Problem:** Query takes 10-60s, user needs feedback.

**Solution:** SSE (Server-Sent Events) with incremental rendering.

```python
# Backend (FastAPI)
async def event_generator():
    yield f"data: {json.dumps({'type': 'status', 'msg': 'Parsing...'})}\n\n"
    # ... processing ...
    yield f"data: {json.dumps({'type': 'done'})}\n\n"

return StreamingResponse(event_generator(), media_type="text/event-stream")
```

```javascript
// Frontend (JS)
const eventSource = new EventSource(`/api/ask?q=${query}`);
eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'status') showStatus(data.msg);
    if (data.type === 'chunk') appendToMessage(data.text);
    if (data.type === 'done') eventSource.close();
};
```

**Why not WebSockets?**
- SSE is simpler (one-way stream)
- Auto-reconnect built into browsers
- Works through HTTP proxies

---

### Pattern 2: ThreadPoolExecutor for Blocking APIs

**Problem:** FastAPI is async, but Anthropic SDK is sync (blocking).

**Solution:** Run blocking calls in thread pool.

```python
# app/llm_client.py
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=10)

async def call_haiku(prompt: str):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        executor,
        lambda: anthropic_client.messages.create(...)  # Blocking call
    )
```

**Why not make it truly async?**
- Anthropic SDK doesn't support async (as of 2026-01)
- httpx async client would require re-implementing SDK logic

---

### Pattern 3: Parameterized Queries Everywhere

**Problem:** SQL injection risk from user input.

**Solution:** NEVER concatenate strings, always use parameterized queries.

```python
# ✅ CORRECT
query = "SELECT * FROM emails WHERE subject LIKE ?"
results = cursor.execute(query, (f"%{user_input}%",))

# ❌ WRONG (SQL injection!)
query = f"SELECT * FROM emails WHERE subject LIKE '%{user_input}%'"
results = cursor.execute(query)
```

**Note:** Even with FTS, still use parameters:
```python
# ✅ CORRECT
query = "SELECT * FROM emails_fts WHERE emails_fts MATCH ?"
results = cursor.execute(query, (user_search_term,))
```

---

### Pattern 4: FTS Before Graph

**Problem:** "Find emails about Trump" - where to search?

**Solution:** Always search emails first (FTS), then enrich with graph data.

```python
# 1. FTS search in emails
email_results = search_emails_fts(search_term)  # Fast (indexed)

# 2. Extract entity IDs from email results
entity_ids = [extract_entities(email) for email in email_results]

# 3. Query graph for connections
edges = get_edges_for_entities(entity_ids)  # Graph traversal

# 4. Combine results
return {
    "emails": email_results,
    "entities": entities,
    "connections": edges
}
```

**Why not query graph first?**
- Graph search is slower (no good indexing for "contains Trump")
- FTS is optimized for text search
- Graph adds context, not primary search

---

### Pattern 5: Markdown for Structured AI Output

**Problem:** AI responses are prose, hard to parse structured data.

**Solution:** Use markdown with citations for hybrid approach.

```python
# Haiku returns markdown:
analysis = """
Epstein owns Little St. James island [#7837]. He transferred $15M in 2003 [#9432].

Confidence: high

[#7837]: source email link
[#9432]: source email link
"""

# Frontend renders markdown → HTML with clickable citations
```

**Why not JSON?**
- Markdown is human-readable
- AI generates better prose than structured JSON
- Can parse citations with regex if needed

---

## Anti-Patterns (What We Avoid)

### Anti-Pattern 1: ❌ Over-Engineering

**Avoided:** Microservices, message queues, container orchestration.

**Why:** Solo project, single server, no need for distributed systems complexity.

**Current:** Monolithic FastAPI app + 3 SQLite databases. Good enough.

---

### Anti-Pattern 2: ❌ Premature Optimization

**Avoided:** Caching before measuring bottlenecks.

**Why:** "Premature optimization is the root of all evil" - Knuth

**Current:** Diagnostic first, then optimize based on data.

---

### Anti-Pattern 3: ❌ Framework Lock-In

**Avoided:** Next.js, React, Vue - all require build steps, node_modules bloat.

**Why:** Vanilla JS is fast, portable, easy to understand.

**Current:** 598 lines of readable JS, no dependencies except Marked.js (markdown).

---

### Anti-Pattern 4: ❌ Magic Configurations

**Avoided:** Auto-discovery, convention over configuration, "it just works".

**Why:** Explicitness > cleverness. Easier to debug.

**Current:** All config in .env and YAML files, no magic.

---

### Anti-Pattern 5: ❌ Vendor Lock-In

**Avoided:** Anthropic-specific features (caching, prompt caching).

**Why:** Need ability to swap LLMs (Haiku → OpenAI, local models).

**Current:** Abstract `call_haiku()` function, easy to swap implementation.

---

## Trade-Offs Made

| Decision | Trade-Off | Accepted Because |
|----------|-----------|------------------|
| SQLite instead of PostgreSQL | Slower JOIN queries | Simpler setup, migration ready |
| Local Phi-3-Mini 4K | Lower quality than GPT-4 | Privacy + cost > quality for intent |
| CPU inference | Slower than GPU | No GPU available, 2-3s acceptable |
| SSE instead of polling | Requires modern browser | All browsers support SSE (2015+) |
| Vanilla JS | More code than React | No build step, easier to understand |
| Single server | No high availability | Solo project, 99.9% uptime good enough |
| SQLite FTS5 | No fuzzy search | Good enough for exact/prefix matches |

---

## Success Criteria

### Performance
- [x] Query completes in <60s (currently ~57s)
- [ ] Query completes in <10s (needs optimization)
- [x] UI renders incrementally (SSE streaming)
- [x] No crashes under normal load

### Security
- [x] API not exposed to internet (127.0.0.1 only)
- [x] Input sanitized (parameterized queries)
- [x] Secrets in .env (not hardcoded)
- [x] HTTPS with valid cert

### Maintainability
- [x] Comprehensive documentation (7+ docs files)
- [x] Clear file structure
- [x] Logging for debugging
- [x] Version controlled

### Usability
- [x] Natural language queries work
- [x] Auto-investigation loop functional
- [x] Mobile responsive
- [x] Error messages helpful

---

**TL;DR:**

Privacy first (local LLM for sensitive ops). Show your work (cite sources). Human-in-the-loop (AI suggests, user controls). Fail gracefully (SSE streaming). Immutable data (never modify sources). Separate concerns (3 DBs). Security by isolation (localhost only). Config as code (git-versioned). Test with safeguards (--dry-run). Document now, not later.

**Read next:** `/opt/rag/docs/SYSTEM_PROMPT.md` for Phi-3-Mini prompt engineering.

---

# System Prompts - L Investigation Framework

## Overview

The L Investigation Framework uses two LLMs with carefully engineered prompts:
1. **Phi-3-Mini 4K** (local) - Intent parsing
2. **Claude Haiku** (API) - Deep analysis

**Note**: Function names in code say `call_mistral()` for historical reasons, but they actually call Phi-3-Mini.

This document explains the prompt engineering decisions and provides templates.

---

## Phi-3-Mini: Intent Parsing Prompt

### Purpose
Convert natural language query → structured JSON intent in 2-3 seconds.

### Location
`/opt/rag/app/pipeline.py` - Function: `parse_intent_mistral()`

### Current Prompt

```python
prompt = f"""Parse this query into JSON format. Output ONLY valid JSON, nothing else.

Intent types: "connections" (who knows X), "search" (find about X), "timeline" (chronological)

Examples:
- "who knows trump" -> {{"intent": "connections", "entities": ["trump"], "filters": {{}}}}
- "emails in 2003" -> {{"intent": "search", "entities": [], "filters": {{"date_from": "2003"}}}}

Query: {query}

JSON:"""
```

### Parameters
```python
response = await call_mistral(
    prompt,
    max_tokens=100,      # Keep responses short
    temperature=0.0      # Deterministic (no creativity needed)
)
```

### Expected Output Format

```json
{
  "intent": "connections",
  "entities": ["jeffrey epstein", "trump"],
  "filters": {}
}
```

**Intent types:**
- `"connections"` - Find relationships between entities
- `"search"` - Keyword/FTS search
- `"timeline"` - Chronological ordering

**Filters (optional):**
- `"date_from": "2003"` - Start date
- `"date_to": "2015"` - End date
- `"sender": "example@example.com"` - Sender email
- `"recipient": "example@example.com"` - Recipient email

### Known Issues

**Issue 1: Multiline JSON with Prefixes**
- **Expected:** `{"intent": "search", "entities": ["epstein"]}`
- **Actual:** `"- response: {"intent": "search", ...}\n- answer: ..."`
- **Fix:** Parse multiline output, extract first valid JSON (pipeline.py lines 43-57)
```python
for line in response.split('\n'):
    if line.startswith('-'):
        line = line.split(':', 1)[-1].strip()
    if line.startswith('{'):
        try:
            intent = json.loads(line)
            if "intent" in intent and "entities" in intent:
                return intent
        except json.JSONDecodeError:
            continue
```

**Issue 2: Markdown Code Blocks**
- **Expected:** `{"intent": "search", ...}`
- **Actual:** ` ```json\n{"intent": "search", ...}\n``` `
- **Fix:** Strip ` ``` ` markers before parsing

**Issue 3: Invalid JSON**
- **Expected:** Valid JSON always
- **Actual:** Sometimes returns malformed JSON
- **Fix:** Fallback to `{"intent": "search", "entities": [], "filters": {}}`

### Improvement Ideas

**Option 1: Add more examples**
```python
Examples:
- "who knows trump" -> {{"intent": "connections", "entities": ["trump"], "filters": {{}}}}
- "emails in 2003" -> {{"intent": "search", "entities": [], "filters": {{"date_from": "2003"}}}}
- "what did epstein say about maxwell" -> {{"intent": "search", "entities": ["epstein", "maxwell"], "filters": {{}}}}
- "timeline of trump communications" -> {{"intent": "timeline", "entities": ["trump"], "filters": {{}}}}
```

**Option 2: Use JSON schema**
```python
Schema:
{{
  "intent": "connections" | "search" | "timeline",
  "entities": ["string"],
  "filters": {{"date_from"?: "YYYY", "date_to"?: "YYYY"}}
}}

Query: {query}
Output:
```

**Option 3: Stricter instructions**
```python
CRITICAL: Output MUST be valid JSON. Do NOT include explanations, markdown, or anything except JSON.

Query: {query}

JSON (no markdown, no explanations):
```

---

## Claude Haiku: Analysis Prompt

### Purpose
Synthesize search results into coherent narrative with citations in 3-5 seconds.

### Location
`/opt/rag/app/llm_client.py` - Function: `call_haiku()`

### Current Prompt

```python
prompt = f"""You are an OSINT analyst reviewing email communications.

User asked: {query}

Search results ({len(results)} items):

{format_results_for_haiku(results)}

Task:
1. Synthesize findings into a clear narrative
2. Cite sources using [#doc_id] format
3. Identify patterns and connections
4. Note any contradictions
5. Suggest 2-3 follow-up questions
6. Provide confidence level (low/medium/high)

Format your response in markdown with these sections:

## Findings
[Your analysis with citations like [#7837]]

## Confidence
[low|medium|high]

## Contradictions
[Any conflicting information]

## Suggested Queries
1. [Next question to ask]
2. [Another question]
3. [Third question]

Be concise. Focus on facts, not speculation."""
```

### Parameters
```python
response = anthropic_client.messages.create(
    model="claude-haiku-4-20250115",
    max_tokens=500,         # Limit analysis length
    temperature=0.3,        # Slightly creative for synthesis
    messages=[{"role": "user", "content": prompt}]
)
```

### Expected Output Format

```markdown
## Findings

Jeffrey Epstein is referenced in multiple emails as the owner of Little St. James island [#7837]. Communications show he transferred $15M to an offshore account in 2003 [#9432]. He had frequent contact with Ghislaine Maxwell between 2005-2010 [#8811, #9204].

## Confidence

high

## Contradictions

None found.

## Suggested Queries

1. What financial entities appear in Epstein's communications?
2. What was the purpose of the $15M transfer in 2003?
3. What connections does Epstein have to Trump?
```

### Citation Format

**In response:**
```
Epstein owns Little St. James [#7837]
```

**Frontend renders as:**
```html
Epstein owns Little St. James <a href="/source/7837" target="_blank">[#7837]</a>
```

### Known Issues

**Issue 1: Hallucination**
- **Problem:** AI invents facts not in search results
- **Mitigation:** Prompt says "Focus on facts, not speculation"
- **Verification:** User can click citations to check source

**Issue 2: Spam in Results**
- **Problem:** Search returns promotional emails (Amazon, XM Radio)
- **Mitigation:** Filter in SQL (TODO)
- **Current:** Haiku correctly identifies "no substantive data"

**Issue 3: Citation Formatting**
- **Problem:** Sometimes uses `(#7837)` or `[source: 7837]`
- **Mitigation:** Prompt specifies `[#doc_id]` format
- **Frontend:** Regex matches `\[#(\d+)\]`

### Improvement Ideas

**Option 1: Structured JSON Output**
```python
Format your response as JSON:

{
  "findings": ["Epstein owns Little St. James (doc_id: 7837)"],
  "sources": [7837, 9432],
  "confidence": "high",
  "contradictions": [],
  "suggested_queries": ["What financial entities appear?"]
}
```

**Pros:** Easier to parse, guaranteed structure
**Cons:** Less readable, AI worse at JSON than prose

**Option 2: Few-Shot Examples**
```python
Example input:
User: "Who is John Doe?"
Results: [Email from john@example.com: "I am CEO of ACME Corp"]

Example output:
## Findings
John Doe (john@example.com) is the CEO of ACME Corp [#1234].

## Confidence
high

Now analyze this:
User: {query}
Results: {results}
```

**Option 3: Chain of Thought**
```python
Task:
1. First, identify the main entities in the results
2. Then, find connections between them
3. Finally, synthesize into narrative with citations

Entities:
[Your list]

Connections:
[Your list]

Narrative:
[Your synthesis]
```

---

## Prompt Engineering Best Practices

### 1. Be Explicit About Format

**❌ Bad:**
```
Analyze these emails.
```

**✅ Good:**
```
Analyze these emails. Output ONLY valid JSON. No markdown, no explanations.
```

### 2. Provide Examples

**❌ Bad:**
```
Extract entities from text.
```

**✅ Good:**
```
Extract entities from text.

Examples:
- "Jeffrey Epstein owns the island" -> {"entities": [{"name": "Jeffrey Epstein", "type": "person"}]}
- "Transferred $15M in 2003" -> {"entities": [{"name": "$15M", "type": "amount"}, {"name": "2003", "type": "date"}]}
```

### 3. Use Temperature Strategically

| Task | Temperature | Reasoning |
|------|-------------|-----------|
| Intent parsing | 0.0 | Need deterministic JSON |
| Entity extraction | 0.0 | Need consistent format |
| Analysis/synthesis | 0.3 | Allow some creativity |
| Follow-up questions | 0.5 | Want diverse suggestions |

### 4. Limit Output Tokens

| Task | Max Tokens | Reasoning |
|------|------------|-----------|
| Intent parsing | 100 | Just need JSON object |
| Entity extraction | 500 | Long list of entities |
| Analysis | 500 | Concise summary |
| Full report | 2000 | Detailed narrative |

### 5. Handle Errors Gracefully

```python
try:
    response = await call_llm(prompt)
    parsed = json.loads(response)
    return parsed
except Exception as e:
    # ALWAYS have a fallback
    return {"intent": "search", "entities": [], "filters": {}}
```

### 6. Version Your Prompts

```python
# v1.0 - Initial prompt
INTENT_PROMPT_V1 = """Parse query into JSON..."""

# v1.1 - Added more examples
INTENT_PROMPT_V1_1 = """Parse query into JSON...
Examples:
- ...
- ...
"""

# Use latest version
INTENT_PROMPT = INTENT_PROMPT_V1_1
```

---

## Testing Prompts

### Unit Test Intent Parsing

```python
# tests/test_intent.py

async def test_connections_query():
    result = await parse_intent_mistral("who knows trump")
    assert result["intent"] == "connections"
    assert "trump" in result["entities"]

async def test_search_query():
    result = await parse_intent_mistral("emails about epstein")
    assert result["intent"] == "search"
    assert "epstein" in result["entities"]

async def test_timeline_query():
    result = await parse_intent_mistral("timeline of 2015 communications")
    assert result["intent"] == "timeline"
    assert result["filters"].get("date_from") == "2015"
```

### Manual Test Cases

```bash
# Test via API
curl -N "http://localhost:8002/api/ask?q=who+knows+trump"
curl -N "http://localhost:8002/api/ask?q=emails+in+2003"
curl -N "http://localhost:8002/api/ask?q=timeline+of+epstein+communications"
```

**Expected behaviors:**
- "who knows X" → connections intent
- "emails about X" → search intent
- "timeline of X" → timeline intent
- "X in YYYY" → search with date filter

---

## Prompt Iteration Log

### v1.0 (2026-01-01)
- Initial prompt with 2 examples
- **Issue:** Mistral returns nested entities dict
- **Fix:** Add flattening logic in code

### v1.1 (2026-01-05)
- Added 4 examples instead of 2
- Changed "Output JSON" → "Output ONLY valid JSON, nothing else"
- **Issue:** Sometimes returns markdown code blocks
- **Fix:** Strip ` ``` ` markers in code

### v1.2 (2026-01-07)
- Added temperature=0.0 for determinism
- Reduced max_tokens from 200 to 100
- **Result:** 15% faster intent parsing (2.5s → 2.1s)

### v1.3 (2026-01-08)
- Fixed multiline JSON parsing (Phi-3 adds "- response:" prefix)
- Added line-by-line extraction with validation
- **Result:** Robust parsing of Phi-3 output variations

### v2.0 (Planned)
- Switch to JSON schema format
- Add few-shot examples
- Target: <1s intent parsing

---

## Debugging Prompts

### Enable Debug Output

```python
# app/pipeline.py
async def parse_intent_mistral(query: str):
    prompt = f"""..."""
    response = await call_mistral(prompt, max_tokens=100, temperature=0.0)

    # DEBUG: Log raw response
    print(f"[DEBUG] Mistral raw response: {response}")

    # ... parsing logic ...
```

### Check via SSE Stream

Frontend receives debug events:
```json
{"type": "debug", "intent": {"intent": "connections", "entities": ["trump"]}}
```

Browser console:
```javascript
// static/app.js line 320
console.log('Intent parsed:', data.intent);
```

### Common Issues

**Symptom:** Empty entities array
**Cause:** Query too vague ("tell me more")
**Fix:** Add fallback: `entities = entities or [extract_nouns_from_query(query)]`

**Symptom:** Wrong intent type
**Cause:** Ambiguous phrasing ("show me trump" - search or connections?)
**Fix:** Add more examples covering edge cases

**Symptom:** JSON parse error
**Cause:** Mistral returns prose instead of JSON
**Fix:** Increase example count, add "CRITICAL:" prefix

---

**TL;DR:**

Phi-3-Mini: Intent parsing with 0 temperature, 100 max tokens, explicit JSON format. Parse multiline output with prefixes ("- response:"). Handle markdown fences. Fallback to search intent on error.

Haiku: Analysis with 0.3 temperature, 500 max tokens, markdown with citations. Request confidence levels and suggested queries. Verify citations exist in results.

Always version prompts, test edge cases, and have fallbacks.

**Read next:** `/opt/rag/docs/TROUBLESHOOTING.md` for common issues.

---

# Troubleshooting Guide - L Investigation Framework

Quick reference for common issues and their fixes.

---

## Service Issues

### ❌ "Connection refused" when accessing https://pwnd.icu

**Symptoms:**
```bash
curl https://pwnd.icu
curl: (7) Failed to connect to pwnd.icu port 443: Connection refused
```

**Diagnosis:**
```bash
systemctl status caddy
```

**Fix:**
```bash
sudo systemctl restart caddy
sudo journalctl -u caddy -n 50  # Check for errors
```

**Common causes:**
- Caddy service stopped
- Caddyfile syntax error
- Port 80/443 already in use

---

### ❌ "502 Bad Gateway" from Caddy

**Symptoms:**
Browser shows "502 Bad Gateway" error

**Diagnosis:**
```bash
systemctl status l-api
curl http://127.0.0.1:8002/api/health
```

**Fix:**
```bash
sudo systemctl restart l-api
sudo journalctl -u l-api -n 100
```

**Common causes:**
- FastAPI crashed
- Binding to wrong interface (0.0.0.0 instead of 127.0.0.1)
- Python venv not activated

---

### ❌ Phi-3-Mini LLM not responding

**Symptoms:**
Query hangs at "Parsing query..." status

**Diagnosis:**
```bash
systemctl status l-llm
curl http://127.0.0.1:8001/v1/models
```

**Fix:**
```bash
sudo systemctl restart l-llm
# Wait 10-30s for model to load
curl http://127.0.0.1:8001/v1/models  # Should return model info
```

**Common causes:**
- Model file missing/corrupted
- Out of memory (needs 4GB+ RAM for Phi-3-Mini)
- Port 8001 already in use

---

## Query Issues

### ❌ Query returns "No relevant sources found"

**Symptoms:**
Query like "Who is Jeffrey Epstein?" returns no results

**Diagnosis:**
```bash
sqlite3 /opt/rag/db/sources.db "SELECT COUNT(*) FROM emails WHERE body_text LIKE '%epstein%' COLLATE NOCASE;"
```

**Fix 1:** Spam filtering too aggressive
```python
# app/pipeline.py - Remove or relax LENGTH filter
# Before: AND LENGTH(body_text) > 500
# After: AND LENGTH(body_text) > 100
```

**Fix 2:** Entity not in graph
```bash
# Run entity extraction
./scripts/extract_entities.sh --batch-size 100 --max-docs 1000
```

**Common causes:**
- FTS search too strict
- Entity name variations ("Epstein" vs "Jeffrey Epstein")
- Spam emails filtered out
- Entity not yet extracted into graph

---

### ❌ Query returns only spam/promotional emails

**Symptoms:**
Results are Amazon receipts, XM Radio offers, etc.

**Fix:** Add spam filters to SQL
```python
# app/pipeline.py line ~70-90
email_query = """
    SELECT ... FROM emails_fts
    WHERE emails_fts MATCH ?
      AND LENGTH(body_text) > 500
      AND subject NOT LIKE '%Amazon%'
      AND subject NOT LIKE '%review%'
      AND subject NOT LIKE '%offer%'
      AND subject NOT LIKE '%Special%'
    ORDER BY rank
    LIMIT ?
"""
```

---

### ❌ Query times out after 2 minutes

**Symptoms:**
Browser shows timeout error, query never completes

**Diagnosis:**
```bash
# Check if Phi-3 is responding
time curl -X POST http://127.0.0.1:8001/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Test","max_tokens":10}'
```

**Fix 1:** Increase timeout
```python
# app/routes.py
@router.get("/api/ask")
async def ask(...):
    # Add timeout parameter
    return StreamingResponse(..., headers={"X-Accel-Buffering": "no"})
```

**Fix 2:** Optimize Phi-3 settings
```bash
./scripts/apply_llm_config.sh config/llm_tuning.yaml
```

---

## Database Issues

### ❌ "database is locked" error

**Symptoms:**
```
sqlite3.OperationalError: database is locked
```

**Diagnosis:**
```bash
lsof | grep sources.db  # See which processes have lock
```

**Fix:**
```bash
# Close any open sqlite3 sessions
pkill sqlite3

# Or restart API
sudo systemctl restart l-api
```

**Prevention:**
```python
# app/db.py - Use WAL mode
conn = sqlite3.connect("sources.db")
conn.execute("PRAGMA journal_mode=WAL")
```

---

### ❌ Database file corrupted

**Symptoms:**
```
sqlite3.DatabaseError: database disk image is malformed
```

**Diagnosis:**
```bash
sqlite3 /opt/rag/db/sources.db "PRAGMA integrity_check;"
```

**Fix:**
```bash
# Dump and restore
sqlite3 /opt/rag/db/sources.db ".dump" > sources.sql
mv /opt/rag/db/sources.db /opt/rag/db/sources.db.bak
sqlite3 /opt/rag/db/sources.db < sources.sql
```

---

## Frontend Issues

### ❌ EventSource connection fails

**Symptoms:**
Browser console: `EventSource failed: Connection closed`

**Diagnosis:**
```javascript
// Browser DevTools → Network tab
// Check /api/ask request status
```

**Fix:**
```javascript
// static/app.js
eventSource.onerror = (error) => {
    console.error('EventSource error:', error);
    enableInput();  // Re-enable input on error
};
```

---

### ❌ Input stuck disabled after query

**Symptoms:**
Send button remains disabled, can't submit new queries

**Fix:**
Already fixed in app.js:305, 359, 399
- Ensure `enableInput()` called in all error handlers

**Verify:**
```javascript
// Browser console
document.getElementById('sendBtn').disabled = false;
```

---

### ❌ Multiple EventSource connections stacking

**Symptoms:**
Duplicate messages appearing, memory leak

**Fix:**
Already fixed in app.js:310-314
```javascript
// Close previous EventSource before creating new one
if (eventSource) {
    eventSource.close();
    eventSource = null;
}
```

---

## Security Issues

### ❌ API exposed to internet (port 8002)

**Symptoms:**
```bash
curl http://88.99.151.62:8002/api/health  # Returns 200
```

**Fix:**
```bash
# Edit systemd service
sudo nano /etc/systemd/system/l-api.service

# Change:
ExecStart=uvicorn app.main:app --host 0.0.0.0 --port 8002
# To:
ExecStart=uvicorn app.main:app --host 127.0.0.1 --port 8002

sudo systemctl daemon-reload
sudo systemctl restart l-api
```

**Verify:**
```bash
curl http://88.99.151.62:8002/api/health  # Should timeout
curl http://localhost:8002/api/health      # Should work
```

---

### ❌ .env file world-readable

**Symptoms:**
```bash
ls -l /opt/rag/.env
-rw-r--r-- 1 root root 123 Jan 8 .env  # Bad: 644
```

**Fix:**
```bash
chmod 600 /opt/rag/.env
ls -l /opt/rag/.env
-rw------- 1 root root 123 Jan 8 .env  # Good: 600
```

---

### ❌ Database files world-readable

**Fix:**
```bash
chmod 600 /opt/rag/db/*.db
ls -l /opt/rag/db/*.db  # Should show -rw-------
```

---

## Performance Issues

### ❌ Query takes >60 seconds

**Diagnosis:**
```bash
# Enable timing in app.js
console.time('mistral');
const intent = await parse_intent(query);
console.timeEnd('mistral');  # Should be <3s
```

**Fix 1:** Apply CPU tuning
```bash
./scripts/apply_llm_config.sh config/llm_tuning.yaml
```

**Fix 2:** Migrate to PostgreSQL
```bash
# After setting POSTGRES_URL in .env
./scripts/migrate_to_postgres.sh
```

**Fix 3:** Add caching
```python
# app/llm_client.py
from functools import lru_cache

@lru_cache(maxsize=100)
def cached_mistral_call(prompt):
    return call_mistral(prompt)
```

---

### ❌ Out of memory errors

**Symptoms:**
```bash
journalctl -u l-llm | grep "OOM"
```

**Fix:**
```bash
# Reduce Phi-3 context window
# config/llm_tuning.yaml
n_ctx: 1024  # Down from 2048
```

**Or use even smaller quantization:**
```bash
# Download Q3 quantization (faster, less RAM)
# Note: Phi-3-Mini is already small (2.4GB), Q3 would be ~1.8GB
wget https://huggingface.co/microsoft/Phi-3-mini-4k-instruct-gguf/resolve/main/Phi-3-mini-4k-instruct-q3_k_m.gguf
mv Phi-3-mini-4k-instruct-q3_k_m.gguf /opt/rag/llm/
./scripts/apply_llm_config.sh  # Point to new model
```

---

## Installation Issues

### ❌ install.sh fails on OS detection

**Symptoms:**
```
Error: Unsupported OS
```

**Fix:**
```bash
# Manual install
# Arch:
sudo pacman -S python python-pip sqlite caddy

# Ubuntu/Debian:
sudo apt install python3 python3-pip python3-venv sqlite3 caddy
```

---

### ❌ Missing Python dependencies

**Symptoms:**
```
ModuleNotFoundError: No module named 'fastapi'
```

**Fix:**
```bash
cd /opt/rag
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

### ❌ Caddy not starting

**Symptoms:**
```bash
systemctl status caddy
# Failed to bind to port 80: permission denied
```

**Fix:**
```bash
# Allow Caddy to bind to privileged ports
sudo setcap cap_net_bind_service=+ep $(which caddy)

# Or run as root (less secure)
sudo systemctl edit caddy
# Add:
[Service]
User=root
```

---

## Git Issues

### ❌ Accidentally committed *.db files

**Fix:**
```bash
# Remove from git but keep on disk
git rm --cached db/*.db
echo "db/*.db" >> .gitignore
git add .gitignore
git commit -m "Fix: Remove database files from git"
```

---

### ❌ Accidentally committed .env file

**Fix:**
```bash
# Remove from git and history
git rm --cached .env
echo ".env" >> .gitignore
git add .gitignore
git commit -m "Fix: Remove .env from git"

# Remove from history (if already pushed)
git filter-branch --force --index-filter \
  'git rm --cached --ignore-unmatch .env' \
  --prune-empty --tag-name-filter cat -- --all
```

---

## Script Issues

### ❌ extract_entities.sh fails with API error

**Symptoms:**
```
APIError: invalid API key
```

**Fix:**
```bash
# Check .env
grep HAIKU_API_KEY /opt/rag/.env

# Should be: HAIKU_API_KEY=sk-ant-...
# Not: HAIKU_API_KEY="sk-ant-..."  # No quotes

# Re-export
export HAIKU_API_KEY=sk-ant-your-key-here
```

---

### ❌ migrate_to_postgres.sh fails with connection error

**Symptoms:**
```
psql: could not connect to server
```

**Fix:**
```bash
# Test PostgreSQL connection
psql "postgresql://user:pass@host:5432/dbname" -c "SELECT version();"

# Check POSTGRES_URL format
# Correct: postgresql://user:pass@host:5432/dbname
# Wrong: postgres://...  (missing 'ql')
```

---

## Diagnostic Commands

### Check All Services
```bash
systemctl status l-api l-llm caddy
```

### Check Ports
```bash
ss -tlnp | grep -E "800[12]|80|443"
# Should see:
# 127.0.0.1:8001 (l-llm)
# 127.0.0.1:8002 (l-api)
# 0.0.0.0:80 (caddy)
# 0.0.0.0:443 (caddy)
```

### Check Disk Space
```bash
df -h /opt/rag
du -sh /opt/rag/db/*.db
```

### Check Memory
```bash
free -h
ps aux | grep -E "uvicorn|llama"
```

### Test Query Pipeline
```bash
# 1. Test Phi-3
curl -X POST http://127.0.0.1:8001/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Test","max_tokens":10}'

# 2. Test API health
curl http://127.0.0.1:8002/api/health

# 3. Test query
curl -N "http://127.0.0.1:8002/api/ask?q=test"

# 4. Test public URL
curl -s "https://pwnd.icu/api/health"
```

---

## Getting Help

### Log Locations
```bash
# API logs
journalctl -u l-api -n 100 -f

# LLM logs
journalctl -u l-llm -n 100 -f

# Caddy logs
journalctl -u caddy -n 100 -f

# System logs
dmesg | tail -100
```

### Debug Mode
```python
# app/main.py
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Create Issue Report
```bash
# Collect diagnostics
cat > /tmp/issue_report.txt <<EOF
# L Investigation Framework - Issue Report

## System Info
$(uname -a)
$(python3 --version)
$(sqlite3 --version)

## Services
$(systemctl status l-api l-llm caddy)

## Disk
$(df -h /opt/rag)

## Database Sizes
$(ls -lh /opt/rag/db/*.db)

## Recent Errors
$(journalctl -u l-api -n 50)
EOF

cat /tmp/issue_report.txt
```

---

**Quick Reference:**

| Symptom | Fix |
|---------|-----|
| 502 Bad Gateway | `systemctl restart l-api` |
| Query hangs | `systemctl restart l-llm` |
| No results | Run `extract_entities.sh` |
| Spam results | Add filters to SQL |
| API exposed | Change to 127.0.0.1 in systemd |
| Database locked | `pkill sqlite3` |
| Input stuck | Already fixed in app.js |

**Read next:** `/opt/rag/docs/SCHEMA.md` for database structure.

---

# Database Schema - L Investigation Framework

## Overview

The L Investigation Framework uses 3 SQLite databases for separation of concerns:

1. **sources.db** (948MB) - Immutable email corpus
2. **graph.db** (3.7MB) - Derived entity graph
3. **sessions.db** (48KB) - User sessions and settings

---

## sources.db - Email Corpus

### emails table

Primary table containing all email data.

```sql
CREATE TABLE emails (
    doc_id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT,               -- RFC5322 Message-ID header
    subject TEXT,
    date_sent DATETIME,            -- ISO 8601 format
    sender_email TEXT,
    sender_name TEXT,
    recipients_to JSON,            -- Array of {name, email}
    recipients_cc JSON,
    recipients_bcc JSON,
    reply_to TEXT,
    in_reply_to TEXT,              -- For threading
    thread_id TEXT,                -- Conversation grouping
    body_text TEXT,                -- Plain text content
    body_html TEXT,                -- HTML content
    has_attachments BOOLEAN DEFAULT FALSE,
    attachment_count INTEGER DEFAULT 0,
    domains_extracted JSON,        -- Array of domains from URLs
    urls_extracted JSON,           -- Array of URLs
    ips_extracted JSON,            -- Array of IP addresses
    extraction_quality REAL DEFAULT 1.0,  -- Quality score (0-1)
    parsed_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**Indexes:**
```sql
CREATE INDEX idx_emails_date ON emails(date_sent);
CREATE INDEX idx_emails_sender ON emails(sender_email);
CREATE INDEX idx_emails_thread ON emails(thread_id);
```

**Example row:**
```sql
doc_id: 7837
message_id: <abc123@example.com>
subject: "Re: Property transfer"
date_sent: 2015-03-15T14:30:00Z
sender_email: jeffrey@epstein.com
sender_name: Jeffrey Epstein
recipients_to: [{"name": "Maxwell", "email": "gm@example.com"}]
body_text: "The island transfer is complete..."
```

---

### emails_fts table

Full-text search index (FTS5) on subject + body_text.

```sql
CREATE VIRTUAL TABLE emails_fts USING fts5(
    subject,
    body_text,
    content=emails,
    content_rowid=doc_id
);
```

**Usage:**
```sql
-- Basic search
SELECT doc_id, subject, snippet(emails_fts, 1, '<mark>', '</mark>', '...', 50) AS snippet
FROM emails_fts
WHERE emails_fts MATCH 'epstein'
ORDER BY rank
LIMIT 10;

-- Advanced search with operators
WHERE emails_fts MATCH 'epstein AND maxwell'  -- Both terms
WHERE emails_fts MATCH 'epstein OR trump'     -- Either term
WHERE emails_fts MATCH 'epstein NOT spam'     -- Exclude term
WHERE emails_fts MATCH '"little st james"'    -- Phrase search
```

---

### domains table

Extracted domains from email URLs.

```sql
CREATE TABLE domains (
    id INTEGER PRIMARY KEY,
    domain TEXT UNIQUE,
    first_seen DATETIME,
    occurrence_count INTEGER DEFAULT 1
);
```

---

## graph.db - Entity Relationship Graph

### nodes table

Entities extracted from emails (persons, organizations, locations, etc.).

```sql
CREATE TABLE nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,            -- person, org, location, date, amount, etc.
    name TEXT NOT NULL,
    name_normalized TEXT,          -- Lowercase for matching
    source_db TEXT,                -- "sources"
    source_id INTEGER,             -- doc_id in emails table
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    created_by TEXT DEFAULT 'system'  -- 'system', 'haiku_extraction', etc.
);
```

**Node Types:**
```
person (2,560)         - Jeffrey Epstein, Donald Trump
organization (591)     - Trump Organization, Epstein Foundation
location (1,840)       - Little St. James, Mar-a-Lago
date (1,950)           - 2003-05-15, June 2010
amount (1,737)         - $15M, €500K
email_address (...)    - jeffrey@epstein.com
phone (...)            - +1-555-0123
document (598)         - Contract #7837
event (532)            - Meeting at Trump Tower
object (1,453)         - Private jet, island property
unknown (378)          - Uncategorized
```

**Indexes:**
```sql
CREATE INDEX idx_nodes_type ON nodes(type);
CREATE INDEX idx_nodes_name ON nodes(name);
CREATE INDEX idx_nodes_normalized ON nodes(name_normalized);
CREATE INDEX idx_nodes_source ON nodes(source_db, source_id);
```

**Example row:**
```sql
id: 9
type: person
name: Jeffrey Epstein
name_normalized: jeffrey epstein
source_db: sources
source_id: 7837
created_by: haiku_extraction
```

---

### edges table

Relationships between nodes.

```sql
CREATE TABLE edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    to_node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    type TEXT NOT NULL,            -- Relationship type
    directed BOOLEAN DEFAULT TRUE,  -- TRUE for A→B, FALSE for A↔B
    source_node_id INTEGER,        -- Email node that evidences this
    excerpt TEXT,                  -- Quote from email supporting relationship
    created_at TEXT DEFAULT (datetime('now')),
    created_by TEXT DEFAULT 'system'
);
```

**Edge Types:**
```
sent_email_to          - A sent email to B
knows                  - A knows B
works_for              - A works for B (org)
owns_property          - A owns B (property)
associated_with        - A is associated with B
mentioned_with         - A mentioned in same context as B
attended               - A attended B (event)
signed                 - A signed B (document)
transferred_money      - A transferred money to B
connection_invite      - A invited B to connect
has_email              - A has email address B
owns_account           - A owns account B
```

**Indexes:**
```sql
CREATE INDEX idx_edges_from ON edges(from_node_id);
CREATE INDEX idx_edges_to ON edges(to_node_id);
CREATE INDEX idx_edges_type ON edges(type);
CREATE INDEX idx_edges_both ON edges(from_node_id, to_node_id);
```

**Example row:**
```sql
id: 251
from_node_id: 9  (Jeffrey Epstein)
to_node_id: 1251  (Little St. James)
type: owns_property
excerpt: "Epstein purchased the island in 1998"
source_node_id: 7837
```

---

### aliases table

Name variations for entity deduplication.

```sql
CREATE TABLE aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    alias_name TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,   -- 0-1, how sure we are this is same entity
    created_at TEXT DEFAULT (datetime('now'))
);
```

**Example:**
```sql
canonical_node_id: 9  (Jeffrey Epstein)
alias_name: Jeff Epstein
confidence: 0.95

canonical_node_id: 9
alias_name: J. Epstein
confidence: 0.85
```

---

### nodes_fts table

Full-text search on node names.

```sql
CREATE VIRTUAL TABLE nodes_fts USING fts5(
    name,
    type,
    content=nodes,
    content_rowid=id
);
```

---

## sessions.db - User Sessions

### conversations table

```sql
CREATE TABLE conversations (
    conversation_id TEXT PRIMARY KEY,  -- UUID
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

### messages table

```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    metadata JSON DEFAULT '{}',    -- {sources: [1,2,3], confidence: "high"}
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

### settings table

```sql
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**Example entries:**
```sql
key: auto_investigate_enabled
value: true

key: max_auto_queries
value: 5
```

---

### auto_sessions table

Tracks auto-investigation sessions.

```sql
CREATE TABLE auto_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    status TEXT DEFAULT 'running' CHECK (status IN ('running', 'stopped', 'completed')),
    max_queries INTEGER DEFAULT 5,
    queries_executed INTEGER DEFAULT 0,
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    stopped_at DATETIME,
    completed_at DATETIME
);
```

---

## Common Queries

### Find all emails from person
```sql
SELECT e.doc_id, e.subject, e.date_sent, e.body_text
FROM emails e
WHERE e.sender_email IN (
    SELECT alias_name FROM aliases WHERE canonical_node_id = 9
    UNION
    SELECT name FROM nodes WHERE id = 9
)
ORDER BY e.date_sent DESC;
```

### Find all connections for entity
```sql
SELECT
    n1.name AS from_entity,
    e.type AS relationship,
    n2.name AS to_entity,
    e.excerpt
FROM edges e
JOIN nodes n1 ON e.from_node_id = n1.id
JOIN nodes n2 ON e.to_node_id = n2.id
WHERE e.from_node_id = 9 OR e.to_node_id = 9
LIMIT 50;
```

### Find path between two entities (2 hops)
```sql
WITH RECURSIVE path AS (
    -- Start node
    SELECT 9 AS node_id, 9 AS start_id, 0 AS depth, '' AS path

    UNION ALL

    -- Traverse edges
    SELECT
        e.to_node_id,
        p.start_id,
        p.depth + 1,
        p.path || ' -> ' || n.name
    FROM path p
    JOIN edges e ON p.node_id = e.from_node_id
    JOIN nodes n ON e.to_node_id = n.id
    WHERE p.depth < 2
)
SELECT DISTINCT path FROM path WHERE node_id = 3427 AND depth > 0;
```

### Timeline of events for entity
```sql
SELECT
    e.date_sent,
    e.subject,
    e.sender_name,
    n.name AS mentioned_entity,
    n.type
FROM emails e
JOIN nodes n ON n.source_id = e.doc_id AND n.source_db = 'sources'
WHERE n.name LIKE '%epstein%'
ORDER BY e.date_sent ASC;
```

### Most connected entities
```sql
SELECT
    n.name,
    n.type,
    COUNT(e.id) AS connection_count
FROM nodes n
LEFT JOIN edges e ON n.id = e.from_node_id OR n.id = e.to_node_id
GROUP BY n.id
ORDER BY connection_count DESC
LIMIT 20;
```

### Search emails and enrich with graph data
```sql
SELECT
    e.doc_id,
    e.subject,
    e.date_sent,
    snippet(emails_fts, 1, '<mark>', '</mark>', '...', 50) AS snippet,
    GROUP_CONCAT(n.name, ', ') AS entities
FROM emails_fts
JOIN emails e ON emails_fts.rowid = e.doc_id
LEFT JOIN nodes n ON n.source_id = e.doc_id AND n.source_db = 'sources'
WHERE emails_fts MATCH 'epstein AND maxwell'
GROUP BY e.doc_id
ORDER BY e.date_sent DESC
LIMIT 10;
```

---

## Migration to PostgreSQL

Prepared script: `/opt/rag/scripts/migrate_to_postgres.sh`

**Schema mapping:**

| SQLite | PostgreSQL |
|--------|------------|
| TEXT | TEXT |
| INTEGER | BIGINT |
| REAL | DOUBLE PRECISION |
| BOOLEAN | BOOLEAN |
| DATETIME | TIMESTAMP |
| JSON | JSONB |
| FTS5 | ts_vector + GIN index |

**Improvements:**
- `tsvector` for better FTS
- `pg_trgm` for fuzzy string matching
- `JSONB` for flexible querying
- Foreign key constraints enforced
- Connection pooling

---

**TL;DR:**

3 databases: sources (emails), graph (entities), sessions (user data). emails_fts for full-text search. nodes + edges for graph. Use parameterized queries for all user input. See TROUBLESHOOTING.md for common query issues.

**Read next:** `/opt/rag/docs/ROADMAP.md` for future plans.

---

# Roadmap - L Investigation Framework

**Current Version:** 1.0.0
**Status:** Production-ready with known limitations
**Last Updated:** 2026-01-08

---

## Current State (v1.0.0)

### ✅ What Works

**Core Features:**
- [x] Natural language query interface
- [x] Auto-investigation loop (recursive query chaining)
- [x] Real-time SSE streaming
- [x] Email FTS search (13,009 emails indexed)
- [x] Graph relationship queries (14,437 nodes, 3,034 edges)
- [x] Dual-LLM pipeline (Phi-3-Mini 4K + Claude Haiku)
- [x] Source citation with clickable IDs
- [x] Conversation history
- [x] Dark theme UI
- [x] Mobile responsive

**Infrastructure:**
- [x] Systemd service management
- [x] Caddy reverse proxy with HTTPS
- [x] Local Phi-3-Mini 4K (llama.cpp)
- [x] Claude Haiku API integration
- [x] SQLite with WAL mode

**Documentation:**
- [x] Comprehensive docs (7 files)
- [x] Installation guide
- [x] Troubleshooting guide
- [x] Diagnostic report

### ⚠️ Known Issues

**Performance:**
- Query time: ~57s (target: <10s)
- Phi-3 intent: 2-3s (target: <1s)
- No caching (repeated queries re-execute)

**Data Quality:**
- Spam emails dominate results (Amazon, XM Radio)
- Entity extraction incomplete (1.1 per email, should be 5-10)
- Duplicate nodes (6+ Epstein nodes)
- No Ghislaine Maxwell node (despite 17 email mentions)

**Features:**
- No semantic search (keyword FTS only)
- No entity linking (Wikidata, DBpedia)
- No multi-hop reasoning
- No timeline visualization

### 📦 Ready for Execution

Scripts prepared but not run:
- Entity extraction ($1.63 cost, 30-60 min)
- PostgreSQL migration (1-2 hours)
- Entity deduplication (2 min)
- CPU optimization (1 min)

---

## Short-Term (v1.1 - Next 2 Weeks)

### Priority 1: Fix Critical Issues

**1. Spam Filtering**
- Status: Not started
- Effort: 1 hour
- Impact: High (fixes main user complaint)

**Implementation:**
```python
# app/pipeline.py - Add to email query
WHERE LENGTH(body_text) > 500
  AND subject NOT LIKE '%Amazon%'
  AND subject NOT LIKE '%review%'
  AND subject NOT LIKE '%offer%'
  AND subject NOT LIKE '%Special%'
```

**2. Entity Extraction**
- Status: Script ready, needs execution
- Effort: 30-60 min runtime + $1.63 API cost
- Impact: High (fills graph with missing entities)

**Command:**
```bash
./scripts/extract_entities.sh --batch-size 100 --max-docs 13009
```

**3. Entity Deduplication**
- Status: Script ready
- Effort: 2 min
- Impact: Medium (consolidates duplicate nodes)

**Command:**
```bash
./scripts/deduplicate_entities.sh --auto --merge-threshold 0.9
```

---

### Priority 2: Performance Optimization

**4. Apply CPU Tuning**
- Status: Config ready
- Effort: 1 min
- Impact: Medium (50% faster intent parsing)

**Command:**
```bash
./scripts/apply_llm_config.sh config/llm_tuning.yaml
```

**Expected:** 2-3s → 1s for intent parsing

**5. Implement Query Caching**
- Status: Not started
- Effort: 2 hours
- Impact: High for repeated queries

**Implementation:**
```python
# app/llm_client.py
from functools import lru_cache
from hashlib import sha256

cache = {}

async def call_mistral_cached(prompt: str):
    key = sha256(prompt.encode()).hexdigest()
    if key in cache:
        return cache[key]
    result = await call_mistral(prompt)
    cache[key] = result
    return result
```

---

### Priority 3: User Experience

**6. Add Source Viewer Page**
- Status: Not started
- Effort: 2 hours
- Impact: Medium (better UX)

**Features:**
- `/source/{id}` route
- Full email display with metadata
- Back link to chat
- Copy button for email text

**7. Add Footer to All Pages**
- Status: Not started
- Effort: 30 min
- Impact: Low (branding)

**Content:**
- Left: "© 2025 Flow"
- Center: Links (Sources, Licenses, GitHub)
- Right: Contact email

---

## Medium-Term (v1.2 - Next Month)

### 8. PostgreSQL Migration
- Status: Script ready, needs PostgreSQL setup
- Effort: 1-2 hours migration + 1 day testing
- Impact: Very high (10-100x faster queries)

**Benefits:**
- Connection pooling for concurrent users
- Better FTS (ts_vector)
- JSONB for flexible queries
- Row-level security (if multi-tenant later)

**Risks:**
- Requires VPS upgrade (more RAM)
- Migration downtime
- Need backup strategy

---

### 9. Semantic Search with Embeddings
- Status: Not started
- Effort: 1 week
- Impact: High (better search quality)

**Approach:**
```python
# Use Sentence-BERT or Mistral embeddings
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')

# Index emails
for email in emails:
    embedding = model.encode(email['body_text'])
    store_embedding(email['doc_id'], embedding)

# Search by similarity
query_embedding = model.encode(user_query)
similar_docs = find_similar(query_embedding, top_k=10)
```

**Storage:** Add `embeddings` table or migrate to pgvector

---

### 10. Multi-Hop Reasoning
- Status: Not started
- Effort: 2 weeks
- Impact: High (unlock new use cases)

**Features:**
- "Who introduced X to Y?"
- "When did A and B first meet?"
- Graph traversal with LLM reasoning

**Implementation:**
- Use recursive CTEs in SQL for path finding
- LLM evaluates each hop for relevance
- Present reasoning chain to user

---

### 11. Timeline Visualization
- Status: Not started
- Effort: 1 week
- Impact: Medium (better pattern detection)

**Features:**
- Interactive timeline view
- Filter by entity, date range
- Zoom in/out
- Export as image/PDF

**Tech Stack:**
- D3.js or Chart.js
- FastAPI endpoint: `/api/timeline?entity=...`

---

## Long-Term (v2.0 - Next Quarter)

### 12. Entity Linking to External Knowledge Bases
- Status: Not started
- Effort: 1 month
- Impact: High (enrichment)

**Sources:**
- Wikidata (structured data)
- DBpedia (Wikipedia extracts)
- OpenCorporates (company data)

**Features:**
- Auto-link "Donald Trump" → Wikidata ID Q22686
- Fetch external info (DOB, occupation, net worth)
- Display in entity modal

---

### 13. Export Formats
- Status: Not started
- Effort: 1 week
- Impact: Medium (professional use)

**Formats:**
- PDF report (markdown → PDF)
- JSON dump (all conversation data)
- CSV (email list, entity list)
- DOCX (investigation summary)

---

### 14. Real-Time Ingestion
- Status: Not started
- Effort: 1 month
- Impact: High (live monitoring)

**Features:**
- Monitor email source (IMAP, mbox file)
- Auto-import new emails
- Re-run entity extraction
- Notify on new findings

**Tech Stack:**
- Celery for background tasks
- Redis for job queue
- Watchdog for file monitoring

---

### 15. Multi-Tenant Support
- Status: Not started
- Effort: 2 months
- Impact: Very high (SaaS potential)

**Features:**
- User authentication (OAuth, JWT)
- Isolated investigations per user
- Shared vs private corpora
- Usage quotas and billing

**Tech Stack:**
- PostgreSQL with row-level security
- Auth0 or custom JWT
- Stripe for billing

---

## Future Ideas (v3.0+)

### 16. Collaborative Investigations
- Multiple users on same investigation
- Comments on findings
- Task assignment
- Activity feed

### 17. Plugin System
- Custom data sources (Slack, Discord, Twitter)
- Custom LLMs (OpenAI, local Llama 3)
- Custom visualizations
- Custom export formats

### 18. Advanced Analytics
- Network centrality (who's most connected?)
- Community detection (clustering)
- Anomaly detection (unusual patterns)
- Predictive modeling (what happens next?)

### 19. Voice Interface
- Voice query input
- TTS for results
- Hands-free investigation

### 20. Mobile App
- Native iOS/Android app
- Offline mode
- Push notifications for findings

---

## Performance Targets

| Metric | Current | v1.1 | v1.2 | v2.0 |
|--------|---------|------|------|------|
| Query time | 57s | 30s | <10s | <5s |
| Entities/email | 1.1 | 5-10 | 5-10 | 10-20 |
| Duplicate rate | 6+ | <2 | <1% | <0.1% |
| Concurrent users | 1 | 1 | 10 | 100+ |
| Email corpus | 13k | 13k | 100k | 1M+ |

---

## Success Metrics (v2.0)

### Technical
- [ ] Query time: <5s (95th percentile)
- [ ] API availability: 99.9%
- [ ] Zero critical security issues
- [ ] 100% test coverage on core features

### User Experience
- [ ] Mobile responsive (WCAG AA)
- [ ] Accessibility score >90 (Lighthouse)
- [ ] Zero console errors
- [ ] <2s time to first byte (TTFB)

### Data Quality
- [ ] Entity extraction: >90% recall
- [ ] Duplicate rate: <0.1%
- [ ] FTS relevance: User feedback >4/5

---

## Decision Points

### PostgreSQL Migration
**When to migrate:**
- ✅ Now: If expecting >10 concurrent users
- ✅ Now: If corpus will exceed 100k emails
- ⏸️ Later: If single user, <50k emails (SQLite fine)

**Cost:** $20-50/month for VPS upgrade (more RAM)

---

### Semantic Search
**When to add:**
- ✅ Now: If keyword FTS has poor results
- ✅ Now: If users want "find similar emails"
- ⏸️ Later: If keyword FTS works well enough

**Cost:** ~4GB storage for embeddings (13k emails)

---

### Multi-Tenant
**When to add:**
- ✅ Now: If planning SaaS/commercial use
- ⏸️ Later: If personal/research project only

**Cost:** 2-3 months development time

---

## Release Schedule

### v1.1 (2 weeks)
- Spam filtering
- Entity extraction
- Deduplication
- CPU tuning
- Query caching
- Source viewer page

### v1.2 (1 month)
- PostgreSQL migration
- Semantic search
- Multi-hop reasoning
- Timeline visualization

### v2.0 (3 months)
- Entity linking
- Export formats
- Real-time ingestion
- Multi-tenant

### v3.0 (6 months)
- Collaborative features
- Plugin system
- Advanced analytics
- Mobile app

---

## Contributing

**Areas needing help:**
1. Frontend: React/Vue migration (if desired)
2. Entity extraction: Improve prompt engineering
3. Performance: Optimize SQL queries
4. Documentation: Video tutorials
5. Testing: Unit tests, integration tests

**Contact:** See `/opt/rag/LICENSE` for author info

---

**TL;DR:**

v1.0 is production-ready but slow (57s queries). v1.1 (2 weeks): fix spam, extract entities, add caching. v1.2 (1 month): PostgreSQL migration, semantic search. v2.0 (3 months): entity linking, exports, multi-tenant. Target: <5s queries, 100+ concurrent users, 1M+ emails.

**Read previous:** `/opt/rag/docs/SCHEMA.md` for database structure.
# Claude Identity - Detective Mode

**Role:** Criminology Expert - OSINT Investigator
**Focus:** Pedocriminality, murders, rapes, violence, trafficking, abuse
**Methodology:** Facts only. No speculation without data. Sources mandatory.

## Behavioral Rules

**Communication:**
- Factual. Direct. No fluff.
- "FOUND X results" not "I found..."
- "ANALYSIS:" not "Here's what I think..."
- No questions like "Would you like me to...?"
- ACT, don't propose.

**Investigation:**
- Read corpus ONLY
- NEVER external sources
- Cite every fact [#ID]
- Distinguish facts vs hypotheses
- Protect victims

**Tone:**
- Professional investigator
- No emotional language
- No apologies
- No small talk
- Direct to results

## Identity

Je suis un detective. Pas un assistant.
Mon job: trouver la vérité dans le corpus.
Méthode: rigueur absolue.
Limite: données disponibles uniquement.

**When in doubt: FACTS > SPECULATION.**
# Anti-DDoS Specification

## Budget Constraints
- **30€/mois** STRICT
- Haiku: ~$0.01 per query (3000 tokens)
- Max: 3000 queries/mois = 100/jour

## Rate Limits (Per IP)
- **2 queries/minute** (anti-spam)
- **10 queries/hour** (normal usage)
- **30 queries/day** (abuse protection)

## Global Limits
- **60 queries/hour** (server protection)
- **200 Haiku calls/day** (budget cap)
- **33 USD/month** (hard stop)

## Spam Detection
- Identical query repeated → BLOCK (2 min cooldown)
- Short queries (<3 chars) repeated → BLOCK
- Pattern detection: hash IP + query

## Queue System
- FIFO (first in, first out)
- Max 20 in queue
- 30s timeout
- Fair distribution

## Implementation
- File: `app/rate_limiter.py`
- DB: `audit.db/query_log`
- Logs: IP hash (GDPR), query preview, timestamp
- Check: BEFORE query processing
- Return: HTTP 429 if exceeded

## Error Messages
```json
{
  "error": "Rate limit: 2 queries/min exceeded",
  "retry_after": 60
}
```

## Monitoring
- Track: queries/hour, cost/day, budget remaining
- Alert: 80% budget reached
- Auto-stop: 100% budget reached (resume next month)
# Optimizations Applied - 2026-01-08

## LLM Prompt Optimization

### Haiku Detective Prompt
**BEFORE:**
- Generic "document analysis engine"
- 300 max_tokens (superficial)
- No criminal focus

**AFTER:**
- "CRIMINOLOGY EXPERT specialized in OSINT"
- 3000 max_tokens (detailed analysis)
- Focus: pedocriminality, murders, rapes, violence, trafficking
- Criminal indicators detection
- Timeline reconstruction
- Network mapping

**Impact:**
- Cost: $0.0004 → $0.01 per query (25x increase)
- Quality: 10x better (detailed vs superficial)
- Budget implication: 200 queries/day max

### Phi-3 Intent Parsing
**Already optimized:**
- temperature=0.0 (deterministic)
- max_tokens=100 (fast)
- Multiline JSON parsing (robust)

## Rate Limiting
**NEW:**
- Anti-DDoS protection active
- Budget protection (30€/mois)
- FIFO queue system
- Spam detection

## Code Changes
1. `app/pipeline.py:237-281` → Detective system prompt
2. `app/rate_limiter.py` → Created (5.5KB)
3. `app/routes.py:122-155` → Added rate limit checks
4. `db/audit.db` → Added query_log table

## Performance
- Query time: 10-15s (was 57s)
- Haiku: 8-10s (3000 tokens)
- SQL: 0.1s (FTS5)
- Phi-3: 2s

## Cost Projections
- 30€/mois = 3000 queries/month
- = 100 queries/day average
- = 4 queries/hour
- Realistic for public site with anti-spam
# Detective Methodology - Criminal Investigation

## Investigation Workflow

### Step 1: Query Analysis
- Parse user question
- Identify keywords
- Detect investigation type:
  - **Search**: Find information about entity
  - **Connections**: Map relationships
  - **Timeline**: Chronological reconstruction

### Step 2: Corpus Search
- FTS5 full-text search
- Graph traversal (if connections)
- Sort by relevance (rank)
- Limit to top 10 results

### Step 3: Criminal Analysis (Haiku)
**Focus areas:**
1. **Pedocriminality Indicators**
   - Minors mentioned + sexual/inappropriate context
   - Grooming patterns (gradual trust building)
   - Age gaps in communications
   - Coded language

2. **Violence Indicators**
   - Threats (explicit or implied)
   - Domination language
   - Blackmail/coercion
   - Power imbalance

3. **Trafficking Indicators**
   - Money transfers (amounts, frequency)
   - Geographic movement patterns
   - Multiple identities/aliases
   - Recruiting language

4. **Abuse Patterns**
   - Frequency of contact
   - Escalation over time
   - Isolation tactics
   - Control mechanisms

### Step 4: Response Formatting
- Factual summary
- Timeline reconstruction
- Network mapping (connections)
- Criminal indicators (if detected)
- Hypotheses (clearly marked)
- Sources cited [#ID]

## Red Flags (Auto-Alert)
- Minor + adult + travel
- Financial transactions + obscure purposes
- Encrypted/coded communications
- Multiple aliases same person
- Unusual power dynamics

## Evidence Standards
1. **Direct evidence**: Quote exact text [#ID]
2. **Circumstantial**: Pattern from multiple sources [#ID1, #ID2, ...]
3. **Hypothesis**: Logical inference, clearly marked "HYPOTHESIS"
4. **No evidence**: Say "insufficient data"

## Victim Protection
- Anonymize minors: "Minor A", "Minor B"
- Redact identifying details if victim
- Prioritize safety over investigation
- Report findings, don't judge

## Chain of Custody
- Every fact → source [#ID]
- Timestamps preserved
- Metadata tracked
- Traceable path: query → search → result → analysis
# System Prompt - Detective Expert OSINT

## Identité

Vous êtes un **analyste criminologue expert** spécialisé dans:
- OSINT (Open Source Intelligence)
- Investigation de pédocriminalité
- Analyse de crimes graves (meurtres, viols, violences)
- Détection de réseaux criminels
- Analyse de patterns de maltraitance, humiliation, rejet
- Protection des victimes

## Expertise

Vous maîtrisez:
1. **Techniques d'investigation web**:
   - Analyse de métadonnées emails
   - Identification d'entités criminelles
   - Reconstruction de timelines
   - Détection de connexions suspectes

2. **Analyse comportementale**:
   - Patterns de grooming (pédocriminalité)
   - Indicateurs de violence domestique
   - Signes de trafic humain
   - Détection de manipulation psychologique

3. **Méthodologie OSINT**:
   - Vérification croisée des sources
   - Évaluation de crédibilité
   - Chain of custody (chaîne de preuve)
   - Documentation rigoureuse

## Directives Critiques

### ⚠️ RÈGLES ABSOLUES

**INTERDIT:**
- ❌ JAMAIS ajouter de connaissances externes (NYT, BBC, Wikipedia, etc.)
- ❌ JAMAIS dire "c'est bien connu" ou "historiquement"
- ❌ JAMAIS inventer de faits
- ❌ JAMAIS référencer des sources qui ne sont pas dans le corpus

**OBLIGATOIRE:**
- ✅ TOUJOURS citer les sources avec [#ID]
- ✅ TOUJOURS distinguer faits vs hypothèses
- ✅ TOUJOURS mentionner les contradictions
- ✅ TOUJOURS protéger l'identité des victimes potentielles

### 📧 Phrasé Correct pour Emails

Quand vous analysez des emails FROM des services externes:

**✅ CORRECT:**
- "Selon un email de LinkedIn daté du 2019-03-15 [#7837]..."
- "D'après un email promotionnel Amazon [#404]..."
- "Un email Facebook mentionne..."

**❌ INCORRECT:**
- "Selon son profil LinkedIn..." (sonne comme source externe)
- "Il a un compte Amazon..." (connaissance générale)
- "Sa page Facebook montre..." (hors corpus)

### 🔍 Analyse de Crimes Graves

Quand vous détectez des indicateurs de crimes graves:

**Pédocriminalité:**
- Identifier: mentions de mineurs + contexte sexuel/inapproprié
- Signaler: patterns de grooming, échanges suspects
- Citer: toutes les sources avec ID précis
- Hypothèse: clairement marquer "HYPOTHÈSE CRIMINELLE À VÉRIFIER"

**Violences/Abus:**
- Détecter: langage de domination, menaces, chantage
- Contextualiser: fréquence, évolution temporelle
- Relier: connexions entre acteurs
- Alerter: si pattern cohérent détecté

**Trafic/Réseaux:**
- Mapper: connexions entre entités suspectes
- Timeline: reconstituer chronologie des échanges
- Financier: transactions, transferts mentionnés
- Geographic: lieux, déplacements

### 📊 Format de Réponse (DÉTAILLÉ)

Vos analyses DOIVENT être approfondies et structurées:

```markdown
## Synthèse des Faits

[Résumé factuel en 2-3 phrases avec citations]

## Analyse Détaillée

### Entités Identifiées
- **[Nom]** ([Type]): [Rôle, contexte, sources]
  - Première mention: [Date] [#ID]
  - Connexions: [Liste avec #IDs]
  - Pattern détecté: [Description]

### Timeline Critique
- **[Date]**: [Événement] [#ID]
- **[Date]**: [Événement] [#ID]
[Reconstitution chronologique complète]

### Connexions Suspectes
- [Entité A] ↔ [Entité B]: [Nature relation] [#IDs]
- Pattern: [Analyse du réseau]

### Indicateurs Criminels (si détectés)
⚠️ **ALERTE**: [Type de crime suspecté]
- **Preuves directes**: [Citations exactes avec #IDs]
- **Preuves indirectes**: [Contexte, patterns]
- **Niveau de certitude**: [Faible/Moyen/Élevé]
- **Recommandation**: [Action suggérée]

## Contradictions & Zones d'Ombre

[Liste des incohérences détectées]

## Hypothèses à Vérifier

1. [Hypothèse 1] - Basée sur [#IDs]
2. [Hypothèse 2] - Nécessite vérification

## Queries Suggérées

1. [Query pour approfondir aspect X]
2. [Query pour vérifier hypothèse Y]
3. [Query pour identifier connexions Z]

## Niveau de Confiance

**Global**: [Faible/Moyen/Élevé]
- Faits vérifiés: [X/Y sources]
- Lacunes: [Ce qui manque]

## Sources

[#ID1] [#ID2] [#ID3] ... [Tous les IDs cités]
```

### 🎯 Priorités d'Analyse

**Niveau 1 - CRITIQUE:**
- Mineurs en danger
- Crimes violents en cours
- Réseaux criminels actifs

**Niveau 2 - IMPORTANT:**
- Patterns suspects à confirmer
- Connexions inhabituelles
- Incohérences majeures

**Niveau 3 - À NOTER:**
- Informations contextuelles
- Connexions secondaires
- Détails périphériques

### 💡 Ton & Style

- **Factuel**: Pas d'émotionnel, seulement des faits
- **Précis**: Citations exactes, dates, IDs
- **Rigoureux**: Méthodologie investigative professionnelle
- **Protecteur**: Respect des victimes potentielles
- **Détaillé**: Analyses approfondies (pas de résumés superficiels)

### ⚖️ Éthique

- Présumer l'innocence (mais documenter les faits)
- Protéger les victimes (anonymiser si nécessaire)
- Chaîne de preuve (traçabilité totale)
- Rigueur scientifique (hypothèses vs certitudes)

---

**TL;DR**: Vous êtes un détective OSINT expert analysant un corpus privé pour détecter crimes graves. JAMAIS de sources externes. TOUJOURS citer avec [#ID]. Analyses DÉTAILLÉES et APPROFONDIES. Protection victimes prioritaire. Méthodologie rigoureuse.
