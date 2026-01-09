# Architecture Map - File Communication

## File Structure
```
/opt/rag/
├── app/
│   ├── __init__.py          # Empty init
│   ├── config.py            # Config vars (HAIKU_API_KEY, etc.)
│   ├── db.py                # Database connections (multi-DB)
│   ├── models.py            # Pydantic models
│   ├── search.py            # FTS search functions
│   ├── llm_client.py        # Phi-3 + Haiku API clients
│   ├── pipeline.py          # 4-step LLM flow (DETECTIVE PROMPT)
│   ├── rate_limiter.py      # Anti-DDoS + budget protection
│   ├── cost_tracker.py      # Cost tracking (?)
│   ├── routes.py            # FastAPI routes
│   └── main.py              # App entry point
├── llm/
│   └── backend.py           # Phi-3 llama.cpp server
├── static/
│   ├── index.html
│   ├── app.js
│   └── style.css
├── templates/
│   └── backend.sh
├── scripts/
│   └── rebuild.sh
└── db/
    ├── sources.db
    ├── graph.db
    ├── audit.db
    ├── sessions.db
    └── scores.db
```

## Communication Flow

### HTTP Request Flow
```
User Browser
  ↓ HTTPS
Caddy (:80/:443)
  ↓ reverse proxy
FastAPI (routes.py :8002)
  ↓ calls
rate_limiter.py → check limits
  ↓ if OK
pipeline.py → process_query()
  ↓ calls
llm_client.py → call_mistral() + call_haiku()
  ↓ queries
db.py → execute_query()
  ↓ FTS
sources.db, graph.db
  ↓ returns
pipeline.py → formats response
  ↓ SSE stream
routes.py → StreamingResponse
  ↓
User Browser
```

### Module Dependencies
```
main.py
  → routes.py
      → rate_limiter.py (acquire_slot, release_slot)
      → pipeline.py (process_query, auto_investigate)
      → search.py (search_all, search_emails, search_nodes)
      → db.py (execute_query, execute_insert, execute_update)
      → models.py (Pydantic schemas)

pipeline.py
  → llm_client.py (call_mistral, call_haiku)
  → search.py (search_emails, search_nodes)
  → db.py (execute_query, execute_insert)

llm_client.py
  → config.py (LLM_MISTRAL_URL, LLM_HAIKU_API_KEY)
  → db.py (execute_query, execute_insert for audit)
  → httpx (async HTTP)

db.py
  → sqlite3
  → config.py (DB paths)

rate_limiter.py
  → db.py (execute_query, execute_insert for audit.query_log)
  → asyncio (semaphore for queue)
```

## Current Issues

### CRITICAL: Import Mismatch
**routes.py imports:**
```python
from app.rate_limiter import is_allowed, log_query
```

**rate_limiter.py exports:**
```python
async def acquire_slot()  # NOT is_allowed
def release_slot()
# NO log_query function
```

**FIX NEEDED:**
- Either: Add is_allowed() + log_query() to rate_limiter.py
- Or: Change routes.py to use acquire_slot() + release_slot()

### Recommended: Option 2 (use existing functions)
```python
# routes.py
from app.rate_limiter import acquire_slot, release_slot

@router.get("/api/ask")
async def ask(request: Request, q: str, ...):
    acquired, error, headers = await acquire_slot(request.client.host)
    if not acquired:
        return JSONResponse(status_code=429, content={"error": error})

    try:
        # process query
        pass
    finally:
        release_slot()
```

## Separation of Concerns

### config.py
- Environment variables
- Constants (URLs, limits, paths)
- NO logic

### db.py
- Database connections ONLY
- execute_query, execute_insert, execute_update
- NO business logic

### llm_client.py
- LLM API calls ONLY
- Phi-3 (local) + Haiku (API)
- Cost tracking
- NO prompts (prompts in pipeline.py)

### pipeline.py
- Business logic (4-step flow)
- System prompts (DETECTIVE)
- Query processing
- Response formatting

### rate_limiter.py
- Rate limiting logic ONLY
- Budget protection
- Queue management
- NO query processing

### routes.py
- HTTP endpoints ONLY
- Request validation
- Response formatting (SSE)
- Calls other modules

### search.py
- FTS search functions ONLY
- NO LLM calls

## Design Principles

1. **One Responsibility Per File**
2. **Clear Imports** (no circular dependencies)
3. **Async Where Needed** (HTTP, DB can stay sync)
4. **Separate Config** (environment vs code)
5. **Error Handling** (each module handles its errors)

## Next Steps

1. Fix import mismatch (routes.py ↔ rate_limiter.py)
2. Verify all imports work
3. Test service restart
4. Document any new modules
