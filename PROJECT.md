# PROJECT INDEX - PWND.ICU

> **Last updated:** 2026-01-10
> **Read this file first** to understand the entire project structure.

---

## Quick Stats

| Metric | Value |
|--------|-------|
| Documents indexed | 33,598 |
| Backend code | ~7,254 lines Python |
| Database | PostgreSQL (5 databases) |
| LLM | Phi-3-Mini local + Claude Haiku fallback |
| Live URL | https://pwnd.icu |

---

## Directory Structure

```
/opt/rag/
├── app/                    # FastAPI backend (CORE)
│   ├── main.py            # Entry point, middleware, routers
│   ├── routes.py          # Search/ask/investigate endpoints
│   ├── routes_chat.py     # Chat API (RAG conversations)
│   ├── routes_auth.py     # Authentication endpoints
│   ├── db.py              # PostgreSQL connection pooling
│   ├── search.py          # Full-text search logic
│   ├── llm_client.py      # Phi-3 + Haiku integration
│   ├── pipeline.py        # Document processing pipeline
│   ├── prosecution.py     # Target evidence tracking
│   ├── models.py          # Pydantic models
│   ├── config.py          # Environment config
│   ├── workers.py         # Background job workers
│   ├── job_queue.py       # Async job queue
│   └── auth.py            # JWT authentication
│
├── static/                 # Frontend (HTML/JS/CSS)
│   ├── index.html         # Main search interface
│   ├── chat.html          # RAG chat interface
│   ├── investigation.html # Graph visualization
│   ├── source.html        # Document viewer
│   ├── upload.html        # Document upload
│   └── thoughts.html      # Live analysis thoughts
│
├── scripts/                # Utilities
│   ├── setup-db.sh        # PostgreSQL setup
│   ├── ingest.py          # Document ingestion
│   ├── seed_scores.py     # Evidence scoring
│   └── export-evidence.sh # Evidence packages
│
├── db/                     # Database
│   └── schema_sessions.sql # Chat tables schema
│
├── docs/                   # Documentation
│   ├── SCHEMA.md          # Database schema
│   ├── SECURITY_AUDIT.md  # Security review
│   └── SYSTEM_PROMPT.md   # LLM system prompts
│
├── mind/                   # AI reasoning logs
│   ├── thoughts.md        # Investigation notes
│   ├── errors.md          # Known issues
│   └── methods.md         # Analysis methods
│
├── external_data/          # Raw data sources
│   ├── court_docs/        # Court documents
│   ├── flight_logs/       # Lolita Express logs
│   └── github_repos/      # External datasets
│
├── llm/                    # Local LLM models
│   └── phi-3-mini-4k-instruct.Q4_K_M.gguf
│
├── install.sh             # One-command setup
├── start.sh               # Start services
├── stop.sh                # Stop services
├── Caddyfile              # Reverse proxy config
├── .env                   # Environment variables
└── PROJECT.md             # THIS FILE
```

---

## Core Files Reference

### Backend (app/)

| File | Purpose | Key Functions |
|------|---------|---------------|
| `main.py` | FastAPI app entry | Rate limiting, CORS, routers |
| `routes.py` | Search endpoints | `/api/search`, `/api/ask`, `/api/investigate` |
| `routes_chat.py` | Chat endpoints | `/api/chat/send`, `/api/chat/stream`, `/api/chat/conversations` |
| `db.py` | Database layer | `execute_query()`, `execute_insert()`, connection pooling |
| `search.py` | Search logic | `search_all()`, `SearchResult` model |
| `llm_client.py` | LLM integration | `call_local()`, `call_haiku()` |
| `prosecution.py` | Evidence tracking | `PROSECUTION_TARGETS`, evidence scores |

### Frontend (static/)

| File | Purpose |
|------|---------|
| `index.html` | Search interface with auto-explore |
| `chat.html` | RAG conversation interface |
| `investigation.html` | Entity graph visualization |
| `source.html` | Document viewer with highlights |

---

## API Endpoints

### Search & Analysis
```
GET  /api/health              # Health check
GET  /api/stats               # Document statistics
GET  /api/search?q=           # Full-text search
GET  /api/ask?q=              # RAG Q&A (SSE streaming)
GET  /api/investigate?entity= # Entity investigation
GET  /api/document/{id}       # Get document by ID
```

