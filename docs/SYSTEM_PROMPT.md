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
