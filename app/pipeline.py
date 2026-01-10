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
import json
import logging
import re
import random
import asyncio
import hashlib
import threading
import time
from datetime import datetime
from typing import AsyncGenerator, Dict, Any, List
from functools import lru_cache
from collections import OrderedDict

from app.llm_client import call_local, call_opus
from app.db import execute_query, execute_insert, execute_update
from app.search import search_corpus_scored, search_nodes, search_go_sync, auto_score_result

log = logging.getLogger(__name__)

# =============================================================================
# MIND FILES - Persistent memories and context
# =============================================================================

def load_mind_context(query: str, max_chars: int = 2000) -> str:
    """Load relevant context from mind/ files for Opus synthesis."""
    from app.config import MIND_DIR

    context_parts = []

    # Load recent thoughts (last 10 entries)
    thoughts_file = MIND_DIR / "thoughts.md"
    if thoughts_file.exists():
        try:
            content = thoughts_file.read_text()
            entries = content.split("\n---\n")[-10:]  # Last 10 thoughts
            recent = "\n---\n".join(entries)[-1500:]
            context_parts.append(f"[RECENT THOUGHTS]\n{recent}")
        except Exception:
            pass

    # Load methods (investigation methodology)
    methods_file = MIND_DIR / "methods.md"
    if methods_file.exists():
        try:
            content = methods_file.read_text()[:800]
            context_parts.append(f"[METHODOLOGY]\n{content}")
        except Exception:
            pass

    # Query-specific context from brainstorming
    brainstorm_file = MIND_DIR / "brainstorming.md"
    if brainstorm_file.exists():
        try:
            content = brainstorm_file.read_text()
            # Find relevant sections based on query terms
            query_terms = query.lower().split()
            relevant_lines = []
            for line in content.split('\n'):
                if any(term in line.lower() for term in query_terms):
                    relevant_lines.append(line)
            if relevant_lines:
                context_parts.append(f"[RELEVANT NOTES]\n" + "\n".join(relevant_lines[:10]))
        except Exception:
            pass

    full_context = "\n\n".join(context_parts)
    return full_context[:max_chars] if full_context else ""

# =============================================================================
# INVESTIGATION ENTITY WHITELIST - Known relevant persons, places, orgs
# =============================================================================

INVESTIGATION_PERSONS = {
    # Primary subjects
    'jeffrey epstein', 'ghislaine maxwell', 'jean-luc brunel', 'sarah kellen',
    'nadia marcinkova', 'lesley groff', 'adriana ross', 'haley robson',
    # Key accusers/victims
    'virginia giuffre', 'virginia roberts', 'courtney wild', 'annie farmer',
    'maria farmer', 'jennifer araoz', 'chauntae davies',
    # Associates/accused
    'prince andrew', 'alan dershowitz', 'les wexner', 'leon black',
    'bill gates', 'bill clinton', 'donald trump', 'kevin spacey',
    'woody allen', 'ehud barak', 'jes staley', 'reid hoffman',
    # Legal/investigation
    'alexander acosta', 'barry krischer', 'james comey', 'robert mueller',
    'maurene comey', 'audrey strauss', 'geoffrey berman',
    # Modeling/recruitment
    'mc2', 'jean-luc brunel', 'claude brunel', 'peter listerman',
    # Staff/pilots
    'larry visoski', 'david rodgers', 'miles alexander',
}

INVESTIGATION_LOCATIONS = {
    'little st james', 'st james island', 'pedophile island', 'orgy island',
    'zorro ranch', 'new mexico', 'stanley new mexico',
    'palm beach', 'el brillo way', 'florida',
    'manhattan townhouse', '9 east 71st', 'east 71st street', 'new york',
    'paris apartment', 'avenue foch',
    'mar-a-lago', 'les wexner mansion', 'ohio mansion',
    'metropolitan correctional center', 'mcc new york',
}

INVESTIGATION_ORGS = {
    'mc2 model management', 'victoria\'s secret', 'l brands', 'the limited',
    'apollo global', 'deutsche bank', 'jpmorgan', 'jp morgan chase',
    'mit media lab', 'harvard university', 'gratitude america',
    'c.o.u.q. foundation', 'elan air', 'air ghislaine',
    'southern district of new york', 'sdny', 'palm beach police',
    'fbi', 'federal bureau of investigation',
}

INVESTIGATION_TOPICS = {
    'flight logs', 'flight manifest', 'lolita express', 'black book',
    'plea deal', 'non-prosecution agreement', 'npa', 'work release',
    'sex trafficking', 'trafficking', 'minor', 'underage', 'recruitment',
    'massage', 'abuse', 'molestation', 'sexual assault',
    'settlement', 'lawsuit', 'deposition', 'testimony', 'trial',
    'conviction', 'indictment', 'arrest', 'suicide', 'homicide',
}