### Chat (RAG Conversations)
```
POST   /api/chat/send                    # Send message, get response
POST   /api/chat/stream                  # SSE streaming response
GET    /api/chat/conversations           # List conversations
GET    /api/chat/conversations/{id}      # Get conversation
DELETE /api/chat/conversations/{id}      # Delete conversation
```

### Auth
```
POST /api/auth/register    # Create account
POST /api/auth/login       # Get JWT token
GET  /api/auth/me          # Current user
```

---

## Database Schema

### PostgreSQL Databases
1. **sources** - Documents, emails, files
2. **graph** - Entity relationships (nodes, edges)
3. **scores** - Evidence scoring
4. **audit** - Query logs
5. **sessions** - Chat conversations

### Key Tables (sessions db)
```sql
conversations (id, title, created_at)
messages (id, conversation_id, role, content, sources, created_at)
```

### Key Tables (sources db)
```sql
emails (id, subject, sender, recipients, body, date)
documents (id, name, content, type, metadata)
```

---

## Configuration (.env)

```bash
# Database
DATABASE_URL=postgresql://lframework:xxx@localhost:5432/lframework
DB_POOL_SIZE=10

# LLM
LLM_MODEL_PATH=/opt/rag/llm/phi-3-mini-4k-instruct.Q4_K_M.gguf
ANTHROPIC_API_KEY=sk-ant-xxx  # Optional

# Rate limits
HAIKU_DAILY_LIMIT=200
MAX_REQUESTS_PER_DAY=30

# Server
API_HOST=0.0.0.0
API_PORT=8002
```

---

## Recent Changes

<!-- CHANGELOG - Update this section after each significant change -->

### 2026-01-10
- **Chat System** (`routes_chat.py`, `chat.html`) - RAG-powered conversations
- **README redesign** - Badges, tables, better presentation
- **Bug fix** - Delete conversation endpoint (wrong table name)

### 2026-01-09
- **Prosecution targets** - Updated with deposition/FOIA evidence
- **DOJ OPR Report** - Added findings to evidence base

### 2026-01-08
- **Deposition analysis** - All high-profile names processed
- **10,523 new documents** - Ingested from FOIA release

---

## Key Commands

```bash
# Start/stop
./start.sh              # Start all services
./stop.sh               # Stop all services
./status.sh             # Check service status

# Development
source venv/bin/activate
uvicorn app.main:app --reload --port 8002

# Database
psql -U lframework -d lframework -h localhost
./scripts/setup-db.sh   # Reset database

# Ingestion
python scripts/ingest.py /path/to/documents
python external_data/ingest_depositions.py

# Git
git status
git log --oneline -10
```

---

## Architecture Notes

### Request Flow
```
Browser → Caddy (443) → FastAPI (8002) → PostgreSQL
                                      → Phi-3 LLM
                                      → Claude Haiku (fallback)
```

### Chat RAG Flow
```
1. User sends message
2. search_context() queries documents
3. build_context_prompt() formats context
4. generate_response() calls LLM with context
5. Response saved to messages table
6. Return response + sources to client
```

### Search Flow
```
1. Query parsed for terms
2. Full-text search (PostgreSQL FTS)
3. Results scored by relevance
4. Snippets extracted
5. Return SearchResult objects
```

---

## Prosecution Targets

Evidence tracked in `app/prosecution.py`:

| Target | Evidence Score | Key Documents |
|--------|----------------|---------------|
| Epstein | 100% | All documents |
| Maxwell | 95% | Trial exhibits, depositions |
| Prince Andrew | 75% | Virginia Giuffre deposition |
| Bill Clinton | 60% | Flight logs, pilot testimony |
| Alan Dershowitz | 70% | Depositions, emails |
| Les Wexner | 55% | Financial records |

---

## Known Issues (mind/errors.md)

1. Stream endpoint slow (generates full response before chunking)
2. Graph visualization needs optimization for large datasets
3. Some OCR documents have extraction errors

---

## Testing

```bash
# Health check
curl http://localhost:8002/api/health

# Search test
curl "http://localhost:8002/api/search?q=maxwell&limit=5"

# Chat test
curl -X POST http://localhost:8002/api/chat/send \
  -H "Content-Type: application/json" \
  -d '{"message":"Who is Ghislaine Maxwell?"}'

# Full test suite
python -m pytest tests/ -v
```

---

## Contact & Links

- **Live:** https://pwnd.icu
- **Repo:** https://github.com/prism-iq/pwnd
- **Issues:** https://github.com/prism-iq/pwnd/issues

---

*This file should be read at the start of each session for full project context.*
