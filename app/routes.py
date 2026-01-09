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
import os

router = APIRouter()

# Hot reload version - changes when index.html is modified
@router.get("/api/version")
async def get_version():
    """Get frontend version for hot-reload"""
    try:
        stat = os.stat("/opt/rag/static/index.html")
        return {"v": int(stat.st_mtime)}
    except:
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

    # Worker stats if available
    worker_stats = None
    try:
        from app.workers import worker_pool
        if worker_pool.workers:
            worker_stats = worker_pool.stats()
    except:
        pass

    # Cache stats
    cache_stats = None
    try:
        from app.pipeline import _search_cache
        cache_stats = _search_cache.stats()
    except:
        pass

    return {
        "nodes": nodes_count,
        "edges": edges_count,
        "sources": emails_count,
        "databases": ["sources", "graph", "scores", "audit", "sessions"],
        "workers": worker_stats,
        "cache": cache_stats
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
    from pathlib import Path
    inbox = Path("/opt/rag/data/inbox")
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