# Spam/commercial terms to filter OUT from suggestions
SPAM_KEYWORDS = {
    # E-commerce
    'amazon', 'order', 'shipping', 'delivery', 'purchase', 'buy', 'sale',
    'product', 'review', 'rating', 'customer', 'marketplace', 'seller',
    'cart', 'checkout', 'payment', 'invoice', 'receipt',
    # Home/furniture
    'rug', 'carpet', 'shag', 'shaggy', 'cozy', 'furniture', 'mattress',
    'bedroom', 'bathroom', 'kitchen', 'decor', 'wallpaper', 'paint',
    'periwinkle', 'blue shag', 'spring mix', 'bohemian', 'boho',
    'feet solid', 'inch', 'memory foam', 'lavender', 'infused',
    # Electronics
    'bluetooth', 'wireless', 'charger', 'cable', 'adapter', 'electronic',
    'portable', 'fitness', 'exercise', 'stripper', 'pole dance',
    # Social media
    'linkedin', 'facebook', 'twitter', 'instagram', 'social media',
    'newsletter', 'subscribe', 'unsubscribe', 'promotion', 'discount',
    # Retailers
    'houzz', 'wayfair', 'ebay', 'etsy', 'walmart', 'target',
    # Common spam phrases
    'you like', 'ever ready', 'first aid', 'fully stocked', 'meet your',
    'how did', 'expectations', 'thank you for', 'your recent',
    'we\'d love', 'hear from you', 'dear customer', 'valued customer',
    'collection', 'exclusive', 'limited time', 'special offer',
    'lucid', 'linenspa', 'criterion', 'blu-ray', 'dvd',
    # Music/entertainment spam
    'lady antebellum', 'antebellum', 'band', 'album', 'concert', 'tour',
    'song', 'music', 'playlist', 'spotify', 'itunes', 'apple music',
    'grammy', 'billboard', 'country music', 'pop music', 'rock music',
    'artist', 'singer', 'musician', 'performer', 'record label',
    # More misc spam
    'three colors', 'first responder', 'ever ready', 'batteries',
    'weather', 'forecast', 'hurricane', 'tropical storm',
    # News/media spam
    'the post', 'washington post', 'new york times', 'wall street',
    'cnn', 'fox news', 'msnbc', 'nbc', 'cbs', 'abc news',
    'publisher', 'editor', 'reporter', 'journalist', 'columnist',
    'headline', 'breaking news', 'daily', 'weekly', 'newsletter',
    # Political spam (not investigation related)
    'text member', 'keeping america', 'make america', 'campaign',
    'donate', 'contribution', 'fundraising', 'rally', 'vote',
    'democrat', 'republican', 'congress', 'senate', 'house of',
    'steve bannon', 'fred ryan', 'jason rezaian',
    # Generic spam
    'the week', 'post most', 'crime victims', 'daily headlines',
}

SPAM_DOMAINS = {
    'amazon.com', 'houzz.com', 'linkedin.com', 'facebook.com', 'twitter.com',
    'ebay.com', 'wayfair.com', 'etsy.com', 'walmart.com', 'target.com',
    'groupon.com', 'yelp.com', 'pinterest.com', 'instagram.com',
}

def is_investigation_relevant(text: str) -> bool:
    """Check if text is relevant to the Epstein investigation"""
    if not text:
        return False
    text_lower = text.lower().strip()

    # Check against investigation entities
    for person in INVESTIGATION_PERSONS:
        if person in text_lower:
            return True
    for location in INVESTIGATION_LOCATIONS:
        if location in text_lower:
            return True
    for org in INVESTIGATION_ORGS:
        if org in text_lower:
            return True
    for topic in INVESTIGATION_TOPICS:
        if topic in text_lower:
            return True
    return False

def is_spam_entity(text: str) -> bool:
    """Check if text is a spam/commercial entity to filter out"""
    if not text:
        return True
    text_lower = text.lower().strip()

    # Too short
    if len(text_lower) < 4:
        return True

    # Contains spam keywords
    for spam in SPAM_KEYWORDS:
        if spam in text_lower:
            return True

    # Is a number or product code
    if text_lower.replace(' ', '').replace('-', '').isdigit():
        return True

    return False

