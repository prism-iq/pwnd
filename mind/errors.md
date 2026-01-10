# Errors - What Failed

> A record of failures, their root causes, and lessons learned.
> Every error is a teacher.

---

## 2026-01-10

### ERROR: /api/query endpoint not found
**Symptom:** UI POST to `/api/query` returned 404
**Root cause:** Only GET `/api/ask` existed in routes.py
**Fix:** Added new POST endpoint
**Lesson:** When changing UI, verify corresponding backend endpoints exist

---

### ERROR: Field name mismatch
**Symptom:** Query endpoint received empty query
**Root cause:** UI sent `{query: ...}`, Pydantic model expected `{q: ...}`
**Fix:** Changed UI to send `{q: query}`
**Lesson:** Always verify request/response schemas match between frontend and backend

---

### ERROR: Async/sync mismatch
**Symptom:** `TypeError: object function can't be used in 'await' expression`
**Root cause:** `search_corpus_scored` is synchronous, called with await
**Fix:** Used `loop.run_in_executor(None, sync_func, args)`
**Lesson:** Check function signatures before awaiting. Use executor for sync functions in async context.

---

### ERROR: LLM response type assumption
**Symptom:** `TypeError: 'dict' object is not subscriptable as string`
**Root cause:** Assumed `call_haiku()` returns string, actually returns Dict
**Fix:** Added type checking: `if isinstance(result, dict): ...`
**Lesson:** Never assume return types. Check actual implementation or use type hints.

---

### ERROR: Empty search results
**Symptom:** Queries returned no documents despite database having 15K+ docs
**Root cause:** Old search hit `emails` table, documents are in `contents` table
**Fix:** Created new search function using `contents_fts` FTS index
**Lesson:** Verify which tables contain the data you're searching

---

### ERROR: LLM 400 Bad Request (RESOLVED)
**Symptom:** Search returns results, but LLM synthesis fails with 400
**Root cause:** Anthropic account has no credits ("Your credit balance is too low")
**Fix:** Removed LLM synthesis from API - return search results directly. Claude Opus handles synthesis in conversation.
**Lesson:** Don't depend on external paid APIs for core functionality. Use local fallbacks or design around it.

---

*This log helps me avoid repeating mistakes.*
