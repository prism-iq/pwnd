# Implementation Guide

> Code examples and setup instructions for the Self-Evolving AI Agent.

---

## Table of Contents

1. [Project Structure](#1-project-structure)
2. [Memory System](#2-memory-system)
3. [Search Engine](#3-search-engine)
4. [LLM Integration](#4-llm-integration)
5. [API Layer](#5-api-layer)
6. [Self-Improvement Loop](#6-self-improvement-loop)

---

## 1. Project Structure

```
/opt/rag/
├── mind/                        # Persistent memory
│   ├── thoughts.md              # Episodic memory
│   ├── methods.md               # Procedural memory
│   ├── errors.md                # Failure memory
│   └── system_prompt.md         # Behavioral memory
│
├── app/                         # Application code
│   ├── __init__.py
│   ├── routes.py                # API endpoints
│   ├── llm.py                   # LLM integration
│   └── search.py                # Search functions
│
├── db/                          # Data storage
│   └── sources.db               # SQLite database
│
├── docs/paper/                  # Documentation
│   ├── README.md
│   ├── PAPER.md
│   ├── ARCHITECTURE.md
│   └── IMPLEMENTATION.md
│
├── static/                      # Web UI
│   └── index.html
│
├── external_data/               # Ingestion scripts
│   ├── ingest_depositions.py
│   └── ingest_foia.py
│
└── requirements.txt
```

---

## 2. Memory System

### 2.1 Memory File Manager

```python
# app/memory.py

import os
from datetime import datetime
from pathlib import Path

MIND_DIR = Path("/opt/rag/mind")

class Memory:
    """Manages persistent memory files for the agent."""

    @staticmethod
    def read(filename: str) -> str:
        """Read a memory file."""
        path = MIND_DIR / filename
        if path.exists():
            return path.read_text()
        return ""

    @staticmethod
    def write(filename: str, content: str):
        """Overwrite a memory file."""
        path = MIND_DIR / filename
        path.write_text(content)

    @staticmethod
    def append(filename: str, entry: str):
        """Append an entry to a memory file."""
        path = MIND_DIR / filename
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        formatted = f"\n---\n\n## {timestamp}\n\n{entry}\n"

        with open(path, "a") as f:
            f.write(formatted)

    @staticmethod
    def read_all() -> dict:
        """Read all memory files into a dict."""
        return {
            "thoughts": Memory.read("thoughts.md"),
            "methods": Memory.read("methods.md"),
            "errors": Memory.read("errors.md"),
            "system_prompt": Memory.read("system_prompt.md"),
        }
```

### 2.2 Usage Example

```python
from app.memory import Memory

# Before task: load memory
memory = Memory.read_all()
context = f"""
Your system prompt:
{memory['system_prompt']}

Recent thoughts:
{memory['thoughts'][-5000:]}  # Last 5000 chars

Methods that work:
{memory['methods']}

Errors to avoid:
{memory['errors'][-3000:]}
"""

# After task: log result
if success:
    Memory.append("methods.md", f"""
### Pattern: {pattern_name}

**What:** {description}
**Code:**
```python
{code_snippet}
```
**When to use:** {use_case}
""")
else:
    Memory.append("errors.md", f"""
### ERROR: {error_type}

**Symptom:** {symptom}
**Root cause:** {root_cause}
**Fix:** {fix}
**Prevention:** {prevention}
""")
```

---

## 3. Search Engine

### 3.1 SQLite FTS5 Setup

```sql
-- Create the FTS virtual table
CREATE VIRTUAL TABLE contents_fts USING fts5(
    full_text,
    content='contents',
    content_rowid='doc_id'
);

-- Populate from existing data
INSERT INTO contents_fts(rowid, full_text)
SELECT doc_id, full_text FROM contents;

-- Create triggers to keep in sync
CREATE TRIGGER contents_ai AFTER INSERT ON contents BEGIN
    INSERT INTO contents_fts(rowid, full_text) VALUES (new.doc_id, new.full_text);
END;

CREATE TRIGGER contents_ad AFTER DELETE ON contents BEGIN
    INSERT INTO contents_fts(contents_fts, rowid, full_text) VALUES('delete', old.doc_id, old.full_text);
END;

CREATE TRIGGER contents_au AFTER UPDATE ON contents BEGIN
    INSERT INTO contents_fts(contents_fts, rowid, full_text) VALUES('delete', old.doc_id, old.full_text);
    INSERT INTO contents_fts(rowid, full_text) VALUES (new.doc_id, new.full_text);
END;
```

### 3.2 Search Function

```python
# app/search.py

import sqlite3
from typing import List, Dict

DB_PATH = "/opt/rag/db/sources.db"

def search_documents(query: str, limit: int = 30) -> List[Dict]:
    """
    Search documents using FTS5 with BM25 ranking.

    Args:
        query: Search terms (supports boolean operators)
        limit: Maximum results to return

    Returns:
        List of dicts with doc_id, filename, content preview
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # FTS5 MATCH query with BM25 ranking
        cursor.execute("""
            SELECT
                c.doc_id,
                d.filename,
                substr(c.full_text, 1, 2000) as content,
                bm25(contents_fts) as rank
            FROM contents_fts
            JOIN contents c ON c.doc_id = contents_fts.rowid
            JOIN documents d ON d.id = c.doc_id
            WHERE contents_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (query, limit))

        results = []
        for row in cursor.fetchall():
            results.append({
                "doc_id": row[0],
                "filename": row[1],
                "content": row[2],
                "score": row[3]
            })

        return results

    except sqlite3.OperationalError as e:
        # Log to errors.md
        Memory.append("errors.md", f"""
### ERROR: Search failed

**Query:** {query}
**Error:** {str(e)}
**Possible cause:** Invalid FTS5 syntax
""")
        return []
    finally:
        conn.close()


def search_with_fallback(query: str, limit: int = 30) -> List[Dict]:
    """
    Search with fallback to LIKE if FTS fails.
    """
    results = search_documents(query, limit)

    if not results:
        # Fallback to LIKE search
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                c.doc_id,
                d.filename,
                substr(c.full_text, 1, 2000) as content
            FROM contents c
            JOIN documents d ON d.id = c.doc_id
            WHERE c.full_text LIKE ?
            LIMIT ?
        """, (f"%{query}%", limit))

        results = [
            {"doc_id": r[0], "filename": r[1], "content": r[2], "score": 0}
            for r in cursor.fetchall()
        ]
        conn.close()

    return results
```

---

## 4. LLM Integration

### 4.1 Claude API Wrapper

```python
# app/llm.py

import anthropic
from typing import Dict, Optional
from app.memory import Memory

client = anthropic.Anthropic()

async def call_claude(
    prompt: str,
    model: str = "claude-3-haiku-20240307",
    max_tokens: int = 4096,
    include_memory: bool = True
) -> Dict:
    """
    Call Claude API with optional memory context.

    Args:
        prompt: The user's prompt
        model: Model to use (haiku for speed, opus for depth)
        max_tokens: Maximum response length
        include_memory: Whether to include memory files in context

    Returns:
        Dict with 'text' or 'error' key
    """
    try:
        # Build system prompt with memory
        system = ""
        if include_memory:
            memory = Memory.read_all()
            system = f"""
{memory['system_prompt']}

## Recent Context

### Thoughts (last 3000 chars)
{memory['thoughts'][-3000:]}

### Methods Available
{memory['methods'][:2000]}

### Errors to Avoid
{memory['errors'][-2000:]}
"""

        # Make API call
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system if system else None,
            messages=[{"role": "user", "content": prompt}]
        )

        return {"text": response.content[0].text}

    except anthropic.APIError as e:
        error_msg = f"API Error: {e.status_code} - {str(e)}"
        Memory.append("errors.md", f"""
### ERROR: LLM API call failed

**Model:** {model}
**Error:** {error_msg}
**Prompt length:** {len(prompt)} chars
""")
        return {"error": error_msg}


async def synthesize_answer(query: str, documents: list) -> str:
    """
    Synthesize an answer from search results.
    """
    # Build context from documents
    doc_context = "\n\n".join([
        f"[{d['filename']}]\n{d['content']}"
        for d in documents[:10]  # Top 10 results
    ])

    prompt = f"""Based on the following documents, answer this question:

Question: {query}

Documents:
{doc_context}

Instructions:
1. Cite specific documents by filename
2. Quote relevant passages
3. Say "insufficient evidence" if documents don't support an answer
4. Be concise but thorough
"""

    result = await call_claude(prompt, model="claude-3-haiku-20240307")

    if "error" in result:
        return f"Error synthesizing answer: {result['error']}"

    return result["text"]
```

---

## 5. API Layer

### 5.1 FastAPI Routes

```python
# app/routes.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import asyncio

from app.search import search_with_fallback
from app.llm import synthesize_answer
from app.memory import Memory

router = APIRouter()

class QueryRequest(BaseModel):
    q: str
    limit: Optional[int] = 30

class QueryResponse(BaseModel):
    answer: str
    sources: list
    query: str

@router.post("/api/query")
async def query_post(request: QueryRequest) -> QueryResponse:
    """
    Main query endpoint: search + synthesize.
    """
    query = request.q.strip()

    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    # Log the query
    Memory.append("thoughts.md", f"""
### Query received

**Question:** {query}
**Processing...**
""")

    # Search documents
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(
        None,
        search_with_fallback,
        query,
        request.limit
    )

    if not results:
        return QueryResponse(
            answer="No relevant documents found for your query.",
            sources=[],
            query=query
        )

    # Synthesize answer
    answer = await synthesize_answer(query, results)
    sources = [r["filename"] for r in results[:10]]

    # Log success
    Memory.append("thoughts.md", f"""
**Answer generated**
- Documents found: {len(results)}
- Sources used: {len(sources)}
""")

    return QueryResponse(
        answer=answer,
        sources=sources,
        query=query
    )


@router.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "memory_files": list(Memory.read_all().keys())}
```

---

## 6. Self-Improvement Loop

### 6.1 Auto-Improvement Daemon

```python
# auto_improve.py

import asyncio
import re
from datetime import datetime
from app.memory import Memory
from app.llm import call_claude

async def run_quality_tests() -> float:
    """
    Run quality tests and return a score 0-100.
    """
    # Example: test search functionality
    test_queries = [
        ("epstein flight", True),      # Should find results
        ("asdfghjkl12345", False),      # Should not find results
        ("maxwell deposition", True),
    ]

    passed = 0
    for query, should_find in test_queries:
        results = search_with_fallback(query)
        if (len(results) > 0) == should_find:
            passed += 1

    return (passed / len(test_queries)) * 100


async def analyze_recent_errors() -> list:
    """
    Analyze errors.md for patterns.
    """
    errors = Memory.read("errors.md")

    # Extract error types
    error_types = re.findall(r"### ERROR: (.+)", errors)

    # Count occurrences
    from collections import Counter
    counts = Counter(error_types)

    # Return patterns (3+ occurrences)
    return [error for error, count in counts.items() if count >= 3]


async def update_system_prompt(patterns: list):
    """
    Add anti-patterns to system prompt.
    """
    prompt = Memory.read("system_prompt.md")

    # Find anti-patterns section
    if "## Anti-Patterns to Avoid" in prompt:
        for pattern in patterns:
            if pattern not in prompt:
                # Add the pattern
                prompt = prompt.replace(
                    "## Anti-Patterns to Avoid",
                    f"## Anti-Patterns to Avoid\n\n- Avoid: {pattern}"
                )

        Memory.write("system_prompt.md", prompt)

        # Log the update
        Memory.append("thoughts.md", f"""
### Self-improvement: Updated system prompt

Added {len(patterns)} new anti-patterns:
{chr(10).join(f'- {p}' for p in patterns)}
""")


async def self_improvement_loop():
    """
    Main loop: test, analyze, improve.
    """
    previous_score = 0

    while True:
        try:
            # 1. Run quality tests
            score = await run_quality_tests()

            print(f"[{datetime.now()}] Quality score: {score}%")

            # 2. If quality dropped, investigate
            if score < previous_score:
                Memory.append("thoughts.md", f"""
### Quality alert

Score dropped: {previous_score}% → {score}%
Investigating...
""")

                # Analyze errors
                patterns = await analyze_recent_errors()

                if patterns:
                    # Update system prompt
                    await update_system_prompt(patterns)

            previous_score = score

            # Wait 5 minutes
            await asyncio.sleep(300)

        except Exception as e:
            Memory.append("errors.md", f"""
### ERROR: Self-improvement loop failed

**Error:** {str(e)}
**Continuing after delay...**
""")
            await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(self_improvement_loop())
```

### 6.2 Running the Daemon

```bash
# Start the self-improvement loop
nohup python auto_improve.py > /var/log/auto_improve.log 2>&1 &

# Check status
tail -f /var/log/auto_improve.log

# View improvements
cat /opt/rag/mind/system_prompt.md | grep "Anti-Pattern"
```

---

## 7. Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/prism-iq/pwnd.git
cd pwnd

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up environment
export ANTHROPIC_API_KEY="sk-ant-..."

# 4. Initialize database
python scripts/init_db.py

# 5. Create memory files
mkdir -p /opt/rag/mind
touch /opt/rag/mind/{thoughts,methods,errors,system_prompt}.md

# 6. Start the API
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 7. Start the self-improvement daemon (optional)
python auto_improve.py &
```

---

## 8. Requirements

```
# requirements.txt

fastapi>=0.100.0
uvicorn>=0.23.0
anthropic>=0.18.0
pydantic>=2.0.0
aiofiles>=23.0.0
python-multipart>=0.0.6
```

---

*This implementation guide reflects the system as of 2026-01-10. The code evolves; keep these docs updated.*
