"""Clean API routes for pwnd.icu v2
Simple, fast, no complex LLM dependencies.
"""
import json
import logging
import re
import uuid
import asyncio
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.db import execute_query, execute_insert, execute_update, get_db
import psycopg2.extras

log = logging.getLogger(__name__)
router = APIRouter()

# ============================================================================
# CHAT MODELS
# ============================================================================

class ChatMessage(BaseModel):
    message: str
    conversation_id: Optional[str] = None

# ============================================================================
# STATS
# ============================================================================

@router.get("/api/v2/stats")
async def stats():
    """System statistics"""
    nodes = execute_query("graph", "SELECT COUNT(*) as c FROM nodes")[0]["c"]
    edges = execute_query("graph", "SELECT COUNT(*) as c FROM edges")[0]["c"]
    emails = execute_query("sources", "SELECT COUNT(*) as c FROM emails")[0]["c"]
    docs = execute_query("sources", "SELECT COUNT(*) as c FROM documents")[0]["c"]
    chunks = execute_query("sources", "SELECT COUNT(*) as c FROM chunks")[0]["c"]

    return {
        "emails": emails,
        "documents": docs,
        "chunks": chunks,
        "nodes": nodes,
        "edges": edges,
        "llm": {"status": "disabled", "reason": "CPU inference too slow"},
        "status": "ok"
    }

# ============================================================================
# SEARCH - Simple, fast, reliable
# ============================================================================

STOP_WORDS = frozenset({
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'what', 'about', 'who',
    'how', 'why', 'when', 'where', 'do', 'does', 'did', 'have', 'has', 'had',
    'be', 'been', 'being', 'and', 'or', 'but', 'if', 'then', 'of', 'to',
    'for', 'with', 'on', 'at', 'by', 'from', 'in', 'out', 'up', 'down',
    'this', 'that', 'these', 'those', 'it', 'its', 'les', 'des', 'une', 'un',
    'est', 'sont', 'qui', 'que', 'dans', 'pour', 'sur', 'avec', 'par'
})

def extract_keywords(query: str) -> List[str]:
    """Extract meaningful keywords"""
    words = re.findall(r'\b[a-zA-Z]{2,}\b', query.lower())
    keywords = [w for w in words if w not in STOP_WORDS]
    return keywords[:5] if keywords else words[:3]

