"""Full-text search functions with score integration - PostgreSQL + Go

Hybrid search architecture:
- Go microservice (port 8003): Fast parallel term search
- PostgreSQL FTS: Full-text with scoring and snippets
- In-memory caching: Avoid redundant queries
"""
from typing import List, Dict, Any, Optional
import httpx
import threading
import time
from collections import OrderedDict
from app.db import execute_query
from app.models import SearchResult

GO_SEARCH_URL = "http://127.0.0.1:8003"

# =============================================================================
# SEARCH CACHE - Avoid redundant queries
# =============================================================================

class SearchCache:
    """Thread-safe LRU cache for search results"""
    def __init__(self, max_size: int = 200, ttl: int = 300):
        self.max_size = max_size
        self.ttl = ttl
        self.cache: OrderedDict = OrderedDict()
        self.timestamps: Dict[str, float] = {}
        self.lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[List]:
        with self.lock:
            if key not in self.cache:
                self.misses += 1
                return None
            if time.time() - self.timestamps[key] > self.ttl:
                del self.cache[key]
                del self.timestamps[key]
                self.misses += 1
                return None
            self.cache.move_to_end(key)
            self.hits += 1
            return self.cache[key]

    def set(self, key: str, value: List):
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
            else:
                if len(self.cache) >= self.max_size:
                    oldest = next(iter(self.cache))
                    del self.cache[oldest]
                    del self.timestamps[oldest]
            self.cache[key] = value
            self.timestamps[key] = time.time()

    def stats(self) -> Dict:
        with self.lock:
            total = self.hits + self.misses
            return {"size": len(self.cache), "hits": self.hits, "misses": self.misses,
                    "hit_rate": round(self.hits / total, 2) if total > 0 else 0}

_search_cache = SearchCache()

# =============================================================================
# AUTO-SCORING - Keywords that indicate importance
# =============================================================================

SUSPICIOUS_KEYWORDS = {
    'epstein', 'maxwell', 'trafficking', 'abuse', 'minor', 'underage', 'victim',
    'settlement', 'lawsuit', 'subpoena', 'deposition', 'indictment', 'arrest',
    'investigation', 'fbi', 'secret', 'confidential', 'offshore', 'shell company',
    'wire transfer', 'cash', 'anonymous', 'cover up', 'destroy', 'delete'
}

PERTINENT_KEYWORDS = {
    'flight', 'plane', 'jet', 'aircraft', 'passenger', 'manifest', 'log',
    'island', 'ranch', 'mansion', 'property', 'yacht', 'helicopter',
    'meeting', 'visit', 'stayed', 'traveled', 'accompanied', 'introduced',
    'payment', 'donation', 'transfer', 'account', 'foundation', 'trust'
}

def auto_score_result(result: Dict) -> Dict[str, int]:
    """Calculate suspicion/pertinence scores from content"""
    text = f"{result.get('name', '')} {result.get('snippet', '')}".lower()

    suspicion = 0
    pertinence = 50

    for kw in SUSPICIOUS_KEYWORDS:
        if kw in text:
            suspicion += 15

    for kw in PERTINENT_KEYWORDS:
        if kw in text:
            pertinence += 10

    return {
        'suspicion': min(suspicion, 100),
        'pertinence': min(pertinence, 100),
        'confidence': 70,
        'anomaly': 0
    }

# =============================================================================
# GO FAST SEARCH - Sync wrapper for pipeline
# =============================================================================

def search_go_sync(terms: List[str], limit: int = 15) -> List[Dict[str, Any]]:
    """Synchronous Go search for use in pipeline"""
    cache_key = f"go:{'+'.join(sorted(terms[:4]))}:{limit}"
    cached = _search_cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        q = " ".join(terms[:4])
        resp = httpx.get(f"{GO_SEARCH_URL}/search/fast", params={"q": q}, timeout=3.0)
        if resp.status_code == 200:
            results = resp.json()
            out = [{"id": r["id"], "name": r["name"], "snippet": r.get("snippet", ""),
                    "rank": r["rank"], "type": "email"} for r in results[:limit]]
            _search_cache.set(cache_key, out)
            return out
    except:
        pass
    return []

async def search_go_fast(terms: List[str], limit: int = 15) -> List[Dict[str, Any]]:
    """Fast parallel search via Go microservice (async)"""
    cache_key = f"go:{'+'.join(sorted(terms[:4]))}:{limit}"
    cached = _search_cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            q = " ".join(terms[:4])
            resp = await client.get(f"{GO_SEARCH_URL}/search/fast", params={"q": q})
            if resp.status_code == 200:
                results = resp.json()
                out = [{"id": r["id"], "name": r["name"], "snippet": r.get("snippet", ""),
                         "rank": r["rank"], "type": "email"} for r in results[:limit]]
                _search_cache.set(cache_key, out)
                return out
    except:
        pass
    return []

# =============================================================================
# SCORE LOOKUP (PostgreSQL)
# =============================================================================

def get_scores(target_type: str, target_ids: List[int]) -> Dict[int, Dict[str, int]]:
    """Fetch scores from PostgreSQL for given targets"""
    if not target_ids:
        return {}

    try:
        placeholders = ','.join(['%s'] * len(target_ids))
        rows = execute_query(
            "scores",
            f"""SELECT target_id, suspicion, pertinence, confidence, anomaly
                FROM scores
                WHERE target_type = %s AND target_id IN ({placeholders})""",
            tuple([target_type] + list(target_ids))
        )

        scores = {}
        for row in rows:
            scores[row['target_id']] = {
                'suspicion': row['suspicion'] or 0,
                'pertinence': row['pertinence'] or 50,
                'confidence': row['confidence'] or 50,
                'anomaly': row['anomaly'] or 0
            }
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
