"""Full-text search functions with score integration"""
import sqlite3
from typing import List, Dict, Any
from pathlib import Path
from app.db import execute_query
from app.models import SearchResult

SCORES_DB = Path("/opt/rag/db/scores.db")

# =============================================================================
# SCORE LOOKUP
# =============================================================================

def get_scores(target_type: str, target_ids: List[int]) -> Dict[int, Dict[str, int]]:
    """Fetch scores from scores.db for given targets"""
    if not target_ids:
        return {}

    try:
        conn = sqlite3.connect(SCORES_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        placeholders = ','.join(['?'] * len(target_ids))
        cursor.execute(f"""
            SELECT target_id, suspicion, pertinence, confidence, anomaly
            FROM scores
            WHERE target_type = ? AND target_id IN ({placeholders})
        """, [target_type] + list(target_ids))

        scores = {}
        for row in cursor.fetchall():
            scores[row['target_id']] = {
                'suspicion': row['suspicion'] or 0,
                'pertinence': row['pertinence'] or 50,
                'confidence': row['confidence'] or 50,
                'anomaly': row['anomaly'] or 0
            }
        conn.close()
        return scores
    except Exception:
        return {}


def calculate_composite_score(ts_rank: float, scores: Dict[str, int]) -> float:
    """
    Calculate composite score:
    final = ts_rank * 0.4 + pertinence * 0.3 + suspicion * 0.2 + confidence * 0.1

    ts_rank is typically 0-1, scores are 0-100
    Normalize scores to 0-1 range for combination
    """
    pertinence = scores.get('pertinence', 50) / 100.0
    suspicion = scores.get('suspicion', 0) / 100.0
    confidence = scores.get('confidence', 50) / 100.0

    # Weight: relevance still matters most, but suspicious/pertinent content bubbles up
    composite = (
        ts_rank * 0.4 +
        pertinence * 0.3 +
        suspicion * 0.2 +
        confidence * 0.1
    )
    return composite


# =============================================================================
# SEARCH FUNCTIONS
# =============================================================================

def search_emails(q: str, limit: int = 20) -> List[SearchResult]:
    """Search emails using PostgreSQL FTS + score enhancement"""
    if not q.strip():
        return []

    # Fetch more results initially to allow re-ranking
    fetch_limit = min(limit * 3, 100)

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

    rows = execute_query("sources", query, (q, q, q, fetch_limit))
    if not rows:
        return []

    # Get scores for these emails
    doc_ids = [row['doc_id'] for row in rows]
    scores_map = get_scores('email', doc_ids)

    # Build results with composite scores
    results = []
    for row in rows:
        doc_id = row['doc_id']
        ts_rank = float(row.get('rank', 0))

        # Get scores (default if not found)
        entity_scores = scores_map.get(doc_id, {
            'suspicion': 0, 'pertinence': 50, 'confidence': 70, 'anomaly': 0
        })

        composite = calculate_composite_score(ts_rank, entity_scores)

        results.append(SearchResult(
            id=doc_id,
            type='email',
            name=row['subject'] or '(no subject)',
            snippet=row.get('snippet', ''),
            score=composite,
            metadata={
                'ts_rank': ts_rank,
                'suspicion': entity_scores['suspicion'],
                'pertinence': entity_scores['pertinence'],
                'anomaly': entity_scores['anomaly']
            }
        ))

    # Re-sort by composite score
    results.sort(key=lambda x: x.score, reverse=True)

    return results[:limit]


def search_nodes(q: str, limit: int = 20) -> List[SearchResult]:
    """Search nodes using trigram similarity + score enhancement"""
    if not q.strip():
        return []

    # Fetch more for re-ranking
    fetch_limit = min(limit * 3, 100)

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
    rows = execute_query("graph", query, (q, q, search_pattern, search_pattern, q, fetch_limit))
    if not rows:
        return []

    # Get scores for these nodes
    node_ids = [row['id'] for row in rows]
    scores_map = get_scores('node', node_ids)

    # Build results with composite scores
    results = []
    for row in rows:
        node_id = row['id']
        sim_rank = float(row.get('rank', 0))

        # Get scores (default if not found)
        entity_scores = scores_map.get(node_id, {
            'suspicion': 0, 'pertinence': 50, 'confidence': 50, 'anomaly': 0
        })

        composite = calculate_composite_score(sim_rank, entity_scores)

        results.append(SearchResult(
            id=node_id,
            type=row['type'],
            name=row['name'],
            snippet=row.get('snippet', ''),
            score=composite,
            metadata={
                'sim_rank': sim_rank,
                'suspicion': entity_scores['suspicion'],
                'pertinence': entity_scores['pertinence'],
                'anomaly': entity_scores['anomaly']
            }
        ))

    # Re-sort by composite score
    results.sort(key=lambda x: x.score, reverse=True)

    return results[:limit]


def search_all(q: str, limit: int = 20) -> List[SearchResult]:
    """Search both emails and nodes with combined scoring"""
    email_results = search_emails(q, limit // 2)
    node_results = search_nodes(q, limit // 2)

    # Combine and sort by composite score
    all_results = email_results + node_results
    all_results.sort(key=lambda x: x.score, reverse=True)

    return all_results[:limit]


# =============================================================================
# PIPELINE SEARCH (used by pipeline.py)
# =============================================================================

def search_corpus_scored(search_term: str, limit: int = 15) -> List[Dict[str, Any]]:
    """
    Search corpus with score enhancement for pipeline.
    Returns dict format compatible with pipeline.py
    """
    if not search_term or not search_term.strip():
        return []

    # Fetch more for re-ranking
    fetch_limit = min(limit * 3, 60)

    try:
        query = """
            SELECT
                doc_id as id,
                subject as name,
                sender_email,
                recipients_to,
                date_sent as date,
                ts_headline('english', COALESCE(body_text, subject), plainto_tsquery('english', %s),
                    'StartSel=<mark>, StopSel=</mark>, MaxWords=35, MinWords=10') as snippet,
                ts_rank(tsv, plainto_tsquery('english', %s)) as rank
            FROM emails
            WHERE tsv @@ plainto_tsquery('english', %s)
            ORDER BY rank DESC
            LIMIT %s
        """
        rows = execute_query("sources", query, (search_term, search_term, search_term, fetch_limit))
        if not rows:
            return []

        # Get scores
        doc_ids = [row['id'] for row in rows]
        scores_map = get_scores('email', doc_ids)

        # Calculate composite scores and sort
        results = []
        for row in rows:
            doc_id = row['id']
            ts_rank = float(row.get('rank', 0))

            entity_scores = scores_map.get(doc_id, {
                'suspicion': 0, 'pertinence': 50, 'confidence': 70, 'anomaly': 0
            })

            composite = calculate_composite_score(ts_rank, entity_scores)

            results.append({
                'id': doc_id,
                'name': row.get('name'),
                'sender_email': row.get('sender_email'),
                'recipients_to': row.get('recipients_to'),
                'date': row.get('date'),
                'snippet': row.get('snippet'),
                'rank': composite,
                'ts_rank': ts_rank,
                'suspicion': entity_scores['suspicion'],
                'pertinence': entity_scores['pertinence']
            })

        # Sort by composite score
        results.sort(key=lambda x: x['rank'], reverse=True)

        return results[:limit]
    except Exception:
        return []
