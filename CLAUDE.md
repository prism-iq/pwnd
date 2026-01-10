# CLAUDE.md - Project Context File

> **Read this file first at the start of every session.**
> **Last Updated:** 2026-01-10

---

## TL;DR

PWND.ICU is an OSINT investigation platform for Epstein documents:
- **33,598 documents** (FOIA, depositions, flight logs, trial exhibits)
- **PostgreSQL** with 5 databases (sources, graph, scores, audit, sessions)
- **RAG Chat** at `/chat.html` - natural language Q&A with source citations
- **Search** at `/index.html` - full-text search with auto-explore
- **LLM**: Phi-3-Mini local (2.4GB) + Claude Haiku fallback
- **Live**: https://pwnd.icu

---

## Quick Commands

```bash
# Start/Stop
./start.sh && ./status.sh
./stop.sh

# Development
source venv/bin/activate
uvicorn app.main:app --reload --port 8002

# Test endpoints
curl http://localhost:8002/api/health
curl http://localhost:8002/api/stats
curl -X POST http://localhost:8002/api/chat/send -H 'Content-Type: application/json' -d '{"message":"Who is Maxwell?"}'

# Git
git status && git log --oneline -5
git add -A && git commit -m "message" && git push origin main

# Database
psql -U lframework -d lframework -h localhost
```

---

## File Structure

```
/opt/rag/
├── app/                    # FastAPI backend
│   ├── main.py            # Entry point, middleware
│   ├── routes.py          # /api/search, /api/ask, /api/investigate
│   ├── routes_chat.py     # /api/chat/* (RAG conversations)
│   ├── routes_auth.py     # /api/auth/* (JWT auth)
│   ├── db.py              # PostgreSQL connection pool
│   ├── search.py          # Full-text search (search_all)
│   ├── llm_client.py      # call_local(), call_haiku()
│   ├── prosecution.py     # Evidence tracking (PROSECUTION_TARGETS)
│   ├── pipeline.py        # Document processing
│   ├── workers.py         # Background workers
│   └── config.py          # Environment config
│
├── static/                 # Frontend
│   ├── index.html         # Search interface
│   ├── chat.html          # RAG chat interface
│   ├── investigation.html # Graph visualization
│   └── source.html        # Document viewer
│
├── scripts/                # Utilities
├── db/                     # Schema files
├── docs/                   # Documentation
├── mind/                   # AI reasoning logs
├── external_data/          # Raw data sources
├── llm/                    # Phi-3 model (not in git)
│
├── install.sh             # One-command setup
├── start.sh / stop.sh     # Service control
├── Caddyfile              # Reverse proxy
├── .env                   # Config (not in git)
├── PROJECT.md             # Detailed project index
└── CLAUDE.md              # THIS FILE
```

---

## API Endpoints

### Chat (RAG)
```
POST /api/chat/send              # Message → AI response + sources
POST /api/chat/stream            # SSE streaming response
GET  /api/chat/conversations     # List conversations
GET  /api/chat/conversations/:id # Get conversation
DELETE /api/chat/conversations/:id # Delete conversation
```

### Search & Analysis
```
GET /api/health                  # Health check
GET /api/stats                   # Document statistics
GET /api/search?q=               # Full-text search
GET /api/ask?q=                  # RAG Q&A (SSE)
GET /api/investigate?entity=     # Entity investigation
GET /api/document/:id            # Get document
```

### Auth
```
POST /api/auth/register          # Create account
POST /api/auth/login             # Get JWT
GET  /api/auth/me                # Current user
```

---

## Database

### PostgreSQL Databases
1. **sources** - Documents (33,598 rows)
2. **graph** - Entities (82,265 nodes, 4,291 edges)
3. **scores** - Evidence scoring
4. **audit** - Query logs
5. **sessions** - Chat conversations

