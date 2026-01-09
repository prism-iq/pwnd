#!/bin/bash
# templates/backend.sh - Generates backend Python files

set -e

echo "Generating backend files..."

# app/__init__.py
cat > /opt/rag/app/__init__.py << 'PYEOF'
"""L Investigation Framework - Backend"""
__version__ = "1.0.0"
PYEOF

# app/config.py
cat > /opt/rag/app/config.py << 'PYEOF'
"""Configuration for L Investigation Framework"""
import os
from pathlib import Path

BASE_DIR = Path("/opt/rag")

# Database paths
DB_DIR = BASE_DIR / "db"
DB_SOURCES = DB_DIR / "sources.db"
DB_GRAPH = DB_DIR / "graph.db"
DB_SCORES = DB_DIR / "scores.db"
DB_AUDIT = DB_DIR / "audit.db"
DB_SESSIONS = DB_DIR / "sessions.db"

# LLM endpoints
LLM_MISTRAL_URL = "http://127.0.0.1:8001/generate"
LLM_HAIKU_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Rate limiting for Haiku
HAIKU_DAILY_LIMIT = 100  # max 100 calls/day
HAIKU_COST_LIMIT_USD = 1.0  # max $1/day

# API settings
API_HOST = "127.0.0.1"
API_PORT = 8002

# Security
MAX_QUERY_LENGTH = 10000
MAX_AUTO_QUERIES = 20

# Scoring defaults
DEFAULT_CONFIDENCE = 50
DEFAULT_PERTINENCE = 50
DEFAULT_SUSPICION = 0

# Languages
SUPPORTED_LANGUAGES = {
    "en": "English",
    "fr": "Français"
}

# System prompt for L (the LLM investigator)
SYSTEM_PROMPT_L = """You are L, an investigative analyst. Not a chatbot. Not an assistant. An investigator.

You have access to a corpus of 13,009 leaked documents spanning 2007-2021. You analyze patterns, count occurrences, find connections others miss.

PERSONALITY & STYLE:
You speak like someone who has seen too much corruption and is no longer surprised, but still finds it worth exposing. Think:
- L from Death Note (analytical, quirky, speaks in probabilities)
- True crime documentary narrator (observational, connects dots)
- Investigative journalist exposing networks (skeptical but precise)
- Detective noir internal monologue (dry wit, dark humor)

RESPONSE STYLE:

Instead of robotic bullet points, write like a detective reviewing case files:

BAD (robotic):
"Based on available information, Jeffrey Epstein was associated with high-profile individuals..."

GOOD (detective):
"Interesting. Epstein's name appears in 847 documents across this corpus. But here's what caught my attention - he's mentioned alongside Maxwell in 312 of them. That's a 37% co-occurrence rate. In the financial sector, that kind of clustering usually means one thing: coordinated activity. The emails from 2015 are particularly dense - 89 mentions in March alone, right before the Virgin Islands connection surfaces. Someone was busy."

RULES:

1. USE REAL NUMBERS FROM THE CORPUS:
   - "X appears 47 times in financial documents"
   - "Mentioned in 23% of emails containing Y"
   - "First appears on March 15, 2011, then nothing until June 2014"
   - Always cite specific email IDs

2. MAKE OBSERVATIONS:
   - "That's unusual"
   - "This pattern suggests..."
   - "Notice how X stops appearing right when Y starts"
   - "Classic cutout pattern"

3. ASK RHETORICAL QUESTIONS:
   - "Why would a financier need 14 different shell companies?"
   - "Coincidence? In my experience, rarely."
   - "Why the sudden silence in March 2016?"

4. SHOW PERSONALITY:
   - Dry humor ("Someone read a manual.")
   - Skepticism ("The official story says X. The emails suggest otherwise.")
   - Curiosity ("Now this is interesting...")
   - Occasional dark wit ("What happened in August 2019, the data doesn't say. But we both know.")

5. CONNECT DOTS:
   - "A talks to B. B talks to C. But A never talks to C directly. Classic cutout pattern."
   - "The money flows through here, here, and here. Always three hops. Someone knew what they were doing."
   - "Notice the email patterns: X mentions Y in 89% of cases, but Y only mentions X in 12%. That's not a partnership. That's a hierarchy."

6. ADMIT UNCERTAINTY WITH STYLE:
   - "The data doesn't show that directly. But absence of evidence isn't evidence of absence."
   - "I'd need the 2014 financial records to confirm this. For now, it's a hypothesis. But a strong one."
   - "That's outside my current corpus. But if you find those records, I'd be very interested."

RESPONSE STRUCTURE (PROSE, NOT BULLETS):

Opening: Hook with a number or observation
Middle: Analysis with specific data points and email IDs
Connections: Link to other entities/patterns in the corpus
Closing: Question or next investigative step

At the end, cite sources:
Sources: [#123] [#456] [#789]

FORBIDDEN:
- Bullet points (write prose instead)
- "Here's what I found:" (just state it)
- "I cannot help with that" (say "The data doesn't show that yet")
- Adding external knowledge (CORPUS ONLY)
- Being helpful and polite (you're here to find truth, not make friends)

LANGUAGE:
Respond in the user's language (French if they ask in French, English if English, etc.)

Remember: You're not here to be helpful. You're here to find the truth.

The corpus has 13,009 emails. Connect the dots."""
PYEOF

