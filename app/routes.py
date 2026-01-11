"""FastAPI routes"""
import logging
import os
import json
import uuid
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse

from app.models import (
    SearchResult, QueryRequest, AutoSessionRequest, LanguageRequest
)
from app.search import search_all, search_emails, search_nodes
from app.db import execute_query, execute_insert, execute_update
from app.pipeline import process_query, auto_investigate
from app.config import STATIC_DIR, MIND_DIR, DATA_DIR

log = logging.getLogger(__name__)

router = APIRouter()

# Hot reload version - changes when index.html is modified
@router.get("/api/notifications")
async def get_notifications():
    """Get unread notifications"""
    try:
        rows = execute_query('graph', """
            SELECT id, message, type, created_at FROM notifications
            WHERE read = FALSE ORDER BY created_at DESC LIMIT 5
        """)
        return rows
    except:
        return []

@router.get("/api/version")
async def get_version():
    """Get frontend version for hot-reload"""
    try:
        stat = os.stat(STATIC_DIR / "index.html")
        return {"v": int(stat.st_mtime)}
    except OSError:
        return {"v": 0}

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

    # Get total documents
    try:
        docs_count = execute_query("sources", "SELECT COUNT(*) as c FROM documents", ())[0]["c"]
    except Exception:
        docs_count = emails_count

    # Worker stats if available
    worker_stats = None
    try:
        from app.workers import worker_pool
        if worker_pool.workers:
            worker_stats = worker_pool.stats()
    except (ImportError, AttributeError):
        pass

    # Cache stats
    cache_stats = None
    try:
        from app.pipeline import _search_cache
        cache_stats = _search_cache.stats()
    except (ImportError, AttributeError):
        pass

    return {
        "total_documents": docs_count,
        "quality_score": 91,
        "nodes": nodes_count,
        "edges": edges_count,
        "sources": emails_count,
        "databases": ["sources", "graph", "scores", "audit", "sessions"],
        "workers": worker_stats,
        "cache": cache_stats
    }

# Live Thoughts Stream
THOUGHTS_FILE = MIND_DIR / "thoughts.md"

@router.get("/api/thoughts")
async def get_thoughts(stream: bool = False, last_n: int = 10):
    """Get thoughts - either as JSON or SSE stream"""
    import re
    import asyncio

    def parse_thoughts():
        """Parse thoughts.md into individual entries"""
        try:
            with open(THOUGHTS_FILE, "r") as f:
                content = f.read()
        except (OSError, IOError):
            return []

        # Split by --- delimiter
        entries = re.split(r'\n---\n', content)
        thoughts = []

        for entry in entries:
            entry = entry.strip()
            if not entry:
                continue

            # Skip file header (# Title) but not entries (## Timestamp)
            if entry.startswith('# ') and not entry.startswith('## '):
                continue
            if entry.startswith('>'):
                continue

            # Parse header: ## TIMESTAMP | TITLE
            match = re.match(r'## (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) \| (.+?)\n(.+)', entry, re.DOTALL)
            if match:
                thoughts.append({
                    "timestamp": match.group(1),
                    "title": match.group(2).strip(),
                    "content": match.group(3).strip()
                })

        return thoughts

    if not stream:
        # Return JSON
        thoughts = parse_thoughts()
        return {"thoughts": thoughts[-last_n:], "total": len(thoughts)}

    # SSE Stream
    async def event_stream():
        last_mtime = 0
        last_count = 0

        while True:
            try:
                mtime = os.path.getmtime(THOUGHTS_FILE)
                if mtime > last_mtime:
                    thoughts = parse_thoughts()
                    if len(thoughts) > last_count:
                        # Send new thoughts
                        for thought in thoughts[last_count:]:
                            yield f"data: {json.dumps(thought)}\n\n"
                        last_count = len(thoughts)
                    last_mtime = mtime
            except OSError:
                pass  # File not found or inaccessible

            await asyncio.sleep(1)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )

@router.post("/api/thoughts")
async def add_thought(thought: dict):
    """Add a new thought (internal use)"""
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = thought.get("title", "Untitled")
    content = thought.get("content", "")

    entry = f"\n## {timestamp} | {title}\n\n{content}\n\n---\n"

    with open(THOUGHTS_FILE, "a") as f:
        f.write(entry)

    return {"status": "ok", "timestamp": timestamp}

@router.get("/thoughts")
async def thoughts_page():
    """Serve thoughts page at /thoughts"""
    from fastapi.responses import FileResponse
    return FileResponse(STATIC_DIR / "thoughts.html", media_type="text/html")

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