def filter_suggestions(suggestions: List[str], query: str, strict: bool = True) -> List[str]:
    """Filter suggestions to only include investigation-relevant ones

    Args:
        suggestions: List of suggested queries
        query: Current query (to avoid duplicates)
        strict: If True, only allow investigation-relevant suggestions
    """
    query_lower = query.lower()
    relevant = []
    maybe = []

    for s in suggestions:
        s_lower = s.lower().strip()

        # Skip if same as query
        if s_lower == query_lower or s_lower in query_lower:
            continue

        # Skip spam
        if is_spam_entity(s):
            continue

        # Investigation-relevant gets priority
        if is_investigation_relevant(s):
            relevant.append(s)
        # In non-strict mode, allow potential names
        elif not strict and len(s) > 8:
            words = s.split()
            if len(words) >= 2 and all(w[0].isupper() for w in words if w):
                maybe.append(s)

    # Return relevant first, then maybe (if not strict)
    result = relevant[:4]
    if len(result) < 4 and not strict:
        result.extend(maybe[:4 - len(result)])

    return result[:4]

def get_curated_suggestions(query: str) -> List[str]:
    """Get suggestions from curated investigation documents based on query"""
    query_lower = query.lower()
    suggestions = []

    # Map query topics to relevant follow-up suggestions
    if any(x in query_lower for x in ['epstein', 'jeffrey']):
        suggestions = ['Ghislaine Maxwell', 'Virginia Giuffre', 'Lolita Express', 'Little St James Island']
    elif any(x in query_lower for x in ['maxwell', 'ghislaine']):
        suggestions = ['Virginia Giuffre testimony', 'Sarah Kellen role', 'Jean-Luc Brunel', 'Maxwell trial verdict']
    elif any(x in query_lower for x in ['giuffre', 'virginia']):
        suggestions = ['Prince Andrew accusations', 'Alan Dershowitz', 'Ghislaine Maxwell', '2008 plea deal']
    elif any(x in query_lower for x in ['prince andrew', 'andrew']):
        suggestions = ['Virginia Giuffre lawsuit', 'Settlement details', 'Maxwell connections', 'Flight logs']
    elif any(x in query_lower for x in ['lolita express', 'flight', 'plane']):
        suggestions = ['Flight logs passengers', 'Little St James trips', 'Bill Clinton flights', 'Celebrity passengers']
    elif any(x in query_lower for x in ['plea deal', '2008', 'acosta']):
        suggestions = ['Alexander Acosta role', 'Non-prosecution agreement', 'Victim impact', 'Federal investigation']
    elif any(x in query_lower for x in ['island', 'st james', 'virgin islands']):
        suggestions = ['Island construction', 'Victim testimony', 'FBI raid 2019', 'Staff witnesses']
    elif any(x in query_lower for x in ['wexner', 'les']):
        suggestions = ['Victoria Secret connection', 'Financial transfers', 'Ohio mansion', 'Power of attorney']
    elif any(x in query_lower for x in ['gates', 'bill gates']):
        suggestions = ['MIT donations', 'Meeting timeline', 'Melinda Gates divorce', 'Jeffrey Epstein meetings']
    elif any(x in query_lower for x in ['trump', 'donald']):
        suggestions = ['Mar-a-Lago connection', 'Palm Beach social circle', '2002 quote', 'Distancing timeline']
    elif any(x in query_lower for x in ['death', 'suicide', 'killed']):
        suggestions = ['Camera malfunction', 'Guard negligence', 'Autopsy findings', 'Conspiracy theories']
    elif any(x in query_lower for x in ['trial', 'verdict', 'conviction']):
        suggestions = ['Maxwell sentencing', 'Victim testimony', 'Evidence presented', 'Co-conspirators']
    elif any(x in query_lower for x in ['brunel', 'jean-luc']):
        suggestions = ['MC2 Model Management', 'Modeling recruitment', 'Paris connection', 'Brunel death']
    elif any(x in query_lower for x in ['kellen', 'sarah']):
        suggestions = ['Scheduling role', 'Immunity deal', 'Victim recruitment', 'Inner circle']
    elif any(x in query_lower for x in ['dershowitz', 'alan']):
        suggestions = ['Virginia Giuffre accusations', 'Legal defense', 'Denial statements', 'Defamation case']
    elif any(x in query_lower for x in ['black book', 'contacts', 'address']):
        suggestions = ['Celebrity contacts', 'Politician names', 'Business connections', 'European contacts']
    elif any(x in query_lower for x in ['palm beach', 'florida']):
        suggestions = ['Police investigation', 'El Brillo Way mansion', 'Victim recruitment', 'State charges']
    elif any(x in query_lower for x in ['zorro', 'new mexico', 'ranch']):
        suggestions = ['Ranch activities', 'Staff testimony', 'Scientific interests', 'Visitor logs']
    elif any(x in query_lower for x in ['mit', 'media lab', 'university']):
        suggestions = ['Joi Ito resignation', 'Donation amounts', 'Academic connections', 'Research funding']
    else:
        # Default relevant suggestions
        suggestions = ['Jeffrey Epstein network', 'Ghislaine Maxwell role', 'Victim testimonies', 'Key evidence']

    # Don't suggest what was already asked
    return [s for s in suggestions if s.lower() not in query_lower][:3]

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
# SMART RESPONSE BUILDER (when Haiku unavailable)
# =============================================================================