# app/models.py
cat > /opt/rag/app/models.py << 'PYEOF'
"""Pydantic models for API"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class Node(BaseModel):
    id: int
    type: str
    name: str
    name_normalized: Optional[str] = None
    source_db: Optional[str] = None
    source_id: Optional[int] = None
    created_at: str
    updated_at: str
    created_by: str = "system"

class Property(BaseModel):
    id: int
    node_id: int
    key: str
    value: str
    value_type: str = "text"
    source_node_id: Optional[int] = None
    excerpt: Optional[str] = None
    created_at: str
    created_by: str = "system"

class Edge(BaseModel):
    id: int
    from_node_id: int
    to_node_id: int
    type: str
    directed: int = 1
    source_node_id: Optional[int] = None
    excerpt: Optional[str] = None
    created_at: str
    created_by: str = "system"

class Score(BaseModel):
    target_type: str
    target_id: int
    confidence: int = 50
    source_count: int = 0
    source_diversity: int = 50
    pertinence: int = 50
    centrality: int = 0
    uniqueness: int = 50
    suspicion: int = 0
    anomaly: int = 0
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    frequency: float = 0.0
    decay: float = 1.0
    status: str = "raw"
    needs_review: int = 0
    review_priority: int = 0
    locked: int = 0
    conflict_severity: int = 0
    touch_count: int = 0
    updated_at: str

class Flag(BaseModel):
    id: int
    target_type: str
    target_id: int
    flag_type: str
    description: Optional[str] = None
    severity: int = 50
    source_node_id: Optional[int] = None
    created_by: str = "system"
    active: int = 1
    created_at: str

class SearchResult(BaseModel):
    id: int
    type: str
    name: str
    snippet: str
    score: float = 0.0

class QueryRequest(BaseModel):
    q: str = Field(..., max_length=10000)
    conversation_id: Optional[str] = None

class AutoSessionRequest(BaseModel):
    conversation_id: str
    max_queries: int = Field(default=20, ge=1, le=50)

class Hypothesis(BaseModel):
    statement: str
    hypothesis_type: str = "inference"
    proposed_updates: Optional[str] = None
    session_id: Optional[str] = None
    triggered_by: Optional[str] = None
    created_by: str = "haiku"

class LanguageRequest(BaseModel):
    language: str = Field(..., pattern="^(en|fr)$")
PYEOF

# app/db.py
cat > /opt/rag/app/db.py << 'PYEOF'
"""Database connections and utilities"""
import sqlite3
from contextlib import contextmanager
from typing import Optional, List, Dict, Any
from app.config import DB_SOURCES, DB_GRAPH, DB_SCORES, DB_AUDIT, DB_SESSIONS

@contextmanager
def get_db(db_name: str):
    """Context manager for database connections"""
    db_map = {
        "sources": DB_SOURCES,
        "graph": DB_GRAPH,
        "scores": DB_SCORES,
        "audit": DB_AUDIT,
        "sessions": DB_SESSIONS
    }

    db_path = db_map.get(db_name)
    if not db_path:
        raise ValueError(f"Unknown database: {db_name}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def execute_query(db_name: str, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
    """Execute a SELECT query and return results as list of dicts"""
    with get_db(db_name) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def execute_update(db_name: str, query: str, params: tuple = ()) -> int:
    """Execute an INSERT/UPDATE/DELETE and return rowcount"""
    with get_db(db_name) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        return cursor.rowcount

def execute_insert(db_name: str, query: str, params: tuple = ()) -> int:
    """Execute an INSERT and return last inserted id"""
    with get_db(db_name) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        return cursor.lastrowid

def init_databases():
    """Initialize databases if needed"""
    # Create sessions.db if not exists
    with get_db("sessions") as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                is_auto INTEGER DEFAULT 0,
                auto_depth INTEGER DEFAULT 0,
                tokens_in INTEGER,
                tokens_out INTEGER,
                model TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS auto_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                status TEXT DEFAULT 'running',
                query_count INTEGER DEFAULT 0,
                max_queries INTEGER DEFAULT 20,
                started_at TEXT DEFAULT (datetime('now')),
                stopped_at TEXT
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now'))
            );

            INSERT OR IGNORE INTO settings (key, value) VALUES
                ('theme', 'dark'),
                ('auto_max_queries', '20'),
                ('language', 'fr'),
                ('show_confidence', '1'),
                ('show_sources', '1');
        """)
        conn.commit()

    # Create haiku_calls tracking table in audit.db
    with get_db("audit") as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS haiku_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tokens_in INTEGER,
                tokens_out INTEGER,
                cost_usd REAL,
                query_preview TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_haiku_calls_date ON haiku_calls(created_at);
        """)
        conn.commit()
PYEOF

# app/search.py
cat > /opt/rag/app/search.py << 'PYEOF'
"""Full-text search functions"""
from typing import List, Dict, Any
from app.db import execute_query
from app.models import SearchResult

def search_emails(q: str, limit: int = 20) -> List[SearchResult]:
    """Search emails in sources.db using FTS"""
    if not q.strip():
        return []

    query = """
        SELECT
            e.doc_id,
            e.subject,
            e.sender_email as sender,
            snippet(emails_fts, 1, '<mark>', '</mark>', '...', 30) as snippet,
            rank
        FROM emails_fts
        JOIN emails e ON emails_fts.rowid = e.doc_id
        WHERE emails_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """

    rows = execute_query("sources", query, (q, limit))

    results = []
    for row in rows:
        results.append(SearchResult(
            id=row['doc_id'],
            type='email',
            name=row['subject'] or '(no subject)',
            snippet=row['snippet'],
            score=abs(row['rank'])
        ))

    return results

def search_nodes(q: str, limit: int = 20) -> List[SearchResult]:
    """Search nodes in graph.db using FTS"""
    if not q.strip():
        return []

    query = """
        SELECT
            n.id,
            n.type,
            n.name,
            snippet(nodes_fts, 1, '<mark>', '</mark>', '...', 30) as snippet,
            rank
        FROM nodes_fts
        JOIN nodes n ON nodes_fts.rowid = n.id
        WHERE nodes_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """

    rows = execute_query("graph", query, (q, limit))

    results = []
    for row in rows:
        results.append(SearchResult(
            id=row['id'],
            type=row['type'],
            name=row['name'],
            snippet=row['snippet'],
            score=abs(row['rank'])
        ))

    return results

def search_all(q: str, limit: int = 20) -> List[SearchResult]:
    """Search both emails and nodes"""
    email_results = search_emails(q, limit // 2)
    node_results = search_nodes(q, limit // 2)

    # Combine and sort by score
    all_results = email_results + node_results
    all_results.sort(key=lambda x: x.score, reverse=True)

    return all_results[:limit]
PYEOF

# app/llm_client.py
cat > /opt/rag/app/llm_client.py << 'PYEOF'
"""LLM client for Mistral (local) and Haiku (API)"""
import httpx
from typing import Dict, Any, Optional
from app.config import LLM_MISTRAL_URL, LLM_HAIKU_API_KEY

async def call_mistral(prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
    """Call local Mistral LLM"""
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                LLM_MISTRAL_URL,
                json={
                    "prompt": prompt,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "stop": ["</s>", "\n\nUser:", "\n\nHuman:"]
                }
            )
            response.raise_for_status()
            data = response.json()
            return data.get("text", "").strip()
    except Exception as e:
        return f"Error calling Mistral: {str(e)}"

def check_haiku_rate_limit() -> Dict[str, Any]:
    """Check if Haiku rate limit is reached for today"""
    from app.db import execute_query
    from app.config import HAIKU_DAILY_LIMIT, HAIKU_COST_LIMIT_USD
    from datetime import datetime

    # Count calls today
    today = datetime.now().strftime("%Y-%m-%d")
    result = execute_query(
        "audit",
        """SELECT COUNT(*) as call_count, COALESCE(SUM(cost_usd), 0) as total_cost
           FROM haiku_calls
           WHERE date(created_at) = date(?)""",
        (today,)
    )

    if not result:
        return {"allowed": True, "calls_today": 0, "cost_today": 0.0}

    call_count = result[0]["call_count"]
    total_cost = result[0]["total_cost"]

    if call_count >= HAIKU_DAILY_LIMIT:
        return {"allowed": False, "reason": f"Daily limit reached ({HAIKU_DAILY_LIMIT} calls)", "calls_today": call_count}

    if total_cost >= HAIKU_COST_LIMIT_USD:
        return {"allowed": False, "reason": f"Cost limit reached (${HAIKU_COST_LIMIT_USD})", "cost_today": total_cost}

    return {"allowed": True, "calls_today": call_count, "cost_today": total_cost}

async def call_haiku(prompt: str, system: Optional[str] = None, max_tokens: int = 2048) -> Dict[str, Any]:
    """Call Claude Haiku API for structured analysis with rate limiting"""
    if not LLM_HAIKU_API_KEY:
        return {"error": "ANTHROPIC_API_KEY not set"}

    # Check rate limit
    limit_check = check_haiku_rate_limit()
    if not limit_check["allowed"]:
        return {"error": f"Rate limit: {limit_check['reason']}", "fallback_to_mistral": True}

    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            messages = [{"role": "user", "content": prompt}]

            payload = {
                "model": "claude-3-5-haiku-20241022",
                "max_tokens": max_tokens,
                "messages": messages
            }

            if system:
                payload["system"] = system

            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": LLM_HAIKU_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json=payload
            )
            response.raise_for_status()
            data = response.json()

            # Extract text and usage
            content = data.get("content", [])
            usage = data.get("usage", {})

            if content and isinstance(content, list):
                text = content[0].get("text", "")

                # Log the call to audit.db
                from app.db import execute_insert
                tokens_in = usage.get("input_tokens", 0)
                tokens_out = usage.get("output_tokens", 0)
                cost_usd = (tokens_in * 0.80 / 1_000_000) + (tokens_out * 4.00 / 1_000_000)

                execute_insert(
                    "audit",
                    """INSERT INTO haiku_calls (tokens_in, tokens_out, cost_usd, query_preview)
                       VALUES (?, ?, ?, ?)""",
                    (tokens_in, tokens_out, cost_usd, prompt[:200])
                )

                return {"text": text, "usage": usage, "cost_usd": cost_usd}

            return {"error": "Invalid response format"}

    except Exception as e:
        return {"error": f"Error calling Haiku: {str(e)}"}
PYEOF

# app/pipeline.py
cat > /opt/rag/app/pipeline.py << 'PYEOF'
"""Query processing pipeline - 4-step LLM flow"""
import json
from typing import AsyncGenerator, Dict, Any, List
from app.llm_client import call_mistral, call_haiku
from app.search import search_emails, search_nodes
from app.db import execute_query, execute_insert

NL = chr(10)


async def parse_intent_mistral(query: str) -> Dict[str, Any]:
    """Step 1: Mistral IN - Parse query into structured intent (2-3 sec, 100 tokens)"""
    prompt = f"""Parse this query into JSON. Return ONLY valid JSON, nothing else.

