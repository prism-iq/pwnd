# Methods - What Works

> Learned techniques, patterns, and approaches that have proven effective.
> This file is my accumulated wisdom.

---

## Document Ingestion

### PDF Processing
```bash
pdftotext -layout "$pdf_file" -  # Preserves formatting
```
- Use `-layout` flag to maintain table structures
- Process in batches of 100 for large archives
- Chunk files > 50KB into 10KB segments for better search

### Archive Handling
```python
# Supported formats
tar -xzf archive.tar.gz    # .tar.gz
unzip -o archive.zip       # .zip
```
- Always extract to temp directory first
- Verify file count matches manifest

### SQLite FTS Search
```sql
SELECT doc_id, filename, substr(full_text, 1, 2000) as content
FROM contents c
JOIN documents d ON d.id = c.doc_id
WHERE c.doc_id IN (
    SELECT rowid FROM contents_fts WHERE contents_fts MATCH ?
)
LIMIT 30
```
- FTS5 is faster than LIKE queries
- Limit content preview to 2000 chars
- Join with documents table for metadata

---

## UI/UX Patterns

### ChatGPT-Style Interface
- Dark theme: `#212121` background, `#2f2f2f` input
- Max-width: 768px centered
- Typing indicator: 3 bouncing dots animation
- Sources displayed as clickable tags

### Error Display
- Show user-friendly message, log full trace
- Retry button for transient failures

---

## API Design

### POST over GET for queries
```python
@router.post("/api/query")
async def query_post(request: QueryRequest):
```
- POST body allows complex queries
- GET params have length limits

### Async with sync functions
```python
loop = asyncio.get_event_loop()
results = await loop.run_in_executor(None, sync_function, args)
```

---

## LLM Integration

### Response handling
```python
result = await call_haiku(prompt)
if isinstance(result, dict):
    if "error" in result:
        answer = f"Error: {result['error']}"
    else:
        answer = result.get("text", str(result))
```
- Always check return type
- Handle error keys explicitly

---

*Updated: 2026-01-10*
