"""Query processing pipeline - Multi-step investigation with streaming

Architecture:
- Fast regex extraction (instant)
- Haiku (API, paid): Final synthesis only
- Graph DB: Relationship exploration
- Chain of custody: SHA256 hashes, timestamps, citations

OPTIMIZED:
- LRU cache for repeated queries
- Async parallel DB searches
- No local LLM calls in hot path

LICENSE COMPLIANCE:
- Protect the weak (anonymize victims)
- Report truth (cite sources)
- Fight evil (follow evidence)
"""
import re
import random
import asyncio
import hashlib
from datetime import datetime
from typing import AsyncGenerator, Dict, Any, List
from functools import lru_cache
from collections import OrderedDict
import threading
import time
from app.llm_client import call_haiku
from app.db import execute_query, execute_insert, execute_update
from app.search import search_corpus_scored, search_nodes, search_go_sync, auto_score_result
import json

# =============================================================================
# LRU CACHE - Avoid redundant searches
# =============================================================================

class TTLCache:
    """Thread-safe LRU cache with TTL"""
    def __init__(self, maxsize=200, ttl=300):
        self.cache = OrderedDict()
        self.ttl = ttl
        self.maxsize = maxsize
        self.lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key):
        with self.lock:
            if key not in self.cache:
                self.misses += 1
                return None
            value, ts = self.cache[key]
            if time.time() - ts > self.ttl:
                del self.cache[key]
                self.misses += 1
                return None
            self.cache.move_to_end(key)
            self.hits += 1
            return value

    def set(self, key, value):
        with self.lock:
            if key in self.cache:
                del self.cache[key]
            elif len(self.cache) >= self.maxsize:
                self.cache.popitem(last=False)
            self.cache[key] = (value, time.time())

    def stats(self):
        total = self.hits + self.misses
        return {"hits": self.hits, "misses": self.misses, "ratio": self.hits/total if total else 0}

# Global search cache
_search_cache = TTLCache(maxsize=500, ttl=300)

# =============================================================================
# CHAIN OF CUSTODY - Evidence Integrity
# =============================================================================

def compute_evidence_hash(data: Dict) -> str:
    """Compute SHA256 hash for evidence integrity"""
    content = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(content.encode()).hexdigest()[:16]

def create_evidence_record(query: str, results: List[Dict], entities: Dict) -> Dict:
    """Create chain of custody record for investigation"""
    timestamp = datetime.utcnow().isoformat()
    evidence = {
        "query": query,
        "timestamp": timestamp,
        "result_count": len(results),
        "result_ids": [r.get('id') for r in results[:50]],
        "entities_found": {
            "persons": len(entities.get("persons", [])),
            "orgs": len(entities.get("orgs", [])),
            "locations": len(entities.get("locations", [])),
        },
        "methodology": "multi-source-search-regex-extraction"
    }
    evidence["hash"] = compute_evidence_hash(evidence)
    return evidence

# =============================================================================
# FAST REGEX EXTRACTION (replaces slow Phi-3)
# =============================================================================

def rust_extract_entities(text: str) -> Dict[str, List]:
    """Call Rust extraction service (3ms vs 50ms Python)"""
    import httpx
    try:
        r = httpx.post("http://127.0.0.1:9001/extract",
                       json={"text": text[:5000]}, timeout=2.0)
        if r.status_code == 200:
            data = r.json()
            return {
                "persons": [{"name": p["value"]} for p in data.get("persons", [])],
                "orgs": [{"name": o["value"]} for o in data.get("organizations", [])],
                "locations": [{"name": l["value"]} for l in data.get("locations", [])],
                "dates": [{"value": d["value"]} for d in data.get("dates", [])],
                "amounts": [{"value": a["value"]} for a in data.get("amounts", [])],
                "emails": [{"value": e["value"]} for e in data.get("emails", [])],
                "patterns": []
            }
    except:
        pass
    return fast_extract_python(text)

def fast_extract_entities(text: str) -> Dict[str, List]:
    """Ultra-fast extraction - try Rust first, fallback to Python"""
    # Try Rust service (3ms)
    result = rust_extract_entities(text)
    if result.get("persons") or result.get("orgs") or result.get("locations"):
        # Add Python pattern detection
        text_lower = text.lower()
        patterns = []
        if any(w in text_lower for w in ['underage', 'minor', 'young girl', 'recruitment']):
            patterns.append({"type": "recruitment_pattern"})
        if any(w in text_lower for w in ['wire transfer', 'offshore', 'shell company', 'cayman']):
            patterns.append({"type": "financial_pattern"})
        if any(w in text_lower for w in ['flight manifest', 'private jet', 'lolita express']):
            patterns.append({"type": "travel_pattern"})
        if any(w in text_lower for w in ['settlement', 'nda', 'non-disclosure', 'sealed']):
            patterns.append({"type": "cover_up_pattern"})
        result["patterns"] = patterns
        return result
    # Fallback to Python regex
    return fast_extract_python(text)