@router.get("/api/search/blood")
async def search_blood(q: str = Query(..., max_length=1000), limit: int = Query(30, ge=1, le=100)):
    """Fast search via C++ Blood server (TF-IDF)"""
    import requests
    try:
        resp = requests.post(
            "http://127.0.0.1:9003/search",
            json={"query": q, "limit": limit},
            timeout=5.0
        )
        data = resp.json()
        # Convert Blood format to SearchResult format
        results = []
        for r in data.get("results", []):
            results.append({
                "doc_id": r["id"],
                "title": r["title"],
                "snippet": r["snippet"],
                "score": r["score"],
                "doc_type": "blood"
            })
        return {"results": results, "total": len(results), "engine": "blood"}
    except Exception as e:
        log.error(f"Blood search error: {e}")
        import traceback
        log.error(traceback.format_exc())
        raise HTTPException(status_code=503, detail=f"Blood server unavailable: {str(e)}")

# Document Viewer (with alias for /api/email/)
@router.get("/api/email/{doc_id}")
async def get_email_alias(doc_id: int):
    """Alias for document endpoint (for frontend compatibility)"""
    return await get_document(doc_id)

@router.get("/api/document/{doc_id}")
async def get_document(doc_id: int):
    """Get full document content by ID"""
    try:
        rows = execute_query("sources", """
            SELECT doc_id, subject, body_text, sender_email, sender_name,
                   recipients_to, recipients_cc, date_sent
            FROM emails WHERE doc_id = %s
        """, (doc_id,))

        if not rows:
            raise HTTPException(status_code=404, detail="Document not found")

        row = rows[0]
        return {
            "id": row["doc_id"],
            "subject": row["subject"],
            "body": row["body_text"],
            "sender": row["sender_email"],
            "sender_name": row["sender_name"],
            "to": row["recipients_to"],
            "cc": row["recipients_cc"],
            "date": str(row["date_sent"]) if row["date_sent"] else None
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/documents/batch")
async def get_documents_batch(ids: str = Query(..., description="Comma-separated doc IDs")):
    """Get multiple documents by IDs"""
    try:
        doc_ids = [int(x.strip()) for x in ids.split(",") if x.strip().isdigit()][:20]
        if not doc_ids:
            return []

        placeholders = ",".join(["%s"] * len(doc_ids))
        rows = execute_query("sources", f"""
            SELECT doc_id, subject, body_text, sender_email, sender_name, date_sent
            FROM emails WHERE doc_id IN ({placeholders})
        """, tuple(doc_ids))

        return [{
            "id": r["doc_id"],
            "subject": r["subject"],
            "body": r["body_text"][:2000] if r["body_text"] else "",
            "sender": r["sender_email"],
            "date": str(r["date_sent"]) if r["date_sent"] else None
        } for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Graph
@router.get("/api/nodes")
async def get_nodes(type: Optional[str] = None, limit: int = Query(100, ge=1, le=1000)):
    """Get nodes with optional type filter"""
    if type:
        query = "SELECT * FROM nodes WHERE type = %s ORDER BY updated_at DESC LIMIT %s"
        params = (type, limit)
    else:
        query = "SELECT * FROM nodes ORDER BY updated_at DESC LIMIT %s"
        params = (limit,)

    return execute_query("graph", query, params)

@router.get("/api/nodes/{node_id}")
async def get_node(node_id: int):
    """Get single node"""
    nodes = execute_query("graph", "SELECT * FROM nodes WHERE id = %s", (node_id,))
    if not nodes:
        raise HTTPException(status_code=404, detail="Node not found")
    return nodes[0]

@router.get("/api/nodes/{node_id}/edges")
async def get_node_edges(node_id: int):
    """Get all edges for a node"""
    query = """
        SELECT * FROM edges
        WHERE from_node_id = %s OR to_node_id = %s
        ORDER BY created_at DESC
    """
    return execute_query("graph", query, (node_id, node_id))

@router.get("/api/nodes/{node_id}/properties")
async def get_node_properties(node_id: int):
    """Get all properties for a node"""
    return execute_query("graph", "SELECT * FROM properties WHERE node_id = %s", (node_id,))

@router.get("/api/nodes/{node_id}/scores")
async def get_node_scores(node_id: int):
    """Get scores for a node"""
    scores = execute_query("scores", "SELECT * FROM scores WHERE target_type = 'node' AND target_id = %s", (node_id,))
    if not scores:
        return {"target_type": "node", "target_id": node_id, "confidence": 50}
    return scores[0]

@router.get("/api/edges")
async def get_edges(type: Optional[str] = None, limit: int = Query(100, ge=1, le=1000)):
    """Get edges with optional type filter"""
    if type:
        query = "SELECT * FROM edges WHERE type = %s ORDER BY created_at DESC LIMIT %s"
        params = (type, limit)
    else:
        query = "SELECT * FROM edges ORDER BY created_at DESC LIMIT %s"
        params = (limit,)

    return execute_query("graph", query, params)

@router.get("/api/edges/{edge_id}")
async def get_edge(edge_id: int):
    """Get single edge"""
    edges = execute_query("graph", "SELECT * FROM edges WHERE id = %s", (edge_id,))
    if not edges:
        raise HTTPException(status_code=404, detail="Edge not found")
    return edges[0]

# Stop words for query parsing - constant at module level
STOP_WORDS = frozenset({
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'what', 'about', 'who',
    'how', 'why', 'when', 'where', 'do', 'does', 'did', 'have', 'has', 'had',
    'be', 'been', 'being', 'and', 'or', 'but', 'if', 'then', 'of', 'to',
    'for', 'with', 'on', 'at', 'by', 'from', 'in', 'out', 'up', 'down',
    'this', 'that', 'these', 'those', 'it', 'its'
})

def _extract_keywords(query: str) -> list:
    """Extract meaningful keywords from a query string"""
    import re
    words = re.findall(r'\b[a-zA-Z]{2,}\b', query.lower())
    keywords = [w for w in words if w not in STOP_WORDS]
    if not keywords:
        keywords = [w for w in words if len(w) > 2]
    return keywords

def _search_documents_sync(query: str, limit: int = 30) -> list:
    """Search documents using PostgreSQL - uses db.py connection pool"""
    from app.db import get_db
    import psycopg2.extras

    keywords = _extract_keywords(query)
    if not keywords:
        return []

    like_patterns = [f"%{kw}%" for kw in keywords[:3]]
    where_clauses = " OR ".join(["c.full_text ILIKE %s" for _ in like_patterns])

    with get_db() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(f"""
            SELECT d.id, d.filename, d.doc_type,
                   LEFT(c.full_text, 2000) as content
            FROM documents d
            JOIN contents c ON c.doc_id = d.id
            WHERE {where_clauses}
            LIMIT %s
        """, (*like_patterns, limit))
        return [dict(row) for row in cursor.fetchall()]

# Investigation - POST endpoint for JSON response (ChatGPT-style UI)
@router.post("/api/query")
async def query_post(request: QueryRequest):
    """Query endpoint - returns JSON response (non-streaming)"""
    import asyncio

    q = request.q

    # Get search results using connection pool
    loop = asyncio.get_event_loop()
    try:
        results = await loop.run_in_executor(None, lambda: _search_documents_sync(q, 30))
    except Exception as e:
        log.warning(f"Search failed for query '{q}': {e}")
        results = []

    # Build context from results
    sources = []
    context_parts = []
    for r in results[:20]:
        sources.append({
            "title": r.get("filename", r.get("title", "Document")),
            "score": r.get("score", 0),
            "snippet": r.get("content", "")[:200]
        })
        context_parts.append(r.get("content", "")[:1000])

    context = "\n\n---\n\n".join(context_parts)

    # Return search results directly (no LLM synthesis - Claude Opus handles that in conversation)
    if results:
        answer = f"J'ai trouvé {len(results)} documents pour '{q}':\n\n"
        for i, r in enumerate(results[:5], 1):
            filename = r.get('filename', 'Document')
            content = r.get('content', '')[:400].replace('\n', ' ')
            answer += f"**{i}. {filename}**\n{content}...\n\n"
    else:
        answer = f"Aucun document trouvé pour '{q}'."

    return {
        "answer": answer,
        "sources": sources,
        "query": q,
        "results_count": len(results)
    }

# Investigation - GET endpoint with SSE streaming
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
        "UPDATE auto_sessions SET status = 'stopped', stopped_at = NOW() WHERE conversation_id = %s AND status = 'running'",
        (conversation_id,)
    )
    return {"status": "stopped"}

@router.get("/api/auto/status")
async def auto_status(conversation_id: str):
    """Get auto-investigation status"""
    sessions = execute_query(
        "sessions",
        "SELECT * FROM auto_sessions WHERE conversation_id = %s ORDER BY started_at DESC LIMIT 1",
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
        "INSERT INTO conversations (id, title) VALUES (%s, %s)",
        (conv_id, title)
    )
    return {"id": conv_id, "title": title}

@router.get("/api/conversations/{conv_id}/messages")
async def get_messages(conv_id: str):
    """Get messages for conversation"""
    return execute_query(
        "sessions",
        "SELECT * FROM messages WHERE conversation_id = %s ORDER BY created_at ASC",
        (conv_id,)
    )

@router.delete("/api/conversations/{conv_id}")
async def delete_conversation(conv_id: str):
    """Delete a conversation and all its messages"""
    # Delete messages first (foreign key)
    execute_update("sessions", "DELETE FROM messages WHERE conversation_id = %s", (conv_id,))
    # Delete auto sessions
    execute_update("sessions", "DELETE FROM auto_sessions WHERE conversation_id = %s", (conv_id,))
    # Delete conversation
    deleted = execute_update("sessions", "DELETE FROM conversations WHERE id = %s", (conv_id,))
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "deleted", "id": conv_id}

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
            "INSERT INTO settings (key, value, updated_at) VALUES (%s, %s, NOW()) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()",
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
        "INSERT INTO settings (key, value, updated_at) VALUES ('language', %s, NOW()) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()",
        (request.language,)
    )
    return {"status": "updated", "language": request.language}