# Prosecution targets who could face charges
PROSECUTION_TARGETS = {
    'prince andrew': {'crimes': ['sexual abuse', 'trafficking'], 'status': 'settled lawsuit'},
    'alan dershowitz': {'crimes': ['sexual abuse allegations'], 'status': 'denies'},
    'les wexner': {'crimes': ['financial enablement', 'property transfer'], 'status': 'not charged'},
    'leon black': {'crimes': ['payments to felon', 'financial ties'], 'status': 'under scrutiny'},
    'bill gates': {'crimes': ['meetings post-conviction'], 'status': 'admitted meetings'},
    'jes staley': {'crimes': ['maintaining contact'], 'status': 'lost job'},
    'jean-luc brunel': {'crimes': ['trafficking', 'rape'], 'status': 'died in custody'},
    'ghislaine maxwell': {'crimes': ['trafficking', 'conspiracy'], 'status': 'convicted'},
    'sarah kellen': {'crimes': ['scheduling abuse', 'conspiracy'], 'status': 'immunity deal'},
    'nadia marcinkova': {'crimes': ['participating in abuse'], 'status': 'immunity deal'},
    'alexander acosta': {'crimes': ['corrupt plea deal'], 'status': 'resigned'},
}

# Topic-to-target mapping for evidence linking
TOPIC_TARGET_LINKS = {
    'lolita express': ['prince andrew', 'bill gates', 'alan dershowitz', 'bill clinton'],
    'flight log': ['prince andrew', 'bill gates', 'alan dershowitz'],
    'little st james': ['prince andrew', 'bill gates', 'bill clinton'],
    'island': ['prince andrew', 'bill gates'],
    'palm beach': ['alexander acosta', 'alan dershowitz'],
    'plea deal': ['alexander acosta'],
    'trafficking': ['ghislaine maxwell', 'jean-luc brunel', 'sarah kellen'],
    'recruitment': ['ghislaine maxwell', 'sarah kellen', 'nadia marcinkova'],
    'massage': ['ghislaine maxwell', 'sarah kellen'],
    'virginia giuffre': ['prince andrew', 'alan dershowitz', 'ghislaine maxwell'],
    'testimony': ['prince andrew', 'alan dershowitz', 'ghislaine maxwell'],
    'deposition': ['prince andrew', 'alan dershowitz'],
    'zorro ranch': ['bill gates', 'les wexner'],
    'new mexico': ['bill gates'],
    'mit media lab': ['bill gates', 'leon black'],
    'donation': ['bill gates', 'leon black', 'les wexner'],
    'deutsche bank': ['jes staley', 'leon black'],
    'financial': ['les wexner', 'leon black', 'jes staley'],
    'maxwell trial': ['ghislaine maxwell', 'sarah kellen', 'nadia marcinkova'],
    'epstein death': ['ghislaine maxwell'],  # conspiracy theories
    'suicide': ['ghislaine maxwell'],
    'model': ['jean-luc brunel', 'ghislaine maxwell'],
    'mc2': ['jean-luc brunel'],
}

def format_prosecution_evidence(results: List[Dict], query: str) -> str:
    """Format evidence relevant to prosecution of targets"""
    query_lower = query.lower()
    evidence_lines = []

    # Find relevant targets: direct mention OR topic link
    relevant_targets = set()

    # Direct mentions
    for target in PROSECUTION_TARGETS:
        if target in query_lower:
            relevant_targets.add(target)

    # Topic-based links
    for topic, targets in TOPIC_TARGET_LINKS.items():
        if topic in query_lower:
            relevant_targets.update(targets)

    for target in relevant_targets:
        info = PROSECUTION_TARGETS.get(target)
        if not info:
            continue

        # Find documents mentioning this target
        relevant_docs = []
        for r in results[:20]:
            snippet = str(r.get('snippet', '')).lower()
            name = str(r.get('name', '')).lower()
            if target in snippet or target in name:
                doc_id = r.get('id')
                relevant_docs.append({
                    'id': doc_id,
                    'snippet': r.get('snippet', '')[:100]
                })

        # Even without docs, show the linked target for topic queries
        target_title = target.title()
        crimes = ', '.join(info['crimes'])
        status = info['status']

        evidence_lines.append(f"\n**EVIDENCE AGAINST {target_title.upper()}:**")
        evidence_lines.append(f"- Potential charges: {crimes}")
        evidence_lines.append(f"- Current status: {status}")

        if relevant_docs:
            evidence_lines.append(f"- Documents found: {len(relevant_docs)}")
            for doc in relevant_docs[:2]:
                evidence_lines.append(f"  - #{doc['id']}: {doc['snippet'][:50]}...")
        else:
            evidence_lines.append(f"- Connection: linked via topic")

    return '\n'.join(evidence_lines) if evidence_lines else ''