@router.get("/api/v2/search")
async def search(q: str = Query(..., max_length=500), limit: int = Query(20, ge=1, le=100)):
    """Universal search - emails + documents + nodes"""
    keywords = extract_keywords(q)
    if not keywords:
        return []

    results = []

    # 1. Search emails (FTS) - prioritize these
    try:
        ts_query = " | ".join(keywords)
        email_results = execute_query("sources", """
            SELECT doc_id as id, subject as title,
                   LEFT(body_text, 500) as snippet,
                   ts_rank(tsv, plainto_tsquery('english', %s)) as score
            FROM emails
            WHERE tsv @@ plainto_tsquery('english', %s)
            ORDER BY score DESC
            LIMIT %s
        """, (q, q, limit))

        for r in email_results:
            results.append({
                "id": r["id"],
                "type": "email",
                "title": r["title"] or "Email",
                "snippet": r["snippet"] or "",
                "score": float(r["score"] or 0)
            })
    except Exception as e:
        log.warning(f"Email search failed: {e}")

    # 2. Search documents via chunks
    try:
        like_pattern = f"%{keywords[0]}%"
        doc_results = execute_query("sources", """
            SELECT DISTINCT d.id, d.filename as title,
                   LEFT(c.content, 300) as snippet
            FROM documents d
            JOIN chunks c ON c.doc_id = d.id
            WHERE c.content ILIKE %s
            LIMIT %s
        """, (like_pattern, limit // 2))

        for r in doc_results:
            results.append({
                "id": r["id"],
                "type": "document",
                "title": r["title"] or "Document",
                "snippet": r["snippet"] or "",
                "score": 0.5
            })
    except Exception as e:
        log.warning(f"Document search failed: {e}")

    # 3. Search nodes (graph) - get related entities
    try:
        node_results = execute_query("graph", """
            SELECT id, name as title, type,
                   similarity(name_normalized, %s) as score
            FROM nodes
            WHERE name_normalized ILIKE %s OR name ILIKE %s
            ORDER BY score DESC
            LIMIT %s
        """, (keywords[0], f"%{keywords[0]}%", f"%{keywords[0]}%", 20))

        for r in node_results:
            results.append({
                "id": r["id"],
                "type": r["type"] or "entity",
                "title": r["title"],
                "snippet": f"Type: {r['type']}",
                "score": float(r["score"] or 0)
            })
    except Exception as e:
        log.warning(f"Node search failed: {e}")

    # Sort by score
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]

# ============================================================================
# EMAIL VIEWER
# ============================================================================

@router.get("/api/v2/email/{doc_id}")
async def get_email(doc_id: int):
    """Get full email"""
    rows = execute_query("sources", """
        SELECT doc_id, subject, body_text, sender_email, sender_name,
               recipients_to, recipients_cc, date_sent
        FROM emails WHERE doc_id = %s
    """, (doc_id,))

    if not rows:
        raise HTTPException(status_code=404, detail="Email not found")

    r = rows[0]
    return {
        "id": r["doc_id"],
        "subject": r["subject"],
        "body": r["body_text"],
        "sender": r["sender_email"],
        "sender_name": r["sender_name"],
        "to": r["recipients_to"],
        "cc": r["recipients_cc"],
        "date": str(r["date_sent"]) if r["date_sent"] else None
    }

# ============================================================================
# DOCUMENT VIEWER
# ============================================================================

@router.get("/api/v2/document/{doc_id}")
async def get_document(doc_id: int):
    """Get full document with chunks"""
    doc = execute_query("sources", """
        SELECT id, filename, filepath, doc_type, origin, page_count, status
        FROM documents WHERE id = %s
    """, (doc_id,))

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    chunks = execute_query("sources", """
        SELECT chunk_index, content FROM chunks
        WHERE doc_id = %s ORDER BY chunk_index
    """, (doc_id,))

    d = doc[0]
    return {
        "id": d["id"],
        "filename": d["filename"],
        "type": d["doc_type"],
        "origin": d["origin"],
        "pages": d["page_count"],
        "status": d["status"],
        "content": "\n\n".join([c["content"] for c in chunks])
    }

# ============================================================================
# GRAPH - Nodes & Edges
# ============================================================================

@router.get("/api/v2/nodes")
async def get_nodes(type: Optional[str] = None, limit: int = Query(50, ge=1, le=500)):
    """Get nodes with confidence scores"""
    if type:
        query = """
            SELECT n.id, n.name, n.type, n.source_db,
                   nc.relevance_score, nc.confidence_score
            FROM nodes n
            LEFT JOIN node_confidence nc ON n.id = nc.node_id
            WHERE n.type = %s
            ORDER BY nc.relevance_score DESC NULLS LAST
            LIMIT %s
        """
        return execute_query("graph", query, (type, limit))
    else:
        query = """
            SELECT n.id, n.name, n.type, n.source_db,
                   nc.relevance_score, nc.confidence_score
            FROM nodes n
            LEFT JOIN node_confidence nc ON n.id = nc.node_id
            ORDER BY nc.relevance_score DESC NULLS LAST
            LIMIT %s
        """
        return execute_query("graph", query, (limit,))

@router.get("/api/v2/nodes/{node_id}")
async def get_node(node_id: int):
    """Get node with edges"""
    node = execute_query("graph", """
        SELECT n.*, nc.relevance_score, nc.confidence_score, nc.factors
        FROM nodes n
        LEFT JOIN node_confidence nc ON n.id = nc.node_id
        WHERE n.id = %s
    """, (node_id,))

    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    edges = execute_query("graph", """
        SELECT e.id, e.type, e.excerpt,
               n1.name as from_name, n1.type as from_type,
               n2.name as to_name, n2.type as to_type
        FROM edges e
        JOIN nodes n1 ON e.from_node_id = n1.id
        JOIN nodes n2 ON e.to_node_id = n2.id
        WHERE e.from_node_id = %s OR e.to_node_id = %s
        LIMIT 100
    """, (node_id, node_id))

    return {
        "node": node[0],
        "edges": edges
    }

@router.get("/api/v2/edges")
async def get_edges(type: Optional[str] = None, limit: int = Query(50, ge=1, le=500)):
    """Get edges"""
    if type:
        return execute_query("graph", """
            SELECT e.id, e.type, e.excerpt,
                   n1.name as from_name, n2.name as to_name
            FROM edges e
            JOIN nodes n1 ON e.from_node_id = n1.id
            JOIN nodes n2 ON e.to_node_id = n2.id
            WHERE e.type = %s
            LIMIT %s
        """, (type, limit))
    else:
        return execute_query("graph", """
            SELECT e.id, e.type, e.excerpt,
                   n1.name as from_name, n2.name as to_name
            FROM edges e
            JOIN nodes n1 ON e.from_node_id = n1.id
            JOIN nodes n2 ON e.to_node_id = n2.id
            LIMIT %s
        """, (limit,))

@router.get("/api/v2/graph/edge-types")
async def get_edge_types():
    """Get all available edge types with counts"""
    types = execute_query("graph", """
        SELECT type, COUNT(*) as count
        FROM edges
        WHERE type IS NOT NULL AND type != ''
        GROUP BY type
        ORDER BY count DESC
    """)
    return types

@router.get("/api/v2/graph/timeline")
async def get_timeline(
    subject: Optional[str] = Query(None, description="Filter by subject (e.g., 'Epstein')"),
    limit: int = Query(100, ge=10, le=500)
):
    """Get timeline events for visualization"""
    import re

    # Key Epstein case events with known dates
    key_events = [
        {"id": "evt_1", "date": "2005-03-01", "title": "Palm Beach Investigation Begins", "type": "investigation", "description": "Palm Beach Police begin investigating Epstein after mother's complaint"},
        {"id": "evt_2", "date": "2006-05-01", "title": "FBI Investigation", "type": "investigation", "description": "FBI opens federal investigation"},
        {"id": "evt_3", "date": "2006-07-01", "title": "Grand Jury Indictment", "type": "legal", "description": "State grand jury indicts Epstein on one count"},
        {"id": "evt_4", "date": "2007-06-30", "title": "NPA Signed", "type": "legal", "description": "Non-Prosecution Agreement signed with federal prosecutors"},
        {"id": "evt_5", "date": "2008-06-30", "title": "State Plea Deal", "type": "legal", "description": "Epstein pleads guilty to state charges, 18-month sentence"},
        {"id": "evt_6", "date": "2008-07-01", "title": "Prison Sentence Begins", "type": "legal", "description": "Begins serving sentence at Palm Beach County Stockade"},
        {"id": "evt_7", "date": "2009-07-22", "title": "Prison Release", "type": "legal", "description": "Released after 13 months with work release"},
        {"id": "evt_8", "date": "2010-01-01", "title": "Sex Offender Registration", "type": "legal", "description": "Required to register as Level 3 sex offender"},
        {"id": "evt_9", "date": "2015-01-01", "title": "Virginia Giuffre Lawsuit", "type": "legal", "description": "Giuffre files lawsuit naming prominent figures"},
        {"id": "evt_10", "date": "2018-11-28", "title": "Miami Herald Investigation", "type": "media", "description": "\"Perversion of Justice\" series published"},
        {"id": "evt_11", "date": "2019-07-06", "title": "Arrest at Teterboro", "type": "arrest", "description": "Arrested by FBI-NYPD task force at Teterboro Airport"},
        {"id": "evt_12", "date": "2019-07-08", "title": "SDNY Indictment", "type": "legal", "description": "Indicted on sex trafficking charges by SDNY"},
        {"id": "evt_13", "date": "2019-07-18", "title": "Bail Denied", "type": "legal", "description": "Judge denies bail, deemed flight risk"},
        {"id": "evt_14", "date": "2019-07-23", "title": "First Incident", "type": "incident", "description": "Found injured in cell with marks on neck"},
        {"id": "evt_15", "date": "2019-07-24", "title": "Suicide Watch", "type": "custody", "description": "Placed on suicide watch at MCC"},
        {"id": "evt_16", "date": "2019-07-29", "title": "Off Suicide Watch", "type": "custody", "description": "Removed from suicide watch after 6 days"},
        {"id": "evt_17", "date": "2019-08-08", "title": "Document Dump", "type": "legal", "description": "2,000 pages of Giuffre v. Maxwell documents unsealed"},
        {"id": "evt_18", "date": "2019-08-10", "title": "Death at MCC", "type": "death", "description": "Found dead in cell at 6:30 AM"},
        {"id": "evt_19", "date": "2019-08-11", "title": "Autopsy Performed", "type": "investigation", "description": "NYC Medical Examiner performs autopsy"},
        {"id": "evt_20", "date": "2019-08-16", "title": "Suicide Ruling", "type": "investigation", "description": "Death ruled suicide by hanging"},
        {"id": "evt_21", "date": "2019-11-19", "title": "Guards Indicted", "type": "legal", "description": "MCC guards Noel and Thomas indicted for falsifying records"},
        {"id": "evt_22", "date": "2020-07-02", "title": "Maxwell Arrested", "type": "arrest", "description": "Ghislaine Maxwell arrested in New Hampshire"},
        {"id": "evt_23", "date": "2020-12-17", "title": "Brunel Arrested", "type": "arrest", "description": "Jean-Luc Brunel arrested in Paris"},
        {"id": "evt_24", "date": "2021-11-29", "title": "Maxwell Trial Begins", "type": "legal", "description": "Federal trial begins in SDNY"},
        {"id": "evt_25", "date": "2021-12-29", "title": "Maxwell Verdict", "type": "legal", "description": "Guilty on 5 of 6 counts"},
        {"id": "evt_26", "date": "2022-02-19", "title": "Brunel Death", "type": "death", "description": "Jean-Luc Brunel found dead in Paris prison"},
        {"id": "evt_27", "date": "2022-02-21", "title": "Prince Andrew Settlement", "type": "legal", "description": "Prince Andrew settles with Virginia Giuffre"},
        {"id": "evt_28", "date": "2022-06-28", "title": "Maxwell Sentenced", "type": "legal", "description": "Sentenced to 20 years in federal prison"},
        {"id": "evt_29", "date": "2023-06-05", "title": "JPMorgan Settlement", "type": "legal", "description": "JPMorgan settles with victims for $290M"},
        {"id": "evt_30", "date": "2023-07-12", "title": "Deutsche Bank Settlement", "type": "legal", "description": "Deutsche Bank settles for $75M"},
    ]

    # Also get events from database
    db_events = execute_query("graph", """
        SELECT n.id, n.name, n.type,
               COALESCE(nc.total_connections, 0) as connections
        FROM nodes n
        LEFT JOIN node_confidence nc ON n.id = nc.node_id
        WHERE n.type = 'event'
          AND (n.name ~ '^[0-9]{4}' OR n.name ~ '[0-9]{4}')
        ORDER BY n.name
        LIMIT %s
    """, (limit,))

    # Parse dates from event names
    def parse_date(name):
        # Try to extract year from name
        match = re.search(r'(20[0-2][0-9]|19[0-9]{2})', name)
        if match:
            year = match.group(1)
            # Try to find month
            months = {'january': '01', 'february': '02', 'march': '03', 'april': '04',
                     'may': '05', 'june': '06', 'july': '07', 'august': '08',
                     'september': '09', 'october': '10', 'november': '11', 'december': '12',
                     'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04', 'jun': '06',
                     'jul': '07', 'aug': '08', 'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'}
            name_lower = name.lower()
            month = '06'  # Default to mid-year
            day = '15'
            for m, num in months.items():
                if m in name_lower:
                    month = num
                    break
            # Try to find day
            day_match = re.search(r'\b([0-3]?[0-9])\b', name)
            if day_match and 1 <= int(day_match.group(1)) <= 31:
                day = day_match.group(1).zfill(2)
            return f"{year}-{month}-{day}"
        return None

    # Convert db events to timeline format
    timeline_events = []
    for evt in db_events:
        date = parse_date(evt['name'])
        if date:
            # Determine event category
            name_lower = evt['name'].lower()
            if any(w in name_lower for w in ['arrest', 'indictment', 'trial', 'plea', 'sentence', 'verdict']):
                evt_type = 'legal'
            elif any(w in name_lower for w in ['death', 'died', 'suicide']):
                evt_type = 'death'
            elif any(w in name_lower for w in ['investigation', 'fbi', 'police']):
                evt_type = 'investigation'
            else:
                evt_type = 'event'

            timeline_events.append({
                "id": f"db_{evt['id']}",
                "date": date,
                "title": evt['name'],
                "type": evt_type,
                "connections": evt['connections'],
                "description": f"Database event with {evt['connections']} connections"
            })

    # Combine key events with db events, sort by date
    all_events = key_events + timeline_events
    all_events.sort(key=lambda x: x['date'])

    # Filter by subject if provided
    if subject:
        subject_lower = subject.lower()
        # Key events are all Epstein-related
        if 'epstein' in subject_lower or 'maxwell' in subject_lower:
            pass  # Keep all key_events
        else:
            all_events = [e for e in timeline_events if subject_lower in e.get('title', '').lower()]

    return {
        "events": all_events,
        "total": len(all_events),
        "range": {
            "start": all_events[0]['date'] if all_events else None,
            "end": all_events[-1]['date'] if all_events else None
        }
    }

@router.get("/api/v2/graph/network")
async def get_network(
    center: Optional[str] = None,
    depth: int = Query(2, ge=1, le=3),
    limit: int = Query(100, ge=10, le=300),
    edge_types: Optional[str] = Query(None, description="Comma-separated edge types to filter")
):
    """Get network data for visualization (vis-network format)"""

    # Parse edge type filter
    type_filter = None
    if edge_types:
        type_filter = [t.strip() for t in edge_types.split(',') if t.strip()]

    if center:
        # Get centered on specific node
        center_node = execute_query("graph", """
            SELECT n.id, n.name, n.type, nc.centrality_score, nc.total_connections
            FROM nodes n
            LEFT JOIN node_confidence nc ON n.id = nc.node_id
            WHERE LOWER(n.name) = LOWER(%s)
            ORDER BY nc.centrality_score DESC NULLS LAST
            LIMIT 1
        """, (center,))

        if not center_node:
            # Search by partial match
            center_node = execute_query("graph", """
                SELECT n.id, n.name, n.type, nc.centrality_score, nc.total_connections
                FROM nodes n
                LEFT JOIN node_confidence nc ON n.id = nc.node_id
                WHERE LOWER(n.name) LIKE LOWER(%s)
                ORDER BY nc.centrality_score DESC NULLS LAST
                LIMIT 1
            """, (f"%{center}%",))

        if not center_node:
            raise HTTPException(status_code=404, detail="Node not found")

        center_id = center_node[0]['id']

        # Get connected nodes (depth 1) - with optional type filter
        if type_filter:
            connected = execute_query("graph", """
                SELECT DISTINCT
                    CASE WHEN e.from_node_id = %s THEN e.to_node_id ELSE e.from_node_id END as node_id
                FROM edges e
                WHERE (e.from_node_id = %s OR e.to_node_id = %s)
                  AND e.type = ANY(%s)
            """, (center_id, center_id, center_id, type_filter))
        else:
            connected = execute_query("graph", """
                SELECT DISTINCT
                    CASE WHEN e.from_node_id = %s THEN e.to_node_id ELSE e.from_node_id END as node_id
                FROM edges e
                WHERE e.from_node_id = %s OR e.to_node_id = %s
            """, (center_id, center_id, center_id))

        node_ids = [center_id] + [c['node_id'] for c in connected]

        # Get depth 2 if requested
        if depth >= 2 and len(node_ids) < limit:
            if type_filter:
                depth2 = execute_query("graph", """
                    SELECT DISTINCT
                        CASE WHEN e.from_node_id = ANY(%s) THEN e.to_node_id ELSE e.from_node_id END as node_id
                    FROM edges e
                    WHERE (e.from_node_id = ANY(%s) OR e.to_node_id = ANY(%s))
                      AND e.type = ANY(%s)
                """, (node_ids, node_ids, node_ids, type_filter))
            else:
                depth2 = execute_query("graph", """
                    SELECT DISTINCT
                        CASE WHEN e.from_node_id = ANY(%s) THEN e.to_node_id ELSE e.from_node_id END as node_id
                    FROM edges e
                    WHERE e.from_node_id = ANY(%s) OR e.to_node_id = ANY(%s)
                """, (node_ids, node_ids, node_ids))
            node_ids = list(set(node_ids + [d['node_id'] for d in depth2]))[:limit]

    else:
        # Get top nodes by centrality
        top_nodes = execute_query("graph", """
            SELECT n.id
            FROM nodes n
            JOIN node_confidence nc ON n.id = nc.node_id
            WHERE n.type = 'person'
            ORDER BY nc.centrality_score DESC NULLS LAST
            LIMIT %s
        """, (limit // 2,))
        node_ids = [n['id'] for n in top_nodes]

    if not node_ids:
        return {"nodes": [], "edges": []}

    # Get node details
    nodes_data = execute_query("graph", """
        SELECT n.id, n.name, n.type,
               COALESCE(nc.centrality_score, 0) as centrality,
               COALESCE(nc.total_connections, 0) as connections,
               COALESCE(nc.relevance_score, 0) as relevance
        FROM nodes n
        LEFT JOIN node_confidence nc ON n.id = nc.node_id
        WHERE n.id = ANY(%s)
    """, (node_ids,))

    # Get edges between these nodes - with optional type filter
    if type_filter:
        edges_data = execute_query("graph", """
            SELECT e.id, e.from_node_id, e.to_node_id, e.type, e.excerpt
            FROM edges e
            WHERE e.from_node_id = ANY(%s) AND e.to_node_id = ANY(%s)
              AND e.type = ANY(%s)
            LIMIT 500
        """, (node_ids, node_ids, type_filter))
    else:
        edges_data = execute_query("graph", """
            SELECT e.id, e.from_node_id, e.to_node_id, e.type, e.excerpt
            FROM edges e
            WHERE e.from_node_id = ANY(%s) AND e.to_node_id = ANY(%s)
            LIMIT 500
        """, (node_ids, node_ids))

    # Color mapping for node types
    type_colors = {
        'person': '#ef4444',      # red
        'organization': '#3b82f6', # blue
        'company': '#22c55e',      # green
        'location': '#f59e0b',     # orange
        'email': '#8b5cf6',        # purple
        'email_address': '#8b5cf6',
        'unknown': '#6b7280',      # gray
    }

    # Format for vis-network
    vis_nodes = []
    for n in nodes_data:
        size = 10 + min(40, (n['centrality'] or 0) * 50)
        vis_nodes.append({
            "id": n['id'],
            "label": n['name'][:25] + ('...' if len(n['name']) > 25 else ''),
            "title": f"{n['name']}\nType: {n['type']}\nConnections: {n['connections']}\nRelevance: {n['relevance']:.2f}",
            "group": n['type'],
            "color": type_colors.get(n['type'], '#6b7280'),
            "size": size,
            "font": {"size": 10 + min(6, (n['centrality'] or 0) * 10)}
        })

    vis_edges = []
    for e in edges_data:
        vis_edges.append({
            "from": e['from_node_id'],
            "to": e['to_node_id'],
            "label": e['type'][:15] if e['type'] else '',
            "title": e['excerpt'] or e['type'],
            "arrows": "to",
            "color": {"color": "#404040", "highlight": "#3b82f6"}
        })

    return {
        "nodes": vis_nodes,
        "edges": vis_edges
    }

# ============================================================================
# ASK - Simple RAG without LLM dependency
# ============================================================================

@router.get("/api/v2/ask")
async def ask(q: str = Query(..., max_length=1000)):
    """RAG query - search + format results (no LLM required)"""

    async def generate():
        yield f'data: {json.dumps({"type": "status", "msg": "Searching..."})}\n\n'

        # Search
        results = await search(q, limit=20)

        yield f'data: {json.dumps({"type": "status", "msg": f"Found {len(results)} results"})}\n\n'

        if not results:
            yield f'data: {json.dumps({"type": "chunk", "text": "No results found."})}\n\n'
            yield f'data: {json.dumps({"type": "done", "sources": []})}\n\n'
            return

        # Format results as markdown
        text = f"## Results for: {q}\n\n"
        sources = []

        for i, r in enumerate(results[:10], 1):
            title = r["title"][:60] if r["title"] else "Untitled"
            snippet = r["snippet"][:200] if r["snippet"] else ""
            rtype = r["type"]

            text += f"**{i}. [{rtype.upper()}] {title}**\n"
            text += f"{snippet}...\n\n"
            sources.append(r["id"])

        yield f'data: {json.dumps({"type": "chunk", "text": text})}\n\n'
        yield f'data: {json.dumps({"type": "sources", "ids": sources})}\n\n'
        yield f'data: {json.dumps({"type": "done", "sources": sources})}\n\n'

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )

# ============================================================================
# PROSECUTION TARGETS
# ============================================================================

@router.get("/api/v2/targets")
async def get_targets():
    """Get prosecution targets from graph"""
    targets = execute_query("graph", """
        SELECT n.id, n.name, n.type,
               nc.relevance_score, nc.confidence_score,
               nc.total_connections, nc.centrality_score,
               nc.corroboration_score
        FROM nodes n
        JOIN node_confidence nc ON n.id = nc.node_id
        WHERE n.type = 'person'
          AND nc.relevance_score > 0.3
        ORDER BY nc.relevance_score DESC
        LIMIT 50
    """)

    result = []
    for t in targets:
        result.append({
            "id": t["id"],
            "name": t["name"],
            "relevance": round(t["relevance_score"], 3),
            "confidence": round(t["confidence_score"], 3),
            "connections": t["total_connections"] or 0,
            "centrality": round(t["centrality_score"] or 0, 3),
            "corroboration": round(t["corroboration_score"] or 0, 3)
        })

    return result

# ============================================================================
# CHAT - Conversational AI with RAG
# ============================================================================

@router.get("/api/v2/chat/conversations")
async def get_conversations():
    """List all conversations"""
    return execute_query("sessions", """
        SELECT id, title, created_at, updated_at
        FROM conversations
        ORDER BY updated_at DESC
        LIMIT 50
    """)

@router.post("/api/v2/chat/new")
async def new_conversation():
    """Create new conversation"""
    conv_id = str(uuid.uuid4())
    execute_update("sessions", """
        INSERT INTO conversations (id, title) VALUES (%s, %s)
    """, (conv_id, "New Chat"))
    return {"id": conv_id}

@router.get("/api/v2/chat/{conv_id}/messages")
async def get_messages(conv_id: str):
    """Get messages for a conversation"""
    return execute_query("sessions", """
        SELECT id, role, content, created_at
        FROM messages
        WHERE conversation_id = %s
        ORDER BY created_at ASC
    """, (conv_id,))

@router.post("/api/v2/chat/send")
async def chat_send(msg: ChatMessage):
    """Send message and get AI response with streaming"""
    conv_id = msg.conversation_id

    # Create conversation if needed
    if not conv_id:
        conv_id = str(uuid.uuid4())
        execute_update("sessions", """
            INSERT INTO conversations (id, title) VALUES (%s, %s)
        """, (conv_id, msg.message[:50]))

    # Save user message
    execute_update("sessions", """
        INSERT INTO messages (conversation_id, role, content) VALUES (%s, %s, %s)
    """, (conv_id, "user", msg.message))

    async def generate():
        yield f'data: {json.dumps({"type": "conv_id", "id": conv_id})}\n\n'
        yield f'data: {json.dumps({"type": "status", "msg": "Searching documents..."})}\n\n'

        # Search for relevant documents
        search_results = await search(msg.message, limit=15)

        yield f'data: {json.dumps({"type": "status", "msg": f"Found {len(search_results)} documents"})}\n\n'

        # Build context from search results
        context_parts = []
        source_ids = []
        for r in search_results[:10]:
            source_ids.append(r["id"])
            title = r.get("title", "")[:100]
            snippet = r.get("snippet", "")[:500]
            context_parts.append(f"[{r['type'].upper()}] {title}\n{snippet}")

        context = "\n\n---\n\n".join(context_parts)

        # Format search results
        # Note: Phi-3 local inference too slow on CPU (~50s per response)
        # Using structured fallback for instant results
        yield f'data: {json.dumps({"type": "status", "msg": "Formatting results..."})}\n\n'
        response_text = format_search_response(msg.message, search_results)
        yield f'data: {json.dumps({"type": "chunk", "text": response_text})}\n\n'

        # Save assistant response
        execute_update("sessions", """
            INSERT INTO messages (conversation_id, role, content) VALUES (%s, %s, %s)
        """, (conv_id, "assistant", response_text))

        # Update conversation timestamp
        execute_update("sessions", """
            UPDATE conversations SET updated_at = NOW() WHERE id = %s
        """, (conv_id,))

        yield f'data: {json.dumps({"type": "sources", "ids": source_ids})}\n\n'
        yield f'data: {json.dumps({"type": "done", "conv_id": conv_id})}\n\n'

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )

def clean_snippet(text: str) -> str:
    """Clean HTML/CSS from snippet"""
    if not text:
        return ""
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Remove CSS blocks
    text = re.sub(r'\{[^}]+\}', '', text)
    text = re.sub(r'\*\s*\{[^}]+\}', '', text)
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\r\n|\r|\n', ' ', text)
    return text.strip()

def format_search_response(query: str, results: list) -> str:
    """Format search results as a readable response"""
    if not results:
        return f"Aucun document trouvé pour « {query} »."

    # Group by type
    emails = [r for r in results if r.get("type") == "email"]
    docs = [r for r in results if r.get("type") == "document"]
    persons = [r for r in results if r.get("type") == "person"]
    orgs = [r for r in results if r.get("type") == "organization"]
    events = [r for r in results if r.get("type") == "event"]
    locations = [r for r in results if r.get("type") == "location"]
    others = [r for r in results if r.get("type") not in ("email", "document", "person", "organization", "event", "location", "unknown")]

    response = f"## « {query} »\n\n"

    # Emails first - they have the most content
    if emails:
        response += "### 📧 Correspondance\n\n"
        for e in emails[:5]:
            title = clean_snippet(e.get("title", "Sans objet"))[:80]
            snippet = clean_snippet(e.get("snippet", ""))[:400]
            response += f"**{title}**\n"
            if snippet and len(snippet) > 20:
                response += f"> {snippet}\n\n"
            else:
                response += "\n"

    # Documents
    if docs:
        response += "### 📄 Documents\n\n"
        for d in docs[:4]:
            title = clean_snippet(d.get("title", "Document"))[:80]
            snippet = clean_snippet(d.get("snippet", ""))[:350]
            response += f"**{title}**\n"
            if snippet and len(snippet) > 20:
                response += f"> {snippet}\n\n"
            else:
                response += "\n"

    # Entities summary - always show when present
    # Combine persons and unknown types as people
    unknowns = [r for r in results if r.get("type") == "unknown"]
    all_persons = persons + unknowns

    entities_parts = []
    if all_persons:
        names = list(dict.fromkeys([p.get("title", "") for p in all_persons if p.get("title")]))
        if names:
            entities_parts.append(("👤 Personnes", names[:10]))
    if orgs:
        names = list(dict.fromkeys([o.get("title", "") for o in orgs if o.get("title")]))
        if names:
            entities_parts.append(("🏢 Organisations", names[:6]))
    if locations:
        names = list(dict.fromkeys([l.get("title", "") for l in locations if l.get("title")]))
        if names:
            entities_parts.append(("📍 Lieux", names[:6]))
    if events:
        names = list(dict.fromkeys([e.get("title", "") for e in events if e.get("title")]))
        if names:
            entities_parts.append(("📅 Événements", names[:6]))

    if entities_parts:
        response += "### 🔗 Entités liées\n\n"
        for label, names in entities_parts:
            response += f"**{label}**: " + ", ".join(names[:8])
            if len(names) > 8:
                response += f" *+{len(names)-8}*"
            response += "\n\n"

    # Count
    total_shown = len(emails[:5]) + len(docs[:4])
    if len(results) > total_shown + 5:
        response += f"---\n*{len(results)} résultats au total*"

    return response