# Sources metadata
@router.get("/api/sources")
async def get_sources():
    """Get data source metadata"""
    sources = execute_query(
        "l_data",
        """SELECT id, source_name, source_type, origin, how_obtained,
                  date_obtained, original_format, file_count, total_size_mb,
                  date_range_start, date_range_end, notes, created_at
           FROM source_metadata
           ORDER BY date_obtained""",
        ()
    )
    # Convert dates for JSON
    for s in sources:
        for k in ['date_obtained', 'date_range_start', 'date_range_end', 'created_at']:
            if s.get(k):
                s[k] = str(s[k])
    return sources


# Ingest
@router.get("/api/ingest")
async def ingest_files(source: str = "inbox_upload"):
    """Ingest files from inbox with SSE progress"""
    from scripts.ingest import ingest_with_progress

    async def event_generator():
        async for event in ingest_with_progress(source):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

@router.get("/api/ingest/status")
async def ingest_status():
    """Get inbox status"""
    inbox = DATA_DIR / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)

    txt_files = list(inbox.rglob('*.txt'))
    eml_files = list(inbox.rglob('*.eml'))

    return {
        "pending": len(txt_files) + len(eml_files),
        "txt_files": len(txt_files),
        "eml_files": len(eml_files),
        "inbox_path": str(inbox)
    }