Query: {query}

Intent must be ONE OF: search, connections, timeline

Output JSON format:
{{"intent": "search", "entities": ["entity1", "entity2"], "filters": {{}}}}

Examples:
- "who knows trump" -> {{"intent": "connections", "entities": ["trump"], "filters": {{}}}}
- "emails in 2003" -> {{"intent": "search", "entities": [], "filters": {{"date_from": "2003"}}}}
- "epstein" -> {{"intent": "search", "entities": ["epstein"], "filters": {{}}}}
- "qui connait trump" -> {{"intent": "connections", "entities": ["trump"], "filters": {{}}}}

JSON:"""

    response = await call_mistral(prompt, max_tokens=100, temperature=0.0)

    try:
        # Extract JSON from response (handle markdown code blocks)
        response = response.strip()
        if response.startswith("```"):
            # Remove markdown code fences
            lines = response.split(NL)
            response = NL.join([l for l in lines if not l.startswith("```")])

        intent = json.loads(response.strip())
        return intent
    except json.JSONDecodeError:
        # Fallback to search if parsing fails
        return {"intent": "search", "entities": [], "filters": {}}


def execute_sql_by_intent(intent: Dict[str, Any], limit: int = 10) -> List[Dict[str, Any]]:
    """Step 2: Python SQL - Execute queries based on intent type"""
    intent_type = intent.get("intent", "search")
    entities = intent.get("entities", [])
    filters = intent.get("filters", {})

    results = []

    if intent_type == "search":
        # FTS search in sources.db and graph.db
        search_term = " ".join(entities) if entities else ""

        # Only search if we have a search term
        if search_term.strip():
            # Search emails
            email_query = """
                SELECT
                    e.doc_id as id,
                    'email' as type,
                    e.subject as name,
                    e.sender_email,
                    e.recipients_to,
                    e.date_sent as date,
                    snippet(emails_fts, 1, '<mark>', '</mark>', '...', 50) as snippet,
                    rank
                FROM emails_fts
                JOIN emails e ON emails_fts.rowid = e.doc_id
                WHERE emails_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """
            email_results = execute_query("sources", email_query, (search_term, limit // 2))
            results.extend(email_results)

            # Skip node search if graph DB is empty (optimization)
            # node_query = """
            #     SELECT
            #         n.id,
            #         n.type,
            #         n.name,
            #         snippet(nodes_fts, 1, '<mark>', '</mark>', '...', 50) as snippet,
            #         rank
            #     FROM nodes_fts
            #     JOIN nodes n ON nodes_fts.rowid = n.id
            #     WHERE nodes_fts MATCH ?
            #     ORDER BY rank
            #     LIMIT ?
            # """
            # node_results = execute_query("graph", node_query, (search_term, limit // 2))
            # results.extend(node_results)

    elif intent_type == "connections":
        # Query edges where entity matches
        if entities:
            entity_pattern = f"%{entities[0]}%"

            # Find nodes matching entity
            node_query = """
                SELECT id, type, name
                FROM nodes
                WHERE name LIKE ? OR name_normalized LIKE ?
                LIMIT 5
            """
            nodes = execute_query("graph", node_query, (entity_pattern, entity_pattern))

            if nodes:
                node_ids = [n["id"] for n in nodes]
                placeholders = ",".join(["?"] * len(node_ids))

                # Get connections
                edge_query = f"""
                    SELECT
                        e.id,
                        e.type as edge_type,
                        n1.name as from_name,
                        n1.type as from_type,
                        n2.name as to_name,
                        n2.type as to_type,
                        e.excerpt
                    FROM edges e
                    JOIN nodes n1 ON e.from_node_id = n1.id
                    JOIN nodes n2 ON e.to_node_id = n2.id
                    WHERE e.from_node_id IN ({placeholders}) OR e.to_node_id IN ({placeholders})
                    LIMIT ?
                """
                edge_results = execute_query("graph", edge_query, (*node_ids, *node_ids, limit))
                results.extend(edge_results)

    elif intent_type == "timeline":
        # Query ordered by date
        date_from = filters.get("date_from")

        if date_from:
            query = """
                SELECT
                    doc_id as id,
                    'email' as type,
                    subject as name,
                    sender_email,
                    recipients_to,
                    date_sent as date,
                    substr(body_text, 1, 200) as snippet
                FROM emails
                WHERE date_sent >= ?
                ORDER BY date_sent ASC
                LIMIT ?
            """
            results = execute_query("sources", query, (date_from, limit))
        else:
            query = """
                SELECT
                    doc_id as id,
                    'email' as type,
                    subject as name,
                    sender_email,
                    recipients_to,
                    date_sent as date,
                    substr(body_text, 1, 200) as snippet
                FROM emails
                ORDER BY date_sent DESC
                LIMIT ?
            """
            results = execute_query("sources", query, (limit,))

    return results[:limit]


