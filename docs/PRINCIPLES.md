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