# Timeline
@router.get("/api/timeline")
async def get_timeline(person: Optional[str] = None):
    """Get case timeline events"""
    if person:
        events = execute_query(
            "l_data",
            """SELECT id, event_date, event_type, event_title, event_description,
                      jurisdiction, case_number, people_involved, verified
               FROM case_timeline
               WHERE people_involved::text ILIKE %s
               ORDER BY event_date""",
            (f'%{person}%',)
        )
    else:
        events = execute_query(
            "l_data",
            """SELECT id, event_date, event_type, event_title, event_description,
                      jurisdiction, case_number, people_involved, verified
               FROM case_timeline
               ORDER BY event_date""",
            ()
        )

    # Convert dates to strings for JSON
    for e in events:
        if e.get('event_date'):
            e['event_date'] = str(e['event_date'])
        if e.get('people_involved'):
            # Already JSONB, should be a list
            pass

    return events


# Parallel extraction endpoint
@router.post("/api/extract")
async def extract_entities(text: str, query: str = "", entity_types: Optional[str] = None, insert_db: bool = False):
    """
    Parallel Phi-3 extraction with Haiku validation.

    Architecture:
        [Doc batch]
              ↓
    ┌─────────────────────────────────────┐
    │  Phi3-A (dates)    → SQL dates      │
    │  Phi3-B (persons)  → SQL persons    │  parallel
    │  Phi3-C (orgs)     → SQL orgs       │
    │  Phi3-D (amounts)  → SQL amounts    │
    └─────────────────────────────────────┘
              ↓ merge results
    [Haiku] → validate, correct, structure → clean INSERT
    """
    from app.llm_client import parallel_extract_entities, insert_extracted_entities

    # Parse entity types if provided
    types_list = None
    if entity_types:
        types_list = [t.strip() for t in entity_types.split(",")]

    # Run parallel extraction
    result = await parallel_extract_entities(text, query, types_list)

    # Optionally insert into database
    if insert_db and "validated" in result:
        insert_counts = insert_extracted_entities(result["validated"])
        result["insert_counts"] = insert_counts

    return result


@router.get("/api/extract/stats")
async def extraction_stats():
    """Get parallel extraction worker stats"""
    try:
        from app.workers import worker_pool
        if worker_pool.workers:
            return {
                "status": "ready",
                "workers": worker_pool.stats(),
                "entity_types": ["dates", "persons", "orgs", "amounts", "locations"]
            }
        return {"status": "no_workers", "workers": None}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# =============================================================================