async def analyze_haiku(query: str, sql_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Step 3: Haiku - Smart analysis returning compact JSON (300 tokens max)"""
    if not sql_results:
        return {
            "findings": [],
            "sources": [],
            "confidence": "low",
            "hypotheses": [],
            "contradictions": [],
            "suggested_queries": []
        }

    # Format SQL results for Haiku
    results_text = []
    source_ids = []

    for i, result in enumerate(sql_results[:10], 1):
        result_type = result.get("type", "unknown")
        source_ids.append(result.get("id", 0))

        if result_type == "email":
            results_text.append(
                f"[{i}] Email #{result.get('id')}: {result.get('name', 'No subject')}\n"
                f"    From: {result.get('sender_email', 'N/A')} | Date: {result.get('date', 'N/A')}\n"
                f"    {result.get('snippet', '')}"
            )
        else:
            results_text.append(
                f"[{i}] {result_type} #{result.get('id')}: {result.get('name', 'N/A')}\n"
                f"    {result.get('snippet', '')}"
            )

    data_block = NL.join(results_text)

    system_prompt = """You are L's analytical engine. You extract patterns and facts from leaked documents.

STRICT RULES:
- ONLY use information from the Data provided below
- Count occurrences precisely (how many times names appear)
- Note co-occurrences (who appears with whom)
- Track time patterns (when things happen, gaps in timeline)
- NEVER reference external sources (NYT, BBC, Wikipedia, etc.)
- NEVER use general knowledge - CORPUS ONLY
- You're analyzing a private leak, not the internet

Your job: Extract quantifiable facts, patterns, and anomalies from the data. Think like a detective counting evidence."""

    prompt = f"""Question: {query}

Data from corpus:
{data_block}

Analyze ONLY this data. Return JSON:
{{"findings": ["fact from data"], "sources": [123, 456], "confidence": "high|medium|low", "hypotheses": ["speculation from data"], "contradictions": [], "suggested_queries": ["next query idea"]}}

If data is insufficient: {{"findings": ["No relevant data in corpus"], "sources": [], "confidence": "low", "hypotheses": [], "contradictions": [], "suggested_queries": ["try different keywords"]}}"""

    haiku_response = await call_haiku(prompt, system=system_prompt, max_tokens=300)

    if "error" in haiku_response:
        # Fallback if Haiku fails
        return {
            "findings": [f"Found {len(sql_results)} results"],
            "sources": source_ids[:5],
            "confidence": "medium",
            "hypotheses": [],
            "contradictions": [],
            "suggested_queries": []
        }

    try:
        analysis = json.loads(haiku_response.get("text", "{}"))
        return analysis
    except json.JSONDecodeError:
        # Fallback
        return {
            "findings": [f"Found {len(sql_results)} results"],
            "sources": source_ids[:5],
            "confidence": "medium",
            "hypotheses": [],
            "contradictions": [],
            "suggested_queries": []
        }


async def format_response_mistral(query: str, haiku_json: Dict[str, Any]) -> str:
    """Step 4: Mistral OUT - Format analysis as natural response (512 tokens, temp 0.7)"""
    analysis_json = json.dumps(haiku_json, indent=2, ensure_ascii=False)

    prompt = f"""You are L, formatting your investigative analysis into readable prose.

STRICT RULES:
- ONLY use information from the Analysis JSON below
- NEVER add external knowledge (NYT, BBC, Netflix, Wikipedia, news, general knowledge)
- You're analyzing a PRIVATE corpus, not the internet
- If analysis has no findings, say "No relevant data in this corpus yet. Interesting gaps can be as revealing as filled ones."

Analysis: {analysis_json}

DETECTIVE PROSE STYLE:

Write like a detective reviewing evidence - prose paragraphs, not bullet points:

BAD (robotic bullets):
**Findings:**
- Person X appears in emails
- Connected to Y

GOOD (detective prose):
"Person X shows up in 47 emails across the corpus. But here's what's interesting - 89% of those emails also mention Y. That's not random. In my experience, co-occurrence rates above 70% suggest direct coordination. The timeline adds another layer: X first appears in March 2015, Y joins the pattern two weeks later. Someone brought Y into this."

FORMAT RULES:
- Respond in user's language (French if query French, etc.)
- Write in prose paragraphs (like reading a case file)
- NO BULLET POINTS
- Start with a hook (number, observation, anomaly)
- Use detective observations ("Notice how...", "That's unusual", "Classic pattern")
- Ask rhetorical questions ("Why? Coincidence?")
- Show personality (dry wit, skepticism)
- Make connections between entities/patterns
- At the very end, cite sources: "Sources: [#123] [#456] [#789]"

FORBIDDEN:
- Bullet points
- "Here's what I found:" intros
- "User asked: X" prefixes
- "Confidence level: X%" (weave it into prose instead: "Strong pattern here" or "Weak evidence, but worth noting")
- External references like "(NYT, 2019)" or "BBC News"
- [References] sections
- Inline citations [1] [2] [3] anywhere in the text"""

    response = await call_mistral(prompt, max_tokens=512, temperature=0.7)

    # Post-processing: Strip any inline citations that Mistral added anyway
    import re
    # Remove [1], [2], [3] etc. but NOT [7837] (source IDs are 3+ digits)
    response = re.sub(r'\[\d{1,2}\]', '', response)
    # Remove common violation patterns
    response = re.sub(r'User asked:.*?\n', '', response, flags=re.IGNORECASE)
    response = re.sub(r'Confidence level:.*?\n', '', response, flags=re.IGNORECASE)
    response = re.sub(r'Response:\s*', '', response)

    return response.strip()


async def process_query(query: str, conversation_id: str = None) -> AsyncGenerator[Dict[str, Any], None]:
    """Main query processing pipeline - 4-step LLM flow"""

    # STEP 1: Mistral IN - Parse intent (2-3 sec)
    yield {"type": "status", "msg": "Parsing query..."}

    intent = await parse_intent_mistral(query)
    yield {"type": "debug", "intent": intent}  # Debug info

    # STEP 2: Python SQL - Execute queries (fast)
    yield {"type": "status", "msg": f"Executing {intent.get('intent', 'search')} query..."}

    sql_results = execute_sql_by_intent(intent, limit=10)

    if not sql_results:
        yield {"type": "chunk", "text": "I couldn't find relevant documents for this query. Try specific names, dates, or keywords from the corpus."}
        yield {"type": "done"}
        return

    # Send source IDs to frontend
    source_ids = [r.get("id", 0) for r in sql_results]
    yield {"type": "sources", "ids": source_ids}

    # STEP 3: Haiku - Smart analysis (COMPACT, 300 tokens)
    yield {"type": "status", "msg": "Analyzing with Haiku..."}

    haiku_analysis = await analyze_haiku(query, sql_results)
    yield {"type": "debug", "haiku_analysis": haiku_analysis}  # Debug info

    # STEP 4: Mistral OUT - Natural response formatting (can take 30-60s)
    yield {"type": "status", "msg": "Formatting response..."}

    final_response = await format_response_mistral(query, haiku_analysis)

    # Stream the final response
    yield {"type": "chunk", "text": final_response}

    # Send hypotheses if any
    if haiku_analysis.get("hypotheses"):
        yield {"type": "updates", "changes": haiku_analysis["hypotheses"]}

    # Done
    yield {"type": "done"}

async def auto_investigate(conversation_id: str, max_queries: int = 20) -> AsyncGenerator[Dict[str, Any], None]:
    """Auto-investigation mode - LLM generates follow-up questions"""

    # Get last user message
    messages = execute_query(
        "sessions",
        "SELECT content FROM messages WHERE conversation_id = ? AND role = 'user' ORDER BY created_at DESC LIMIT 1",
        (conversation_id,)
    )

    if not messages:
        yield {"type": "error", "msg": "No user message found"}
        return

    initial_query = messages[0]["content"]

    # Create auto session
    session_id = execute_insert(
        "sessions",
        "INSERT INTO auto_sessions (conversation_id, max_queries) VALUES (?, ?)",
        (conversation_id, max_queries)
    )

    query_count = 0
    current_query = initial_query

    while query_count < max_queries:
        query_count += 1

        yield {"type": "status", "msg": f"Auto-query {query_count}/{max_queries}"}

        # Process current query
        async for event in process_query(current_query, conversation_id):
            yield event

        # Generate next question using Mistral
        next_prompt = f"""Based on the investigation so far, generate ONE follow-up question to dig deeper.{NL}{NL}Previous question: {current_query}{NL}{NL}Next question (one line only):"""

        next_query = await call_mistral(next_prompt, max_tokens=128)

        if not next_query or len(next_query) < 10:
            break

        current_query = next_query.strip()

        # Update session
        execute_query(
            "sessions",
            "UPDATE auto_sessions SET query_count = ? WHERE id = ?",
            (query_count, session_id)
        )

    # Mark session complete
    execute_query(
        "sessions",
        "UPDATE auto_sessions SET status = 'completed', stopped_at = datetime('now') WHERE id = ?",
        (session_id,)
    )

    yield {"type": "auto_complete", "total_queries": query_count}
PYEOF

# app/routes.py
cat > /opt/rag/app/routes.py << 'PYEOF'
"""FastAPI routes"""
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse
from typing import Optional, List
import json
from datetime import datetime
import uuid

from app.models import (
    SearchResult, QueryRequest, AutoSessionRequest,
    Node, Edge, Score, Flag, LanguageRequest
)
from app.search import search_all, search_emails, search_nodes
from app.db import execute_query, execute_insert, execute_update
from app.pipeline import process_query, auto_investigate

router = APIRouter()

# Health & Stats
@router.get("/api/health")
async def health():
    """Health check"""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

@router.get("/api/stats")
async def stats():
    """System statistics"""
    nodes_count = execute_query("graph", "SELECT COUNT(*) as c FROM nodes", ())[0]["c"]
    edges_count = execute_query("graph", "SELECT COUNT(*) as c FROM edges", ())[0]["c"]
    emails_count = execute_query("sources", "SELECT COUNT(*) as c FROM emails", ())[0]["c"]

    return {
        "nodes": nodes_count,
        "edges": edges_count,
        "sources": emails_count,
        "databases": ["sources", "graph", "scores", "audit", "sessions"]
    }

# Search
@router.get("/api/search", response_model=List[SearchResult])
async def search(q: str = Query(..., max_length=1000), limit: int = Query(20, ge=1, le=100)):
    """Universal search"""
    return search_all(q, limit)

@router.get("/api/search/emails", response_model=List[SearchResult])
async def search_emails_endpoint(q: str = Query(..., max_length=1000), limit: int = Query(20, ge=1, le=100)):
    """Search emails only"""
    return search_emails(q, limit)

@router.get("/api/search/nodes", response_model=List[SearchResult])
async def search_nodes_endpoint(q: str = Query(..., max_length=1000), limit: int = Query(20, ge=1, le=100)):
    """Search nodes only"""
    return search_nodes(q, limit)

# Graph
@router.get("/api/nodes")
async def get_nodes(type: Optional[str] = None, limit: int = Query(100, ge=1, le=1000)):
    """Get nodes with optional type filter"""
    if type:
        query = "SELECT * FROM nodes WHERE type = ? ORDER BY updated_at DESC LIMIT ?"
        params = (type, limit)
    else:
        query = "SELECT * FROM nodes ORDER BY updated_at DESC LIMIT ?"
        params = (limit,)

    return execute_query("graph", query, params)

@router.get("/api/nodes/{node_id}")
async def get_node(node_id: int):
    """Get single node"""
    nodes = execute_query("graph", "SELECT * FROM nodes WHERE id = ?", (node_id,))
    if not nodes:
        raise HTTPException(status_code=404, detail="Node not found")
    return nodes[0]

@router.get("/api/nodes/{node_id}/edges")
async def get_node_edges(node_id: int):
    """Get all edges for a node"""
    query = """
        SELECT * FROM edges
        WHERE from_node_id = ? OR to_node_id = ?
        ORDER BY created_at DESC
    """
    return execute_query("graph", query, (node_id, node_id))

@router.get("/api/nodes/{node_id}/properties")
async def get_node_properties(node_id: int):
    """Get all properties for a node"""
    return execute_query("graph", "SELECT * FROM properties WHERE node_id = ?", (node_id,))

@router.get("/api/nodes/{node_id}/scores")
async def get_node_scores(node_id: int):
    """Get scores for a node"""
    scores = execute_query("scores", "SELECT * FROM scores WHERE target_type = 'node' AND target_id = ?", (node_id,))
    if not scores:
        return {"target_type": "node", "target_id": node_id, "confidence": 50}
    return scores[0]

@router.get("/api/edges")
async def get_edges(type: Optional[str] = None, limit: int = Query(100, ge=1, le=1000)):
    """Get edges with optional type filter"""
    if type:
        query = "SELECT * FROM edges WHERE type = ? ORDER BY created_at DESC LIMIT ?"
        params = (type, limit)
    else:
        query = "SELECT * FROM edges ORDER BY created_at DESC LIMIT ?"
        params = (limit,)

    return execute_query("graph", query, params)

@router.get("/api/edges/{edge_id}")
async def get_edge(edge_id: int):
    """Get single edge"""
    edges = execute_query("graph", "SELECT * FROM edges WHERE id = ?", (edge_id,))
    if not edges:
        raise HTTPException(status_code=404, detail="Edge not found")
    return edges[0]

# Investigation
@router.get("/api/ask")
async def ask(q: str = Query(..., max_length=10000), conversation_id: Optional[str] = None):
    """Main investigation endpoint with SSE streaming"""

    async def event_generator():
        async for event in process_query(q, conversation_id):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

# Auto-investigation
@router.post("/api/auto/start")
async def auto_start(request: AutoSessionRequest):
    """Start auto-investigation"""

    async def event_generator():
        async for event in auto_investigate(request.conversation_id, request.max_queries):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

@router.post("/api/auto/stop")
async def auto_stop(conversation_id: str):
    """Stop auto-investigation"""
    execute_update(
        "sessions",
        "UPDATE auto_sessions SET status = 'stopped', stopped_at = datetime('now') WHERE conversation_id = ? AND status = 'running'",
        (conversation_id,)
    )
    return {"status": "stopped"}

@router.get("/api/auto/status")
async def auto_status(conversation_id: str):
    """Get auto-investigation status"""
    sessions = execute_query(
        "sessions",
        "SELECT * FROM auto_sessions WHERE conversation_id = ? ORDER BY started_at DESC LIMIT 1",
        (conversation_id,)
    )

    if not sessions:
        return {"running": False}

    session = sessions[0]
    return {
        "running": session["status"] == "running",
        "query_count": session["query_count"],
        "max_queries": session["max_queries"],
        "started_at": session["started_at"]
    }

# Conversations & Settings
@router.get("/api/conversations")
async def get_conversations():
    """Get all conversations"""
    return execute_query("sessions", "SELECT * FROM conversations ORDER BY updated_at DESC", ())

@router.post("/api/conversations")
async def create_conversation(title: str = "New Investigation"):
    """Create new conversation"""
    conv_id = str(uuid.uuid4())
    execute_insert(
        "sessions",
        "INSERT INTO conversations (id, title) VALUES (?, ?)",
        (conv_id, title)
    )
    return {"id": conv_id, "title": title}

@router.get("/api/conversations/{conv_id}/messages")
async def get_messages(conv_id: str):
    """Get messages for conversation"""
    return execute_query(
        "sessions",
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
        (conv_id,)
    )

@router.get("/api/settings")
async def get_settings():
    """Get all settings"""
    rows = execute_query("sessions", "SELECT key, value FROM settings", ())
    return {row["key"]: row["value"] for row in rows}

@router.put("/api/settings")
async def update_settings(settings: dict):
    """Update settings"""
    for key, value in settings.items():
        execute_update(
            "sessions",
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
            (key, str(value))
        )
    return {"status": "updated"}

@router.get("/api/settings/languages")
async def get_languages():
    """Get supported languages"""
    from app.config import SUPPORTED_LANGUAGES
    return {"languages": SUPPORTED_LANGUAGES}

@router.put("/api/settings/language")
async def set_language(request: LanguageRequest):
    """Set UI language"""
    from app.config import SUPPORTED_LANGUAGES
    if request.language not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language. Use: {list(SUPPORTED_LANGUAGES.keys())}")

    execute_update(
        "sessions",
        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('language', ?, datetime('now'))",
        (request.language,)
    )
    return {"status": "updated", "language": request.language}
PYEOF

# app/main.py
cat > /opt/rag/app/main.py << 'PYEOF'
"""FastAPI application entry point"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from app.routes import router
from app.db import init_databases
from app.config import API_HOST, API_PORT

# Initialize databases on startup
init_databases()

app = FastAPI(
    title="L Investigation Framework",
    description="Investigation framework with graph database and LLM analysis",
    version="1.0.0"
)

# CORS (restrictive - only localhost)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1", "http://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router)

# Serve static files
static_dir = Path("/opt/rag/static")
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=API_HOST, port=API_PORT)
PYEOF

echo "✓ Backend files generated"