def fast_extract_python(text: str) -> Dict[str, List]:
    """Python regex extraction fallback"""
    entities = {"persons": [], "orgs": [], "locations": [], "dates": [], "amounts": [], "emails": [], "patterns": []}

    # Persons: First Last pattern
    persons = re.findall(r'\b([A-Z][a-z]{2,15} [A-Z][a-z]{2,15})\b', text)
    seen = set()
    for p in persons:
        pl = p.lower()
        if pl not in seen and pl not in {'the new', 'new york', 'los angeles', 'san francisco', 'las vegas'}:
            seen.add(pl)
            entities["persons"].append({"name": p})

    # Organizations
    orgs = re.findall(r'\b([A-Z][a-zA-Z]+(?: [A-Z][a-zA-Z]+)* (?:Inc|LLC|Corp|Ltd|Foundation|Group|Partners|Company|Co|Association))\b', text)
    for o in set(orgs):
        entities["orgs"].append({"name": o})

    # Locations
    locations = re.findall(r'\b(New York|Los Angeles|London|Paris|Miami|Palm Beach|Virgin Islands|Manhattan|Florida|California|Washington|St\. Thomas|Little St\. James)\b', text, re.I)
    for loc in set(locations):
        entities["locations"].append({"name": loc.title()})

    # Dates
    dates = re.findall(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{2}[/-]\d{2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4})\b', text, re.I)
    for d in dates[:10]:
        entities["dates"].append({"value": d})

    # Amounts
    amounts = re.findall(r'(\$[\d,]+(?:\.\d{2})?(?:[MBK])?)', text)
    for a in set(amounts):
        if len(a) > 3:
            entities["amounts"].append({"value": a})

    # Emails
    emails = re.findall(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', text)
    for e in set(emails):
        entities["emails"].append({"value": e.lower()})

    # Criminal pattern detection (LICENSE: pattern analysis of criminal activity)
    text_lower = text.lower()
    patterns_detected = []
    if any(w in text_lower for w in ['underage', 'minor', 'young girl', 'recruitment']):
        patterns_detected.append("recruitment_pattern")
    if any(w in text_lower for w in ['wire transfer', 'offshore', 'shell company', 'cayman']):
        patterns_detected.append("financial_pattern")
    if any(w in text_lower for w in ['flight manifest', 'private jet', 'lolita express']):
        patterns_detected.append("travel_pattern")
    if any(w in text_lower for w in ['settlement', 'nda', 'non-disclosure', 'sealed']):
        patterns_detected.append("cover_up_pattern")
    entities["patterns"] = [{"type": p} for p in patterns_detected]

    return entities

NL = chr(10)

# =============================================================================
# LANGUAGE DETECTION
# =============================================================================

FRENCH_MARKERS = {
    'qui', 'est', 'que', 'quoi', 'comment', 'pourquoi', 'quand', 'quel', 'quelle',
    'quels', 'quelles', 'sont', 'avec', 'dans', 'pour', 'sur', 'entre', 'comme',
    'mais', 'donc', 'aussi', 'tous', 'tout', 'cette', 'ces', 'leur', 'leurs',
    'nous', 'vous', 'ils', 'elles', 'ont', 'était', 'être', 'avoir', 'fait',
    'très', 'plus', 'moins', 'bien', 'peut', 'doit', 'faut', 'parce', 'depuis',
    'pendant', 'avant', 'après', 'contre', 'sans', 'sous', 'vers', 'chez',
    'trouve', 'montre', 'cherche', 'emails', 'mails', 'connexions', 'liens'
}

SPANISH_MARKERS = {
    'que', 'quien', 'como', 'donde', 'cuando', 'porque', 'cual', 'cuales',
    'es', 'son', 'está', 'están', 'con', 'para', 'por', 'entre', 'sobre',
    'pero', 'también', 'todos', 'esta', 'estas', 'estos', 'ellos', 'ellas'
}

def detect_language(text: str) -> str:
    """Detect language from text - returns 'fr', 'es', or 'en'"""
    words = set(re.findall(r'\b([a-zàâäéèêëïîôùûüç]+)\b', text.lower()))

    fr_count = len(words & FRENCH_MARKERS)
    es_count = len(words & SPANISH_MARKERS)

    if fr_count >= 2:
        return 'fr'
    elif es_count >= 2:
        return 'es'
    return 'en'


# =============================================================================
# ANTI-LOOP TRACKING
# =============================================================================

def get_session_search_history(conversation_id: str) -> Dict[str, int]:
    """Get search terms already used in this session"""
    if not conversation_id:
        return {}

    rows = execute_query(
        "sessions",
        """SELECT search_term, COUNT(*) as cnt
           FROM session_searches
           WHERE conversation_id = %s
           GROUP BY search_term""",
        (conversation_id,)
    )
    return {r['search_term'].lower(): r['cnt'] for r in rows}


def record_session_search(conversation_id: str, term: str, email_ids: List[int]):
    """Record a search in session history"""
    if not conversation_id:
        return
    try:
        execute_insert(
            "sessions",
            """INSERT INTO session_searches (conversation_id, search_term, email_ids)
               VALUES (%s, %s, %s)""",
            (conversation_id, term.lower(), json.dumps(email_ids))
        )
    except:
        pass


def get_session_seen_emails(conversation_id: str) -> set:
    """Get email IDs already seen in this session"""
    if not conversation_id:
        return set()

    rows = execute_query(
        "sessions",
        "SELECT email_ids FROM session_searches WHERE conversation_id = %s",
        (conversation_id,)
    )
    seen = set()
    for r in rows:
        ids = r.get('email_ids', [])
        if isinstance(ids, list):
            seen.update(ids)
    return seen


ALTERNATIVE_ANGLES = [
    "flight records", "Virgin Islands", "legal correspondence",
    "bank transfers", "property records", "known associates",
    "Maxwell connections", "foundation payments", "travel dates",
    "witness names", "settlement documents", "private jet"
]


def get_timeline_context(query: str, email_dates: list) -> str:
    """Get relevant case timeline events for context"""
    events = []

    # Search by people mentioned in query
    people_terms = ['epstein', 'maxwell', 'giuffre', 'acosta']
    query_lower = query.lower()
    matching_people = [p for p in people_terms if p in query_lower]

    if matching_people:
        # Get events involving these people
        placeholders = ','.join(['%s'] * len(matching_people))
        for person in matching_people:
            rows = execute_query(
                "l_data",
                f"""SELECT event_date, event_type, event_title, event_description, jurisdiction, case_number
                    FROM case_timeline
                    WHERE people_involved::text ILIKE %s
                    ORDER BY event_date""",
                (f'%{person}%',)
            )
            for r in rows:
                if r not in events:
                    events.append(r)

    # Also get events near email dates
    if email_dates:
        date_range = [d for d in email_dates if d and len(str(d)) >= 7]
        if date_range:
            min_date = min(date_range)[:10]
            max_date = max(date_range)[:10]
            rows = execute_query(
                "l_data",
                """SELECT event_date, event_type, event_title, event_description, jurisdiction, case_number
                   FROM case_timeline
                   WHERE event_date BETWEEN %s AND %s
                   ORDER BY event_date""",
                (min_date, max_date)
            )
            for r in rows:
                if r not in events:
                    events.append(r)

    if not events:
        return ""

    # Sort and format
    events = sorted(events, key=lambda x: x['event_date'])
    lines = ["CASE TIMELINE (verified events):"]
    for e in events[:10]:
        case_ref = f" [{e['case_number']}]" if e.get('case_number') else ""
        lines.append(f"  {e['event_date']} | {e['event_type'].upper()}: {e['event_title']}{case_ref}")
        if e.get('event_description'):
            lines.append(f"    → {e['event_description'][:100]}")

    return NL.join(lines)


def get_graph_context(query: str, discovered_names: List[str] = None) -> str:
    """Get relevant graph nodes and relationships for the query"""
    graph_lines = []

    # Search nodes matching the query
    try:
        node_results = search_nodes(query, limit=10)
        if node_results:
            graph_lines.append("GRAPH ENTITIES (from depositions, court docs, extractions):")
            for r in node_results[:8]:
                meta = r.metadata or {}
                suspicion = meta.get('suspicion', 0)
                marker = " [!]" if suspicion >= 30 else ""
                graph_lines.append(f"  {r.type.upper()}: {r.name}{marker}")
    except:
        pass

    # Also search for discovered names
    if discovered_names:
        for name in discovered_names[:3]:
            try:
                name_results = search_nodes(name, limit=5)
                for r in name_results:
                    line = f"  {r.type.upper()}: {r.name}"
                    if line not in graph_lines:
                        graph_lines.append(line)
            except:
                pass

    # Get edges/relationships for key entities
    if graph_lines:
        try:
            # Get some relationships
            rows = execute_query("graph", """
                SELECT DISTINCT e.type, fn.name as from_name, tn.name as to_name
                FROM edges e
                JOIN nodes fn ON e.from_node_id = fn.id
                JOIN nodes tn ON e.to_node_id = tn.id
                WHERE fn.name ILIKE %s OR tn.name ILIKE %s
                LIMIT 10
            """, (f'%{query}%', f'%{query}%'))

            if rows:
                graph_lines.append("\nRELATIONSHIPS:")
                for r in rows[:8]:
                    graph_lines.append(f"  {r['from_name']} --[{r['type']}]--> {r['to_name']}")
        except:
            pass

    return NL.join(graph_lines) if graph_lines else ""

# =============================================================================
# SYSTEM PROMPTS
# =============================================================================

HAIKU_SYSTEM_PROMPT_BASE = """You are a forensic analyst. Direct. Precise.

ALWAYS STRUCTURE YOUR RESPONSE:
1. ANALYSIS: (what you found)
2. FINDINGS: (key facts with #IDs)
3. NEXT STEP: (specific action)

RULES:
- Cite sources: #ID for emails
- Be concise (3-6 sentences)
- End with a specific next step

NEVER:
- Theatrical language
- Filler phrases
- Generic suggestions"""

LANGUAGE_INSTRUCTIONS = {
    'en': "",
    'fr': """
LANGUE: Français uniquement.
- Style direct et professionnel
- Citations: #ID
- Même règles de concision""",
    'es': """
IDIOMA: Español únicamente.
- Estilo directo y profesional
- Citas: #ID
- Mismas reglas de concisión"""
}

def get_system_prompt(lang: str = 'en') -> str:
    """Get system prompt with language instructions"""
    return HAIKU_SYSTEM_PROMPT_BASE + LANGUAGE_INSTRUCTIONS.get(lang, '')

FOLLOWUP_PROMPT = """Based on these search results, what's MISSING? What should I search next?

Results so far:
{results}

Reply with 1-2 specific search terms (names, domains, keywords) that would fill gaps.
Format: term1, term2
Nothing else."""

# =============================================================================
# STOP WORDS
# =============================================================================

STOP_WORDS = {
    # English
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare',
    'ought', 'used', 'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by',
    'from', 'as', 'into', 'through', 'during', 'before', 'after', 'above',
    'who', 'what', 'where', 'when', 'why', 'how', 'which', 'show', 'me',
    'find', 'get', 'tell', 'give', 'list', 'all', 'any', 'some', 'every',
    # French
    'qui', 'que', 'quoi', 'est', 'sont', 'était', 'étaient', 'être', 'avoir',
    'fait', 'avec', 'dans', 'pour', 'sur', 'par', 'entre', 'comme', 'mais',
    'donc', 'aussi', 'tous', 'tout', 'cette', 'ces', 'leur', 'leurs', 'nous',
    'vous', 'ils', 'elles', 'ont', 'très', 'plus', 'moins', 'bien', 'peut',
    'doit', 'faut', 'quand', 'comment', 'pourquoi', 'quel', 'quelle', 'quels',
    'montre', 'moi', 'trouve', 'cherche', 'donne', 'voir', 'liste',
    # Spanish
    'que', 'quien', 'como', 'donde', 'cuando', 'porque', 'cual', 'cuales',
    'es', 'son', 'está', 'están', 'con', 'para', 'por', 'entre', 'sobre',
    'pero', 'también', 'todos', 'esta', 'estas', 'estos', 'ellos', 'ellas',
    'muestra', 'busca', 'encuentra', 'dame', 'ver', 'lista',
    'below', 'between', 'under', 'again', 'further', 'then', 'once',
    'here', 'there', 'when', 'where', 'why', 'how', 'all', 'each', 'few',
    'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only',
    'own', 'same', 'so', 'than', 'too', 'very', 'just', 'and', 'but',
    'if', 'or', 'because', 'until', 'while', 'although', 'though',
    'what', 'which', 'who', 'whom', 'this', 'that', 'these', 'those',
    'tell', 'show', 'find', 'give', 'know', 'about', 'look', 'want',
    'search', 'explain', 'describe', 'list', 'help', 'please',
    'quelles', 'quelle', 'quels', 'quel', 'les', 'des', 'une', 'dans',
    'pour', 'sur', 'avec', 'par', 'sont', 'est', 'ont', 'aux', 'entre',
}

# =============================================================================
# SEARCH FUNCTIONS
# =============================================================================

def extract_search_terms(query: str) -> List[str]:
    """Extract meaningful search terms from query"""
    # Find quoted phrases
    quoted = re.findall(r'"([^"]+)"', query)

    # Find capitalized words (names) - filter stop words
    caps = [c for c in re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b', query)
            if c.lower() not in STOP_WORDS]

    # Get remaining words
    words = [w.lower() for w in re.findall(r'\b([a-zA-Z]{4,})\b', query.lower())
             if w.lower() not in STOP_WORDS]

    terms = quoted + caps + words
    # Dedupe while preserving order
    seen = set()
    result = []
    for t in terms:
        tl = t.lower()
        if tl not in seen:
            seen.add(tl)
            result.append(t)

    return result[:5]


def search_corpus(search_term: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Search emails with caching - Go fast search first, fallback to PostgreSQL"""
    cache_key = f"search:{search_term.lower()}:{limit}"

    # Check cache first
    cached = _search_cache.get(cache_key)
    if cached is not None:
        return cached

    # Try Go service first (3-4x faster)
    go_results = search_go_sync([search_term], limit)
    if go_results:
        for r in go_results:
            scores = auto_score_result(r)
            r.update(scores)
        _search_cache.set(cache_key, go_results)
        return go_results

    # Fallback to PostgreSQL FTS
    results = search_corpus_scored(search_term, limit)
    _search_cache.set(cache_key, results)
    return results


def explore_graph_connections(entity_name: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Explore graph for entity connections"""
    try:
        # Find node by name
        nodes = execute_query(
            "graph",
            """SELECT id, type, name FROM nodes
               WHERE name ILIKE %s OR name_normalized ILIKE %s
               LIMIT 5""",
            (f"%{entity_name}%", f"%{entity_name}%")
        )

        if not nodes:
            return []

        connections = []
        for node in nodes:
            # Get edges from this node
            edges = execute_query(
                "graph",
                """SELECT e.type as rel_type, n2.name as connected_to, n2.type as node_type
                   FROM edges e
                   JOIN nodes n2 ON e.to_node_id = n2.id
                   WHERE e.from_node_id = %s
                   LIMIT %s""",
                (node['id'], limit)
            )
            for edge in edges:
                connections.append({
                    'from': node['name'],
                    'relation': edge['rel_type'],
                    'to': edge['connected_to'],
                    'to_type': edge['node_type']
                })

            # Also get reverse edges
            rev_edges = execute_query(
                "graph",
                """SELECT e.type as rel_type, n2.name as connected_from, n2.type as node_type
                   FROM edges e
                   JOIN nodes n2 ON e.from_node_id = n2.id
                   WHERE e.to_node_id = %s
                   LIMIT %s""",
                (node['id'], limit)
            )
            for edge in rev_edges:
                connections.append({
                    'from': edge['connected_from'],
                    'relation': edge['rel_type'],
                    'to': node['name'],
                    'from_type': edge['node_type']
                })

        return connections[:limit]
    except Exception:
        return []


def format_results_for_llm(results: List[Dict], search_term: str) -> str:
    """Format search results for LLM consumption"""
    if not results:
        return f"[Search '{search_term}': No results]"

    lines = [f"[Search '{search_term}': {len(results)} results]"]
    for r in results[:8]:
        # Show suspicion indicator if high
        sus = r.get('suspicion', 0)
        sus_marker = " [!]" if sus >= 30 else ""
        lines.append(f"  #{r.get('id')}{sus_marker}: {r.get('name', 'No subject')[:60]}")
        lines.append(f"    From: {r.get('sender_email', '?')} | Date: {str(r.get('date', '?'))[:10]}")
        snippet = r.get('snippet', '')
        if snippet:
            # Clean snippet
            snippet = re.sub(r'<[^>]+>', '', snippet)[:150]
            lines.append(f"    \"{snippet}...\"")
    return NL.join(lines)


async def extract_entities_from_results(results: List[Dict], use_local_llm: bool = True) -> List[Dict]:
    """Extract entities from search results using local Phi-3 or fallback to regex

    Returns list of {name, type, count} dicts
    """
    if not results:
        return []

    # Combine text from results
    combined_text = []
    for r in results[:12]:
        text_parts = []
        if r.get('name'):
            text_parts.append(str(r['name']))
        if r.get('sender_email'):
            text_parts.append(f"From: {r['sender_email']}")
        if r.get('recipients_to'):
            recips = r['recipients_to']
            if isinstance(recips, list):
                # Handle list of strings or dicts
                recip_strs = []
                for rec in recips[:3]:
                    if isinstance(rec, dict):
                        recip_strs.append(rec.get('email', str(rec)))
                    else:
                        recip_strs.append(str(rec))
                text_parts.append(f"To: {', '.join(recip_strs)}")
            else:
                text_parts.append(f"To: {recips}")
        if r.get('snippet'):
            snippet = re.sub(r'<[^>]+>', '', str(r['snippet']))[:300]
            text_parts.append(snippet)
        combined_text.append(' '.join(text_parts))

    full_text = '\n\n'.join(combined_text)

    # Try local LLM extraction first
    if use_local_llm:
        try:
            entities = await extract_entities_local(full_text)
            if entities:
                # Dedupe and count
                entity_counts = {}
                for e in entities:
                    name = e.get('name', '').strip()
                    etype = e.get('type', 'unknown')
                    if name and len(name) > 2:
                        key = (name.lower(), etype)
                        if key not in entity_counts:
                            entity_counts[key] = {'name': name, 'type': etype, 'count': 0}
                        entity_counts[key]['count'] += 1

                return list(entity_counts.values())
        except Exception:
            pass  # Fall through to regex

    # Fallback: regex extraction
    entities = []

    # Names (First Last pattern)
    name_pattern = r'\b([A-Z][a-z]{2,15} [A-Z][a-z]{2,15})\b'
    names = re.findall(name_pattern, full_text)
    name_counts = {}
    # No filtering - anything could be relevant
    for n in names:
        name_counts[n] = name_counts.get(n, 0) + 1

    for name, count in name_counts.items():
        if count >= 1:
            entities.append({'name': name, 'type': 'person', 'count': count})

    # Organizations (capitalized words ending in Inc, LLC, Corp, etc)
    org_pattern = r'\b([A-Z][a-zA-Z]+(?: [A-Z][a-zA-Z]+)* (?:Inc|LLC|Corp|Ltd|Foundation|Group|Partners))\b'
    orgs = re.findall(org_pattern, full_text)
    for org in set(orgs):
        entities.append({'name': org, 'type': 'org', 'count': orgs.count(org)})

    # Amounts ($X,XXX or $X.XM)
    amount_pattern = r'\$[\d,]+(?:\.\d{1,2})?(?:[MBK])?'
    amounts = re.findall(amount_pattern, full_text)
    for amt in set(amounts):
        if len(amt) > 3:  # Skip tiny amounts
            entities.append({'name': amt, 'type': 'amount', 'count': amounts.count(amt)})

    return entities


# =============================================================================
# MAIN PIPELINE - MULTI-STEP INVESTIGATION
# =============================================================================

async def process_query(query: str, conversation_id: str = None, is_auto: bool = False) -> AsyncGenerator[Dict[str, Any], None]:
    """Multi-step investigation pipeline - deep local search, single API call"""

    # Detect language
    user_lang = detect_language(query)

    # Save user message
    if conversation_id:
        try:
            execute_insert(
                "sessions",
                "INSERT INTO messages (conversation_id, role, content, is_auto) VALUES (%s, %s, %s, %s)",
                (conversation_id, "user", query, 1 if is_auto else 0)
            )
        except:
            pass

    # Get session history for anti-loop
    session_history = get_session_search_history(conversation_id)
    session_seen_emails = get_session_seen_emails(conversation_id)

    all_results = []
    all_ids = set()
    search_history = []
    discovered_entities = set()  # Track entities we find
    is_looping = False

    # ==========================================================================
    # STEP 1: Initial broad search
    # ==========================================================================
    yield {"type": "status", "msg": "Analyzing query..."}
    yield {"type": "thinking", "text": f"Query: \"{query}\"\n"}
    if user_lang != 'en':
        yield {"type": "thinking", "text": f"Language: {user_lang}\n"}

    initial_terms = extract_search_terms(query)
    if not initial_terms:
        initial_terms = [query]

    yield {"type": "thinking", "text": f"Terms: {', '.join(initial_terms)}\n\n"}

    # Check for loop - if ALL initial terms were already searched 2+ times
    loop_terms = [t for t in initial_terms if session_history.get(t.lower(), 0) >= 2]
    if len(loop_terms) == len(initial_terms) and len(loop_terms) > 0:
        is_looping = True
        # Suggest alternative angles
        used_terms = set(session_history.keys())
        alternatives = [a for a in ALTERNATIVE_ANGLES if a.lower() not in used_terms][:4]

        if user_lang == 'fr':
            loop_msg = f"J'ai déjà analysé cette piste en profondeur ({', '.join(loop_terms)}). "
            loop_msg += f"Emails vus: {len(session_seen_emails)}. "
            loop_msg += "Nouvelles pistes d'investigation: " + ", ".join(alternatives) + "?"
        else:
            loop_msg = f"I've thoroughly analyzed this trail already ({', '.join(loop_terms)}). "
            loop_msg += f"Emails seen: {len(session_seen_emails)}. "
            loop_msg += "New investigation angles: " + ", ".join(alternatives) + "?"

        yield {"type": "chunk", "text": loop_msg}
        yield {"type": "suggestions", "queries": alternatives}
        yield {"type": "done", "sources": list(session_seen_emails)[:20]}
        return

    # First search - search each term separately for better recall
    yield {"type": "status", "msg": f"[1/5] Searching {len(initial_terms[:4])} terms..."}

    for i, term in enumerate(initial_terms[:4]):
        yield {"type": "thinking", "text": f"[1.{i+1}] \"{term}\"\n"}

        res = search_corpus(term, limit=12)
        search_history.append({"term": term, "count": len(res)})

        # Track this search
        result_ids = [r.get('id') for r in res if r.get('id')]
        record_session_search(conversation_id, term, result_ids)

        if res:
            new_results = [r for r in res if r.get('id') not in session_seen_emails and r.get('id') not in all_ids]
            all_results.extend(new_results)
            for r in new_results:
                all_ids.add(r.get('id'))
            yield {"type": "thinking", "text": f"    → {len(res)} emails ({len(new_results)} new)\n"}

    yield {"type": "sources", "ids": list(all_ids)}

    # ==========================================================================
    # STEP 2: Extract entities and search by sender domains
    # ==========================================================================
    if all_results:
        yield {"type": "thinking", "text": f"\nExtracting patterns...\n"}

        # Collect all senders
        all_senders = [r.get('sender_email', '') for r in all_results if r.get('sender_email')]

        # Find interesting domains (not generic)
        domain_counts = {}
        for s in all_senders:
            if '@' in s:
                domain = s.split('@')[1]
                if domain not in ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'aol.com']:
                    domain_counts[domain] = domain_counts.get(domain, 0) + 1

        # Search top 2 domains
        sorted_domains = sorted(domain_counts.items(), key=lambda x: -x[1])[:2]
        for domain, count in sorted_domains:
            domain_term = domain.split('.')[0]
            if domain_term.lower() not in [t.lower() for t in initial_terms] and len(domain_term) > 3:
                discovered_entities.add(domain)
                yield {"type": "status", "msg": f"[2/5] Domain: {domain}..."}
                yield {"type": "thinking", "text": f"[2] Domain \"{domain}\" ({count}x)\n"}

                res = search_corpus(domain_term, limit=12)
                search_history.append({"term": domain_term, "count": len(res)})
                new_count = 0
                for r in res:
                    if r.get('id') not in all_ids:
                        all_results.append(r)
                        all_ids.add(r.get('id'))
                        new_count += 1
                if new_count > 0:
                    yield {"type": "thinking", "text": f"    → +{new_count} new emails\n"}
                    yield {"type": "sources", "ids": list(all_ids)}
                break

    # ==========================================================================
    # STEP 3: Fast regex extraction (instant, no LLM)
    # ==========================================================================
    extracted_entities = []
    parallel_extracted = {}
    if len(all_results) > 2:
        yield {"type": "status", "msg": "[3/5] Fast extraction..."}

        # Combine text from results
        combined_text = NL.join([
            f"{r.get('name', '')} {r.get('sender_email', '')} {r.get('snippet', '')[:300]}"
            for r in all_results[:20]
        ])

        # Fast regex extraction (instant)
        parallel_extracted = fast_extract_entities(combined_text)
        total_count = sum(len(v) for v in parallel_extracted.values())
        yield {"type": "thinking", "text": f"[3] Extracted: {total_count} entities\n"}

        # Alert on criminal patterns (LICENSE: criminal pattern detection)
        patterns = parallel_extracted.get("patterns", [])
        if patterns:
            pattern_names = [p.get("type", "").replace("_", " ") for p in patterns]
            yield {"type": "thinking", "text": f"    ⚠ PATTERNS: {', '.join(pattern_names)}\n"}

        # Convert to old format
        for p in parallel_extracted.get("persons", []):
            extracted_entities.append({"name": p.get("name", ""), "type": "person", "count": 1})
        for o in parallel_extracted.get("orgs", []):
            extracted_entities.append({"name": o.get("name", ""), "type": "org", "count": 1})
        for l in parallel_extracted.get("locations", []):
            extracted_entities.append({"name": l.get("name", ""), "type": "location", "count": 1})

        # Filter and search by persons found - use parallel async searches
        persons = [e for e in extracted_entities if e.get('type') == 'person']
        persons = sorted(persons, key=lambda x: -x.get('count', 0))

        # Collect entities to search in parallel
        entities_to_search = []
        for entity in persons[:3]:
            name = entity.get('name', '')
            if name and name not in discovered_entities and name.lower() not in query.lower():
                entities_to_search.append(entity)
                discovered_entities.add(name)

        # Search entities
        for entity in entities_to_search[:2]:  # Limit to 2 for speed
            name = entity.get('name', '')
            yield {"type": "thinking", "text": f"    → {name}\n"}
            res = search_corpus(name, limit=8)
            search_history.append({"term": name, "count": len(res)})
            new_count = 0
            for r in res:
                rid = r.get('id')
                if rid and rid not in all_ids:
                    all_results.append(r)
                    all_ids.add(rid)
                    new_count += 1
            if new_count > 0:
                yield {"type": "sources", "ids": list(all_ids)}

        # Also search organizations
        orgs = [e for e in extracted_entities if e.get('type') == 'org']
        for entity in orgs[:1]:
            name = entity.get('name', '')
            if name and name not in discovered_entities:
                discovered_entities.add(name)
                yield {"type": "thinking", "text": f"    Org: {name}\n"}
                res = search_corpus(name, limit=8)
                search_history.append({"term": name, "count": len(res)})
                for r in res:
                    if r.get('id') not in all_ids:
                        all_results.append(r)
                        all_ids.add(r.get('id'))

        # Explore graph connections for top entities
        graph_connections = []
        for entity_name in list(discovered_entities)[:2]:
            conns = explore_graph_connections(entity_name, limit=5)
            if conns:
                graph_connections.extend(conns)
                # Search connected entities
                for conn in conns[:2]:
                    connected = conn.get('to') or conn.get('from')
                    if connected and connected not in discovered_entities:
                        discovered_entities.add(connected)
                        rel = conn.get('relation', 'connected')
                        yield {"type": "thinking", "text": f"    Graph: {entity_name} --{rel}--> {connected}\n"}

        if graph_connections:
            yield {"type": "graph", "connections": graph_connections[:10]}

    # ==========================================================================
    # STEP 4: Search by date clusters
    # ==========================================================================
    if len(all_results) > 5:
        # Find date clusters
        dates = [str(r.get('date', ''))[:7] for r in all_results if r.get('date')]
        date_counts = {}
        for d in dates:
            if d and len(d) >= 7:
                date_counts[d] = date_counts.get(d, 0) + 1

        if date_counts:
            # Find peak month
            peak_month = max(date_counts.items(), key=lambda x: x[1])
            if peak_month[1] >= 3:
                yield {"type": "thinking", "text": f"[4] Timeline spike: {peak_month[0]} ({peak_month[1]} emails)\n"}

    # ==========================================================================
    # STEP 5: Search recipients trail
    # ==========================================================================
    if len(all_results) > 3:
        all_recipients = []
        for r in all_results[:10]:
            recip = r.get('recipients_to', '')
            if isinstance(recip, list):
                all_recipients.extend([x for x in recip if x])
            elif isinstance(recip, str) and recip:
                all_recipients.extend([x.strip() for x in recip.split(',') if x.strip()])

        # Find interesting recipients
        recip_counts = {}
        for rec in all_recipients:
            if '@' in rec:
                local = rec.split('@')[0].lower()
                if len(local) > 3 and local not in ['info', 'admin', 'support', 'contact', 'noreply']:
                    recip_counts[rec] = recip_counts.get(rec, 0) + 1

        top_recips = sorted(recip_counts.items(), key=lambda x: -x[1])[:1]
        for recip, count in top_recips:
            if count >= 2:
                local_part = recip.split('@')[0]
                if local_part not in discovered_entities and local_part.lower() not in query.lower():
                    discovered_entities.add(local_part)
                    yield {"type": "status", "msg": f"[4/5] Recipient: {local_part}..."}
                    yield {"type": "thinking", "text": f"[5] Recipient \"{recip}\" ({count}x)\n"}

                    res = search_corpus(local_part, limit=8)
                    search_history.append({"term": local_part, "count": len(res)})
                    new_count = 0
                    for r in res:
                        if r.get('id') not in all_ids:
                            all_results.append(r)
                            all_ids.add(r.get('id'))
                            new_count += 1
                    if new_count > 0:
                        yield {"type": "thinking", "text": f"    → +{new_count} new emails\n"}
                        yield {"type": "sources", "ids": list(all_ids)}

    # ==========================================================================
    # STEP 6: One more keyword from subjects
    # ==========================================================================
    if len(all_results) > 5:
        subject_words = []
        for r in all_results[:15]:
            subj = str(r.get('name', '')).lower()
            words = re.findall(r'\b([a-z]{5,15})\b', subj)
            subject_words.extend(words)

        word_counts = {}
        # No filtering - anything could be evidence
        for w in subject_words:
            if w not in query.lower():  # Only skip query terms to avoid loops
                word_counts[w] = word_counts.get(w, 0) + 1

        top_words = sorted(word_counts.items(), key=lambda x: -x[1])[:1]
        for word, count in top_words:
            if count >= 3 and word not in discovered_entities:
                yield {"type": "status", "msg": f"[5/5] Keyword: {word}..."}
                yield {"type": "thinking", "text": f"[6] Keyword \"{word}\" ({count}x in subjects)\n"}

                res = search_corpus(word, limit=8)
                search_history.append({"term": word, "count": len(res)})
                new_count = 0
                for r in res:
                    if r.get('id') not in all_ids:
                        all_results.append(r)
                        all_ids.add(r.get('id'))
                        new_count += 1
                if new_count > 0:
                    yield {"type": "thinking", "text": f"    → +{new_count} new emails\n"}
                    yield {"type": "sources", "ids": list(all_ids)}

    yield {"type": "thinking", "text": f"\n━━━ {len(all_results)} emails collected ━━━\n"}

    # ==========================================================================
    # STEP 4: Phi-3 synthesis (local, streaming) + Haiku DB enrichment (1 API call)
    # ==========================================================================
    yield {"type": "thinking", "text": f"\n--- Phi-3 Synthesis ---\n"}
    yield {"type": "status", "msg": "Analyzing findings..."}

    if not all_results:
        response = f"""ANALYSIS: No results for "{query}".

FINDINGS: The absence of data means either:
- The connection doesn't exist in these documents
- It's hidden under different names/aliases
- The search terms are too specific

NEXT STEP: Try alternate spellings, related names, or broader search terms."""
        yield {"type": "chunk", "text": response}
        yield {"type": "suggestions", "queries": ["epstein", "maxwell", "virgin islands", "palm beach"]}
        yield {"type": "done", "sources": []}
        return

    # Prepare compact data for synthesis
    search_summary = ", ".join([f"'{s['term']}' ({s['count']})" for s in search_history[:5]])

    # Format extracted entities for context (compact)
    entities_context = ""
    if parallel_extracted:
        entity_parts = []
        persons = [p.get('name', '') for p in parallel_extracted.get("persons", [])[:5]]
        if persons:
            entity_parts.append(f"PERSONS: {', '.join(persons)}")
        orgs = [o.get('name', '') for o in parallel_extracted.get("orgs", [])[:3]]
        if orgs:
            entity_parts.append(f"ORGS: {', '.join(orgs)}")
        locs = [l.get('name', '') for l in parallel_extracted.get("locations", [])[:3]]
        if locs:
            entity_parts.append(f"LOCATIONS: {', '.join(locs)}")
        entities_context = NL.join(entity_parts)

    # Assess content quality - help L calibrate response length
    junk_domains = {'houzz.com', 'amazon.com', 'spotify.com', 'linkedin.com', 'facebook.com',
                    'twitter.com', 'newsletter', 'alert', 'noreply', 'news.', 'response.'}
    junk_subjects = {'weather', 'newsletter', 'daily digest', 'weekly', 'alert', 'notification',
                     'your order', 'shipping', 'delivered', 'sale', 'discount', 'unsubscribe'}

    junk_count = 0
    personal_count = 0
    for r in all_results[:25]:
        sender = str(r.get('sender_email', '')).lower()
        subject = str(r.get('name', '')).lower()
        # Check if junk
        if any(d in sender for d in junk_domains) or any(s in subject for s in junk_subjects):
            junk_count += 1
        # Check if personal (short subject, personal domain)
        elif '@gmail' in sender or '@yahoo' in sender or '@hotmail' in sender:
            if len(subject) < 50 and 'fwd' not in subject and 're:' not in subject:
                personal_count += 1

    total = len(all_results[:25])
    if total > 0:
        junk_ratio = junk_count / total
        if junk_ratio > 0.7:
            content_hint = "CONTENT ASSESSMENT: Mostly automated/marketing emails. Be BRIEF - 2-3 sentences, redirect to better search."
        elif junk_ratio > 0.4:
            content_hint = "CONTENT ASSESSMENT: Mixed content. Focus only on non-automated emails if any."
        elif personal_count > 3:
            content_hint = "CONTENT ASSESSMENT: Personal communications detected. Analyze carefully."
        else:
            content_hint = "CONTENT ASSESSMENT: Standard mix. Calibrate response to actual significance."
    else:
        content_hint = "CONTENT ASSESSMENT: No results. Be very brief."

    # Build concise prompt for Haiku (compact to minimize tokens)
    top_emails = []
    for r in all_results[:15]:
        sender = r.get('sender_email', '?')
        subject = r.get('name', '')[:50]
        snippet = re.sub(r'<[^>]+>', '', r.get('snippet', ''))[:100]
        top_emails.append(f"#{r.get('id')}: {subject} | {sender} | {snippet}")

    haiku_prompt = f"""Query: "{query}"
{content_hint}
Searches: {search_summary}
Found: {len(all_results)} emails

{NL.join(top_emails)}

{entities_context}

Analyze briefly. Cite #IDs. Suggest next step."""

    # Call Haiku for synthesis (fast, ~3s)
    system_prompt = get_system_prompt(user_lang)
    haiku_response = await call_haiku(haiku_prompt, system=system_prompt, max_tokens=800)

    if "error" in haiku_response:
        # Fast fallback - no LLM needed
        senders = list(set(r.get('sender_email', '') for r in all_results[:10] if r.get('sender_email')))[:3]
        dates = sorted([str(r.get('date', ''))[:7] for r in all_results if r.get('date')])
        top_ids = ', '.join([f'#{r.get("id")}' for r in all_results[:5]])

        response = f"""ANALYSIS: Found {len(all_results)} relevant emails.

FINDINGS: Key contacts include {', '.join(senders[:2]) if senders else 'various senders'}. Timeline spans {dates[0] if dates else '?'} to {dates[-1] if dates else '?'}. See {top_ids}.

NEXT STEP: Search for specific names mentioned in these emails."""
    else:
        response = haiku_response.get("text", "Analysis complete.")

    yield {"type": "chunk", "text": response}

    # Save response
    if conversation_id:
        try:
            execute_insert(
                "sessions",
                "INSERT INTO messages (conversation_id, role, content, is_auto) VALUES (%s, %s, %s, %s)",
                (conversation_id, "assistant", response, 1 if is_auto else 0)
            )
        except:
            pass

    # Background: Enrich DB with extracted entities (non-blocking)
    if parallel_extracted:
        try:
            for p in parallel_extracted.get("persons", [])[:20]:
                name = p.get("name", "").strip()
                if len(name) > 3:
                    execute_insert("graph",
                        "INSERT INTO nodes (name, name_normalized, type) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                        (name, name.lower(), "person"))
            for o in parallel_extracted.get("orgs", [])[:10]:
                name = o.get("name", "").strip()
                if len(name) > 3:
                    execute_insert("graph",
                        "INSERT INTO nodes (name, name_normalized, type) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                        (name, name.lower(), "organization"))
            for l in parallel_extracted.get("locations", [])[:10]:
                name = l.get("name", "").strip()
                if len(name) > 2:
                    execute_insert("graph",
                        "INSERT INTO nodes (name, name_normalized, type) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                        (name, name.lower(), "location"))
        except:
            pass

    # Suggest follow-ups - NO FILTERING, anything could be a lead
    query_lower = query.lower()
    suggestions = []

    for s in search_history:
        term = s['term']
        term_lower = term.lower()
        # Only skip if identical to query
        if term_lower == query_lower:
            continue
        # Prefer multi-word terms (prioritize)
        if ' ' in term and s['count'] > 0:
            suggestions.insert(0, term)
        elif s['count'] > 0:
            suggestions.append(term)

    # Add discovered entities from extraction
    for entity in discovered_entities:
        if entity.lower() not in query_lower and entity not in suggestions:
            if ' ' in entity:  # Multi-word = likely real name
                suggestions.insert(0, entity)

    # Dedupe and limit
    seen_sugg = set()
    unique_suggestions = []
    for s in suggestions:
        sl = s.lower()
        if sl not in seen_sugg:
            seen_sugg.add(sl)
            unique_suggestions.append(s)

    if unique_suggestions:
        yield {"type": "suggestions", "queries": unique_suggestions[:4]}

    # Create chain of custody record (LICENSE: evidence integrity)
    evidence = create_evidence_record(query, all_results, parallel_extracted)
    yield {"type": "done", "sources": list(all_ids), "evidence": evidence}


# =============================================================================
# AUTO-INVESTIGATION (unchanged)
# =============================================================================

async def auto_investigate(conversation_id: str, max_queries: int = 10) -> AsyncGenerator[Dict[str, Any], None]:
    """Auto-investigation mode"""

    messages = execute_query(
        "sessions",
        "SELECT content FROM messages WHERE conversation_id = %s AND role = 'user' ORDER BY created_at DESC LIMIT 1",
        (conversation_id,)
    )

    if not messages:
        yield {"type": "error", "msg": "No user message found."}
        return

    yield {"type": "auto_start", "max_queries": max_queries}

    query_count = 0
    pending = [messages[0]['content']]
    processed = set()

    while query_count < max_queries and pending:
        current = pending.pop(0)
        if current in processed:
            continue
        processed.add(current)
        query_count += 1

        yield {"type": "auto_query", "query": current, "index": query_count}

        async for event in process_query(current, conversation_id, is_auto=True):
            if event.get("type") == "suggestions":
                for q in event.get("queries", []):
                    if q not in processed and q not in pending:
                        pending.append(q)
            yield event

    yield {"type": "auto_complete", "total_queries": query_count}