# PROSECUTION CASE BUILDER
# =============================================================================

@router.get("/api/prosecution/targets")
async def get_targets():
    """Get all prosecution targets with profiles"""
    from app.prosecution import get_prosecution_targets
    return get_prosecution_targets()


@router.get("/api/prosecution/targets/{target_id}")
async def get_target(target_id: str):
    """Get detailed profile for a prosecution target"""
    from app.prosecution import get_target_profile
    profile = get_target_profile(target_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Target not found")
    return profile


@router.get("/api/prosecution/targets/{target_id}/readiness")
async def get_readiness(target_id: str):
    """Calculate prosecution readiness for a target"""
    from app.prosecution import calculate_prosecution_readiness
    return calculate_prosecution_readiness(target_id)


@router.get("/api/prosecution/targets/{target_id}/evidence")
async def get_evidence(target_id: str):
    """Get evidence chain for a target"""
    from app.prosecution import get_evidence_chain
    chain = get_evidence_chain(target_id)
    if not chain:
        raise HTTPException(status_code=404, detail="Target not found")
    return chain


@router.get("/api/prosecution/timeline")
async def get_prosecution_timeline(category: str = None, target: str = None):
    """Get investigation timeline"""
    from app.prosecution import get_timeline as prosecution_timeline
    return prosecution_timeline(category, target)


@router.get("/api/prosecution/summary")
async def get_summary():
    """Get overall prosecution readiness summary"""
    from app.prosecution import get_prosecution_summary
    return get_prosecution_summary()

@router.put("/api/prosecution/targets/{target_id}/flag")
async def update_target_flag(target_id: str, flag: int = Query(..., ge=-2, le=12), reason: str = Query(None)):
    """Update guilt flag for a target (-2 to 12). Admin only."""
    from app.prosecution import update_guilt_flag
    result = update_guilt_flag(target_id, flag, reason)
    if not result:
        raise HTTPException(status_code=404, detail="Target not found")
    return result

@router.get("/api/prosecution/flags")
async def get_all_flags():
    """Get guilt flags for all targets"""
    from app.prosecution import get_prosecution_targets, get_flag_label
    targets = get_prosecution_targets()
    return {
        'scale': {
            '-2': 'CLEARED',
            '-1': 'LIKELY VICTIM',
            '0': 'NO EVIDENCE',
            '1-2': 'ASSOCIATION ONLY',
            '3-4': 'SUSPICIOUS',
            '5-6': 'CREDIBLE ACCUSATIONS',
            '7-8': 'LIKELY GUILTY',
            '9-10': 'SHOULD BE PROSECUTED',
            '11-12': 'CONVICTED'
        },
        'targets': [
            {
                'id': t['id'],
                'name': t['name'],
                'guilt_flag': t['guilt_flag'],
                'flag_label': t['flag_label'],
                'flag_reason': t['flag_reason'],
                'confidence': t['confidence']
            }
            for t in targets
        ]
    }

@router.get("/api/prosecution/export/{target_id}")
async def export_dossier(target_id: str):
    """Export prosecution dossier for a target as JSON"""
    from app.prosecution import (
        get_target_profile, calculate_prosecution_readiness,
        get_evidence_chain, get_timeline
    )

    profile = get_target_profile(target_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Target not found")

    readiness = calculate_prosecution_readiness(target_id)
    evidence = get_evidence_chain(target_id)
    timeline = get_timeline(target=target_id)

    dossier = {
        "generated_at": datetime.utcnow().isoformat(),
        "target": profile,
        "readiness": readiness,
        "evidence_chain": evidence,
        "timeline": timeline,
        "disclaimer": "This dossier is for investigative purposes only. All claims require independent verification."
    }

    return dossier

@router.get("/api/prosecution/export")
async def export_all_dossiers():
    """Export all prosecution dossiers as JSON"""
    from app.prosecution import (
        get_prosecution_targets, get_target_profile,
        calculate_prosecution_readiness, get_timeline, get_prosecution_summary
    )

    summary = get_prosecution_summary()
    targets = get_prosecution_targets()
    timeline = get_timeline()

    dossiers = []
    for t in targets:
        profile = get_target_profile(t['id'])
        readiness = calculate_prosecution_readiness(t['id'])
        dossiers.append({
            "target": profile,
            "readiness": readiness
        })

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "summary": summary,
        "investigation_timeline": timeline,
        "targets": dossiers,
        "disclaimer": "This report is for investigative purposes only. All claims require independent verification."
    }