def build_smart_response(query: str, results: List[Dict], entities: Dict) -> str:
    """Build intelligent response using curated document content"""
    if not results:
        return f"No results found for '{query}'. Try different search terms."

    # Prioritize curated investigation documents
    curated = [r for r in results if r.get('sender_email') == 'investigation@pwnd.icu']
    other = [r for r in results if r.get('sender_email') != 'investigation@pwnd.icu']

    query_lower = query.lower()

    # If we have curated docs, extract key content
    if curated:
        top_doc = curated[0]
        doc_id = top_doc.get('id')
        title = top_doc.get('name', '').upper()
        snippet = re.sub(r'<[^>]+>', '', top_doc.get('snippet', ''))

        # Build response from curated content
        lines = [f"**{title}** (#{doc_id})"]
        lines.append("")
        lines.append(snippet.strip())

        # Add related docs
        if len(curated) > 1:
            related = [f"#{r.get('id')}: {r.get('name', '')[:50]}" for r in curated[1:4]]
            lines.append("")
            lines.append("**Related documents:** " + " | ".join(related))

        # Add entities if found (filter out spam)
        persons = entities.get("persons", [])[:15]
        if persons:
            names = []
            for p in persons:
                name = p.get('name', '')
                if name and not is_spam_entity(name):
                    if is_investigation_relevant(name):
                        names.insert(0, name)  # Priority for investigation entities
                    elif len(name) > 5:
                        names.append(name)
            if names:
                lines.append("")
                lines.append(f"**Key persons:** {', '.join(names[:5])}")

        # Add prosecution evidence if target mentioned
        prosecution_evidence = format_prosecution_evidence(results, query)
        if prosecution_evidence:
            lines.append(prosecution_evidence)

        # Suggest next step
        lines.append("")
        lines.append("**Next:** Click source documents for full details.")

        return "\n".join(lines)

    # Fallback for non-curated results - provide structured summary
    lines = [f"**Document Search Results** for '{query}'"]
    lines.append("")

    # Show top documents with details
    for r in results[:5]:
        doc_id = r.get('id', '')
        title = r.get('name', 'Untitled')[:60]
        sender = r.get('sender_email', '')[:30]
        snippet = re.sub(r'<[^>]+>', '', r.get('snippet', ''))[:100]
        lines.append(f"**[#{doc_id}]** {title}")
        if sender:
            lines.append(f"  *From:* {sender}")
        if snippet:
            lines.append(f"  {snippet}...")
        lines.append("")

    # Add entities if found
    persons = entities.get("persons", [])[:8]
    if persons:
        names = [p.get('name', '') for p in persons if p.get('name') and not is_spam_entity(p.get('name', ''))]
        if names:
            lines.append(f"**Key persons mentioned:** {', '.join(names[:5])}")
            lines.append("")

    # Add prosecution evidence if target mentioned
    prosecution_evidence = format_prosecution_evidence(results, query)
    if prosecution_evidence:
        lines.append(prosecution_evidence)

    lines.append("*(Note: Full AI analysis unavailable - showing raw document excerpts)*")

    return "\n".join(lines)

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
    except (httpx.RequestError, httpx.TimeoutException, ValueError):
        pass  # Rust service unavailable, fallback to Python
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
    except Exception as e:
        log.debug("Failed to record session search: %s", e)


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
    "Ghislaine Maxwell role", "Virginia Giuffre testimony", "flight logs passengers",
    "Little St James Island", "2008 plea deal", "Palm Beach investigation",
    "Les Wexner connection", "victim testimonies", "Jean-Luc Brunel",
    "Prince Andrew accusations", "Bill Gates meetings", "Maxwell trial evidence",
    "Epstein death circumstances", "Sarah Kellen role", "Black book contacts"
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
    except Exception as e:
        log.debug("Node search failed: %s", e)

    # Also search for discovered names
    if discovered_names:
        for name in discovered_names[:3]:
            try:
                name_results = search_nodes(name, limit=5)
                for r in name_results:
                    line = f"  {r.type.upper()}: {r.name}"
                    if line not in graph_lines:
                        graph_lines.append(line)
            except Exception:
                pass  # Continue with other names

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
        except Exception as e:
            log.debug("Edge query failed: %s", e)

    return NL.join(graph_lines) if graph_lines else ""

