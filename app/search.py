"""Full-text search functions"""
from typing import List, Dict, Any
from app.db import execute_query
from app.models import SearchResult

def search_emails(q: str, limit: int = 20) -> List[SearchResult]:
    """Search emails using PostgreSQL full-text search"""
    if not q.strip():
        return []

    query = """
        SELECT
            doc_id,
            subject,
            sender_email as sender,
            ts_headline('english', COALESCE(body_text, subject), plainto_tsquery('english', %s),
                'StartSel=<mark>, StopSel=</mark>, MaxWords=30, MinWords=10') as snippet,
            ts_rank(tsv, plainto_tsquery('english', %s)) as rank
        FROM emails
        WHERE tsv @@ plainto_tsquery('english', %s)
        ORDER BY rank DESC
        LIMIT %s
    """

    rows = execute_query("sources", query, (q, q, q, limit))

    results = []
    for row in rows:
        results.append(SearchResult(
            id=row['doc_id'],
            type='email',
            name=row['subject'] or '(no subject)',
            snippet=row.get('snippet', ''),
            score=float(row.get('rank', 0))
        ))

    return results

def search_nodes(q: str, limit: int = 20) -> List[SearchResult]:
    """Search nodes using trigram similarity"""
    if not q.strip():
        return []

    query = """
        SELECT
            id,
            type,
            name,
            name as snippet,
            GREATEST(
                similarity(name, %s),
                similarity(COALESCE(name_normalized, ''), %s)
            ) as rank
        FROM nodes
        WHERE name ILIKE %s
           OR name_normalized ILIKE %s
           OR similarity(name, %s) > 0.3
        ORDER BY rank DESC
        LIMIT %s
    """

    search_pattern = f"%{q}%"
    rows = execute_query("graph", query, (q, q, search_pattern, search_pattern, q, limit))

    results = []
    for row in rows:
        results.append(SearchResult(
            id=row['id'],
            type=row['type'],
            name=row['name'],
            snippet=row.get('snippet', ''),
            score=float(row.get('rank', 0))
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
