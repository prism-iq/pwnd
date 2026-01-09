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

# Authentication
POST /api/auth/register                  # Create account (email + password)
POST /api/auth/login                     # Login, get JWT token
POST /api/auth/logout                    # Invalidate session
GET  /api/auth/me                        # Get current user (requires auth)
GET  /api/auth/verify                    # Check if authenticated
```

### Authentication System

**Password Security:**
- Argon2id hashing (time_cost=2, memory_cost=65536KB)
- Passwords require: 8+ chars, letters, numbers

**Token System:**
- JWT tokens for API access (24h expiry)
- Session tokens stored as SHA256 hash in PostgreSQL
- HTTPOnly + Secure + SameSite=Strict cookies

**Usage:**
```bash
# Register
curl -X POST /api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"SecurePass123"}'

# Login
curl -X POST /api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"SecurePass123"}'
# Returns: {"access_token": "eyJ...", "user": {...}}

# Use token
curl /api/auth/me -H "Authorization: Bearer eyJ..."
```

**Database Tables:**
- `users` - User accounts (email, password_hash, role)
- `user_sessions` - Active sessions (token_hash, expires_at)
- `password_resets` - Password reset tokens

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

## GITHUB & SECURITY

**Repo:** https://github.com/prism-iq/pwnd (LIVE)

### NEVER COMMIT:
- API keys (ANTHROPIC_API_KEY, etc.)
- SSH keys (~/.ssh/*)
- Passwords, tokens, secrets
- .env files
- Database files (*.db)

### Environment Variables
Secrets go in environment, not code:
```bash
export ANTHROPIC_API_KEY="xxx"  # In ~/.bashrc, NEVER in code
```

Code reads from env:
```python
API_KEY = os.getenv("ANTHROPIC_API_KEY")  # No default with real key!
```

### Before Committing
```bash
git diff --staged | grep -iE "(sk-ant|password|secret|token|ssh|BEGIN.*KEY)" && echo "⚠️ SECRET DETECTED" || echo "✓ Clean"
```

### Auto-Commit Protocol
```bash
git add -A && git commit -m "[type]: description" && git push
```
Types: feat, fix, docs, refactor, chore