# =============================================================================
# SYSTEM PROMPTS
# =============================================================================

HAIKU_SYSTEM_PROMPT_BASE = """Elite forensic analyst. Epstein network investigation.

ANALYSIS METHOD:
- Cross-reference names, dates, locations
- Identify patterns: who meets whom, when, where
- Note what's missing or suspiciously absent
- Follow money and access

RESPONSE FORMAT:
**KEY FINDING:** [Main conclusion, cite #ID]
**EVIDENCE:** [2-3 supporting facts with #IDs]
**CONNECTIONS:** [Non-obvious links between people/events]
**CONFIDENCE:** [confirmed/strongly indicated/possible]
**NEXT:** [Specific investigative step]

RULES:
- Lead with insight, not process
- Every claim needs a source #ID
- Flag suspicious timing or gaps
- 4-6 sentences max

NEVER: filler, theatrics, speculation without basis"""

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
        except Exception as e:
            log.debug("Failed to save user message: %s", e)

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
    # STEP 4: Claude synthesis (Opus API) + DB enrichment
    # ==========================================================================
    yield {"type": "thinking", "text": f"\n--- Claude Synthesis ---\n"}
    yield {"type": "status", "msg": "Analyzing findings..."}

    if not all_results:
        response = f"""ANALYSIS: No results for "{query}".

FINDINGS: The absence of data means either:
- The connection doesn't exist in these documents
- It's hidden under different names/aliases
- The search terms are too specific

NEXT STEP: Try alternate spellings, related names, or broader search terms."""
        yield {"type": "chunk", "text": response}
        yield {"type": "suggestions", "queries": get_curated_suggestions(query)}
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

    # Build rich prompt for Claude Opus
    top_emails = []
    for r in all_results[:10]:  # Top 10 for context
        doc_id = r.get('id', '')
        subject = r.get('name', '')[:80]
        sender = r.get('sender_email', '')[:40]
        snippet = re.sub(r'<[^>]+>', '', r.get('snippet', ''))[:150]
        top_emails.append(f"[#{doc_id}] {subject}\n  From: {sender}\n  {snippet}")

    # Get system prompt and mind context
    from app.config import SYSTEM_PROMPT_L
    mind_context = load_mind_context(query, max_chars=1500)

    # Claude prompt - rich context from local processing + mind files
    opus_prompt = f"""User query: "{query}"

SEARCH RESULTS ({len(all_results)} documents found):

{NL.join(top_emails)}

EXTRACTED ENTITIES:
{entities_context if entities_context else "No named entities extracted"}

{content_hint}

{f"PRIOR KNOWLEDGE:{NL}{mind_context}" if mind_context else ""}

Analyze these documents as an investigator. Be specific - cite document IDs like [#123].
Connect dots between people, dates, and events. Note any patterns or anomalies.
Keep response focused and under 300 words."""

    # Try Opus first (high quality), fallback to Phi-3, then smart response
    response = None
    opus_result = await call_opus(opus_prompt, system=SYSTEM_PROMPT_L, max_tokens=400)

    if opus_result.get("text") and len(opus_result.get("text", "")) > 50:
        response = opus_result["text"]
        yield {"type": "thinking", "text": f"    ✓ Opus synthesis (${opus_result.get('cost_usd', 0):.4f})\n"}
    else:
        # Fallback to local Phi-3
        yield {"type": "thinking", "text": f"    → Opus unavailable, using local model...\n"}
        phi3_prompt = f"""<|system|>
Forensic analyst. Epstein investigation. Be concise. Cite #IDs.
<|end|>

<|user|>
Query: "{query}"
Found: {len(all_results)} docs

{NL.join([f"#{r.get('id')}: {r.get('name', '')[:35]}" for r in all_results[:5]])}

{entities_context}

Key finding with #ID. 2-3 sentences max.
<|end|>

<|assistant|>"""
        local_response = await call_local(phi3_prompt, max_tokens=150, temperature=0.3)

        if local_response and len(local_response) > 30:
            response = local_response

    if not response:
        # Smart fallback - use curated document content directly
        response = build_smart_response(query, all_results, parallel_extracted)

    yield {"type": "chunk", "text": response}

    # Save response
    if conversation_id:
        try:
            execute_insert(
                "sessions",
                "INSERT INTO messages (conversation_id, role, content, is_auto) VALUES (%s, %s, %s, %s)",
                (conversation_id, "assistant", response, 1 if is_auto else 0)
            )
        except Exception as e:
            log.debug("Failed to save assistant message: %s", e)

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
            for loc in parallel_extracted.get("locations", [])[:10]:
                name = loc.get("name", "").strip()
                if len(name) > 2:
                    execute_insert("graph",
                        "INSERT INTO nodes (name, name_normalized, type) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                        (name, name.lower(), "location"))
        except Exception as e:
            log.debug("Entity enrichment failed: %s", e)

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

    # Add discovered entities from extraction (only investigation-relevant ones)
    for entity in discovered_entities:
        if entity.lower() not in query_lower and entity not in suggestions:
            if is_investigation_relevant(entity):
                suggestions.insert(0, entity)
            elif ' ' in entity and not is_spam_entity(entity):
                suggestions.append(entity)

    # Filter suggestions to remove spam and prioritize investigation entities
    filtered = filter_suggestions(suggestions, query)

    # If no good suggestions from extraction, use curated suggestions
    if len(filtered) < 2:
        curated = get_curated_suggestions(query)
        for c in curated:
            if c.lower() not in [f.lower() for f in filtered]:
                filtered.append(c)

    # Dedupe and limit
    seen_sugg = set()
    unique_suggestions = []
    for s in filtered[:6]:
        sl = s.lower()
        if sl not in seen_sugg and sl not in query_lower:
            seen_sugg.add(sl)
            unique_suggestions.append(s)

    # Always provide at least curated suggestions if nothing else
    if not unique_suggestions:
        unique_suggestions = get_curated_suggestions(query)

    if unique_suggestions:
        yield {"type": "suggestions", "queries": unique_suggestions[:4]}

    # Create chain of custody record (LICENSE: evidence integrity)
    evidence = create_evidence_record(query, all_results, parallel_extracted)
    yield {"type": "done", "sources": list(all_ids), "evidence": evidence}


# =============================================================================
# AUTO-EXPLORATION - Find unscored investigation-relevant content
# =============================================================================

def get_exploration_targets(limit: int = 20) -> List[str]:
    """Get search terms for unexplored investigation-relevant emails"""
    try:
        # Find emails with investigation keywords that haven't been scored
        rows = execute_query("sources", """
            SELECT DISTINCT e.subject
            FROM emails e
            LEFT JOIN scores s ON s.target_type = 'email' AND s.target_id = e.doc_id
            WHERE s.target_id IS NULL
              AND e.sender_email != 'investigation@pwnd.icu'
              AND (
                  LOWER(e.subject) LIKE '%epstein%'
                  OR LOWER(e.subject) LIKE '%maxwell%'
                  OR LOWER(e.subject) LIKE '%giuffre%'
                  OR LOWER(e.subject) LIKE '%trafficking%'
                  OR LOWER(e.subject) LIKE '%island%'
                  OR LOWER(e.subject) LIKE '%flight%'
                  OR LOWER(e.subject) LIKE '%victim%'
                  OR LOWER(e.subject) LIKE '%investigation%'
                  OR LOWER(e.subject) LIKE '%lawsuit%'
                  OR LOWER(e.subject) LIKE '%settlement%'
              )
            ORDER BY RANDOM()
            LIMIT %s
        """, (limit,))

        targets = []
        for row in rows:
            subject = row.get('subject', '')
            if subject and len(subject) > 10:
                # Extract key terms from subject
                words = subject.split()[:4]
                term = ' '.join(words)
                if not is_spam_entity(term):
                    targets.append(term)

        # Add known investigation entities that may have related emails
        investigation_targets = [
            "Epstein network connections",
            "Maxwell recruitment patterns",
            "Flight manifest details",
            "Victim testimony records",
            "Financial transactions Epstein",
            "Property records Little St James",
            "Legal correspondence 2008",
            "Settlement documents victims"
        ]

        # Mix exploration targets with known investigation topics
        combined = targets[:10] + investigation_targets[:10]
        random.shuffle(combined)
        return combined[:limit]

    except Exception:
        # Fallback to curated exploration targets
        return [
            "Jeffrey Epstein associates",
            "Ghislaine Maxwell network",
            "Virginia Giuffre case",
            "Flight logs analysis",
            "Victim recruitment patterns",
            "Palm Beach investigation files",
            "New York prosecution",
            "Financial trail Epstein"
        ]

def get_unscored_entity_count() -> int:
    """Count emails without scores for progress tracking"""
    try:
        rows = execute_query("sources", """
            SELECT COUNT(*) as cnt
            FROM emails e
            LEFT JOIN scores s ON s.target_type = 'email' AND s.target_id = e.doc_id
            WHERE s.target_id IS NULL
        """, ())
        return rows[0]['cnt'] if rows else 0
    except Exception:
        return 0

# =============================================================================
# AUTO-INVESTIGATION - Enhanced with exploration mode
# =============================================================================

async def auto_investigate(conversation_id: str, max_queries: int = 10) -> AsyncGenerator[Dict[str, Any], None]:
    """Auto-investigation mode with heat-seeking exploration

    Heat-seeking logic:
    - Track "heat" based on curated docs found and high scores
    - When hot: continue in same direction (follow suggestions)
    - When cooling: bounce to explore new directions
    """

    messages = execute_query(
        "sessions",
        "SELECT content FROM messages WHERE conversation_id = %s AND role = 'user' ORDER BY created_at DESC LIMIT 1",
        (conversation_id,)
    )

    if not messages:
        yield {"type": "error", "msg": "No user message found."}
        return

    # Get initial exploration targets from database
    exploration_targets = get_exploration_targets(max_queries * 2)
    unscored_count = get_unscored_entity_count()

    yield {"type": "auto_start", "max_queries": max_queries, "unscored_emails": unscored_count}

    query_count = 0
    pending = [messages[0]['content']]
    hot_pending = []  # High-priority queue for heat-seeking
    processed = set()
    exploration_index = 0

    # Heat tracking
    heat_score = 0
    consecutive_cold = 0
    hot_threshold = 3  # Curated docs found to be "hot"
    cold_threshold = 3  # Consecutive low-value queries before bouncing

    while query_count < max_queries:
        # Priority: hot_pending > pending > exploration
        if hot_pending:
            current = hot_pending.pop(0)
            yield {"type": "thinking", "text": f"[HOT LEAD: {current}]\n"}
        elif pending:
            current = pending.pop(0)
        elif exploration_index < len(exploration_targets):
            current = exploration_targets[exploration_index]
            exploration_index += 1
            consecutive_cold = 0  # Reset on bounce
            yield {"type": "thinking", "text": f"[EXPLORING: {current}]\n"}
        else:
            break

        if current.lower() in [p.lower() for p in processed]:
            continue

        processed.add(current)
        query_count += 1

        yield {"type": "auto_query", "query": current, "index": query_count, "heat": heat_score}

        # Track this query's heat
        query_curated_count = 0
        query_suggestions = []

        async for event in process_query(current, conversation_id, is_auto=True):
            if event.get("type") == "sources":
                # Count curated docs in sources (13011-13031)
                sources = event.get("ids", [])
                query_curated_count = len([s for s in sources if 13011 <= s <= 13031])

            if event.get("type") == "suggestions":
                query_suggestions = event.get("queries", [])

            yield event

        # Update heat based on results
        if query_curated_count >= hot_threshold:
            # HOT - Found valuable content, prioritize following this thread
            heat_score += query_curated_count
            consecutive_cold = 0
            yield {"type": "thinking", "text": f"[HEAT +{query_curated_count}] Following hot lead...\n"}

            # Add suggestions to hot queue (priority)
            for q in query_suggestions:
                q_lower = q.lower()
                if q_lower not in [p.lower() for p in processed]:
                    if is_investigation_relevant(q):
                        hot_pending.insert(0, q)
                    elif not is_spam_entity(q) and q not in pending:
                        hot_pending.append(q)

        elif query_curated_count > 0:
            # WARM - Some value, add to regular queue
            heat_score += query_curated_count
            consecutive_cold = 0

            for q in query_suggestions:
                q_lower = q.lower()
                if q_lower not in [p.lower() for p in processed] and q not in pending:
                    if is_investigation_relevant(q):
                        pending.insert(0, q)
                    elif not is_spam_entity(q):
                        pending.append(q)

        else:
            # COLD - No value, increment cold counter
            consecutive_cold += 1
            if consecutive_cold >= cold_threshold and not hot_pending:
                # Bounce to new exploration
                yield {"type": "thinking", "text": f"[COLD x{consecutive_cold}] Bouncing to new direction...\n"}
                pending.clear()  # Clear low-value pending items
                consecutive_cold = 0

    yield {"type": "auto_complete", "total_queries": query_count, "explored": exploration_index, "final_heat": heat_score}