### Key Tables
```sql
-- sources.documents
documents (id, name, content, type, metadata)

-- sessions.conversations
conversations (id, title, created_at)
messages (id, conversation_id, role, content, sources, created_at)

-- graph.nodes
nodes (id, type, name, properties)
edges (id, from_node_id, to_node_id, type)
```

---

## Architecture

```
Browser → Caddy (443) → FastAPI (8002) → PostgreSQL
                                      → Phi-3 LLM (local)
                                      → Claude Haiku (fallback)
```

### Chat RAG Flow
1. User sends message to `/api/chat/send`
2. `search_context()` queries documents for relevant context
3. `build_context_prompt()` formats context for LLM
4. `generate_response()` calls Phi-3 (or Haiku fallback)
5. Response + sources saved to `messages` table
6. Return response with source citations

---

## Recent Changes

### 2026-01-10
- **Chat System** - RAG-powered conversations (`routes_chat.py`, `chat.html`)
- **README redesign** - Badges, tables, better presentation
- **Bug fix** - Delete conversation endpoint (wrong table name)

### 2026-01-09
- **Prosecution targets** - Updated with deposition/FOIA evidence
- **DOJ OPR Report** - Added findings

### 2026-01-08
- **Deposition analysis** - All high-profile names processed
- **10,523 new documents** - Ingested from FOIA release

---

## Key Files to Know

| File | Purpose | When to Edit |
|------|---------|--------------|
| `app/routes_chat.py` | Chat API | Adding chat features |
| `app/routes.py` | Search/ask API | Adding search features |
| `app/search.py` | Search logic | Modifying search behavior |
| `app/llm_client.py` | LLM calls | Changing prompts/models |
| `app/prosecution.py` | Evidence tracking | Adding targets |
| `static/chat.html` | Chat UI | Frontend changes |
| `static/index.html` | Search UI | Frontend changes |

---

## Common Tasks

### Add new API endpoint
1. Edit `app/routes.py` or create new `app/routes_*.py`
2. Add router in `app/main.py`
3. Restart: `./stop.sh && ./start.sh`

### Modify chat behavior
1. Edit `app/routes_chat.py`
2. Key functions: `search_context()`, `generate_response()`, `SYSTEM_PROMPT`

### Test changes
```bash
curl http://localhost:8002/api/health
curl -X POST http://localhost:8002/api/chat/send -H 'Content-Type: application/json' -d '{"message":"test"}'
```

### Deploy changes
```bash
git add -A && git commit -m "description" && git push origin main
```

---

## Environment (.env)

```bash
DATABASE_URL=postgresql://lframework:xxx@localhost:5432/lframework
LLM_MODEL_PATH=/opt/rag/llm/phi-3-mini-4k-instruct.Q4_K_M.gguf
ANTHROPIC_API_KEY=sk-ant-xxx  # Optional, for Haiku fallback
API_HOST=0.0.0.0
API_PORT=8002
```

---

## Known Issues

1. **Stream endpoint slow** - Generates full response before chunking
2. **Conversation titles** - All say "New Chat" (need title extraction)
3. **Some OCR errors** - Scanned documents have extraction issues

---

## Standing Permissions

**Autorisé sans demander:**
- Améliorer l'interface (static/*.html, static/*.css)
- Corriger des bugs
- Optimiser le code
- Commit et push

**Demander d'abord:**
- Changements de schéma de base de données
- Nouveaux endpoints majeurs
- Modifications de sécurité

---

## Security Reminders

**NEVER commit:**
- API keys, passwords, secrets
- .env files
- Database files (*.db)
- SSH keys

**Always:**
- Use parameterized queries
- Validate user input
- Keep services bound to localhost (except Caddy)

---

## Links

- **Live:** https://pwnd.icu
- **Repo:** https://github.com/prism-iq/pwnd
- **Chat:** https://pwnd.icu/chat.html
- **Search:** https://pwnd.icu/

---

*"Evil must be fought wherever it is found." — The Code*
