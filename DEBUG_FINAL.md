# DEBUG - Final Rebuild

**Date:** 2026-01-08
**Status:** SUCCESS

## Issues Fixed

### 1. Messages Not Persisting
**Problem:** `process_query()` didn't save messages to database
**Solution:** Added `execute_insert()` calls to save user and assistant messages

```python
# Save user message
execute_insert("sessions",
    "INSERT INTO messages (conversation_id, role, content, is_auto) VALUES (%s, %s, %s, %s)",
    (conversation_id, "user", query, 1 if is_auto else 0))

# Save assistant message after response
execute_insert("sessions",
    "INSERT INTO messages (conversation_id, role, content, is_auto) VALUES (%s, %s, %s, %s)",
    (conversation_id, "assistant", final_response, 1 if is_auto else 0))
```

### 2. Frontend Only Handling `chunk` Events
**Problem:** Frontend ignored `status`, `sources`, `done`, `error` events
**Solution:** Rebuilt frontend with proper SSE event handling

```javascript
function handleSSEEvent(data, contentDiv, setFullText) {
    switch (data.type) {
        case 'status': showStatus(data.msg); break;
        case 'chunk': /* update content */ break;
        case 'sources': showSources(data.ids); break;
        case 'error': /* show error */ break;
        case 'done': hideStatus(); break;
    }
}
```

### 3. Auto-Investigate Not Working
**Problem:** Auto mode couldn't find messages (because they weren't saved)
**Solution:**
- Fixed message persistence (issue #1)
- Rewrote `auto_investigate()` to:
  - Generate questions via Mistral
  - Process each query with `is_auto=True`
  - Track progress in `auto_sessions` table
  - Yield proper SSE events

### 4. No Error Handling
**Problem:** Errors silently failed
**Solution:** Added try/catch blocks with `yield {"type": "error", "msg": str(e)}`

## Test Results

### Query Flow
```bash
curl "http://localhost:8002/api/ask?q=epstein&conversation_id=xxx"
# Result: Messages saved, response returned
```

### Auto-Investigate
```bash
curl -X POST /api/auto/start -d '{"conversation_id":"xxx","max_queries":2}'
# Result:
# - 2 auto queries generated
# - Messages saved with is_auto=1
# - auto_complete event sent
```

### Database Verification
```sql
SELECT role, LEFT(content, 40), is_auto FROM messages;
-- user | epstein | 0
-- assistant | ANOTHER RULE... | 0
-- user | What is the relationship... | 1
-- assistant | I couldn't find... | 1
```

## Files Modified

### Backend
- `/opt/rag/app/pipeline.py`
  - `process_query()` - Added message persistence + error handling
  - `auto_investigate()` - Complete rewrite

### Frontend
- `/opt/rag/static/index.html`
  - Complete rebuild with:
    - Proper SSE handling for all event types
    - Status bar with spinner
    - Sources panel
    - Auto-investigate UI
    - Error display

## Known Limitations

1. **Intent Parser Returns Empty Entities**
   - Complex questions like "What is the relationship between..." get parsed as `{"entities": []}`
   - This causes FTS search to use the full query, which may not match
   - Fix: Improve Phi-3 intent parsing prompt or use keyword extraction

2. **Phi-3 Response Quality**
   - Sometimes outputs formatting rules instead of actual content
   - This is a prompt engineering issue in `format_response_mistral()`

## Scripts Created

- `/opt/rag/scripts/rebuild_final.sh` - Complete system rebuild

## Next Steps

1. Tune Phi-3 prompts for better intent parsing
2. Add keyword extraction fallback when entities=[]
3. Improve response formatting prompt
4. Add rate limiting for auto-investigate
