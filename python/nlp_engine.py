#!/usr/bin/env python3
"""
HybridCore NLP Engine - Entity Extraction & Pattern Analysis
Uses regex patterns + heuristics for zero-cost NLP
"""

import re
import json
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import List, Dict, Tuple
from collections import defaultdict

# ═══════════════════════════════════════════════════════════════════
# REGEX PATTERNS - The Heart of Pattern Matching
# ═══════════════════════════════════════════════════════════════════

PATTERNS = {
    # Emails with flexible TLDs
    'email': re.compile(
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        re.IGNORECASE
    ),

    # Phone numbers (international formats)
    'phone': re.compile(
        r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{2,4}[-.\s]?\d{2,4}',
        re.IGNORECASE
    ),

    # URLs with protocols
    'url': re.compile(
        r'https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)',
        re.IGNORECASE
    ),

    # IP addresses (v4)
    'ip_address': re.compile(
        r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'
    ),

    # Dates (multiple formats)
    'date': re.compile(
        r'\b(?:\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4})\b',
        re.IGNORECASE
    ),

    # Currency amounts
    'currency': re.compile(
        r'[$€£¥]\s*\d+(?:[.,]\d{2,3})*(?:[.,]\d{2})?|\d+(?:[.,]\d{3})*(?:[.,]\d{2})?\s*(?:USD|EUR|GBP|BTC|ETH)',
        re.IGNORECASE
    ),

    # Crypto addresses (BTC, ETH)
    'crypto_btc': re.compile(r'\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b'),
    'crypto_eth': re.compile(r'\b0x[a-fA-F0-9]{40}\b'),

    # Social handles
    'twitter': re.compile(r'@[A-Za-z0-9_]{1,15}\b'),
    'hashtag': re.compile(r'#[A-Za-z0-9_]+\b'),

    # Code patterns
    'function_call': re.compile(r'\b[a-zA-Z_][a-zA-Z0-9_]*\s*\([^)]*\)'),
    'variable': re.compile(r'\b(?:let|const|var|def|fn|func)\s+([a-zA-Z_][a-zA-Z0-9_]*)'),

    # Person names (simple heuristic: capitalized words)
    'potential_name': re.compile(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b'),

    # Organizations (Inc, Corp, Ltd, etc.)
    'organization': re.compile(
        r'\b[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*)*\s+(?:Inc|Corp|LLC|Ltd|GmbH|SA|SAS|SARL|Co|Company|Foundation|Institute|University|Association)\b',
        re.IGNORECASE
    ),
}

# ═══════════════════════════════════════════════════════════════════
# ENTITY EXTRACTION
# ═══════════════════════════════════════════════════════════════════

def extract_entities(text: str) -> Dict[str, List[Dict]]:
    """Extract all entities from text using regex patterns"""
    entities = defaultdict(list)

    for entity_type, pattern in PATTERNS.items():
        for match in pattern.finditer(text):
            entity = {
                'value': match.group(),
                'start': match.start(),
                'end': match.end(),
                'confidence': calculate_confidence(entity_type, match.group())
            }
            # Deduplicate
            if entity not in entities[entity_type]:
                entities[entity_type].append(entity)

    return dict(entities)


def calculate_confidence(entity_type: str, value: str) -> float:
    """Calculate confidence score based on pattern specificity"""
    base_confidence = {
        'email': 0.95,
        'url': 0.95,
        'ip_address': 0.99,
        'crypto_btc': 0.90,
        'crypto_eth': 0.95,
        'phone': 0.70,
        'date': 0.80,
        'currency': 0.85,
        'twitter': 0.90,
        'hashtag': 0.95,
        'potential_name': 0.50,
        'organization': 0.60,
        'function_call': 0.75,
        'variable': 0.80,
    }
    return base_confidence.get(entity_type, 0.5)


# ═══════════════════════════════════════════════════════════════════
# TEXT ANALYSIS
# ═══════════════════════════════════════════════════════════════════

def analyze_text(text: str) -> Dict:
    """Full text analysis with statistics and entities"""
    # Basic stats
    words = text.split()
    sentences = re.split(r'[.!?]+', text)

    # Entity extraction
    entities = extract_entities(text)

    # Keyword extraction (simple TF approach)
    word_freq = defaultdict(int)
    stopwords = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                 'would', 'could', 'should', 'may', 'might', 'must', 'shall',
                 'can', 'need', 'dare', 'ought', 'used', 'to', 'of', 'in',
                 'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into',
                 'through', 'during', 'before', 'after', 'above', 'below',
                 'between', 'under', 'again', 'further', 'then', 'once',
                 'and', 'but', 'or', 'nor', 'so', 'yet', 'both', 'either',
                 'neither', 'not', 'only', 'own', 'same', 'than', 'too',
                 'very', 'just', 'also', 'now', 'here', 'there', 'when',
                 'where', 'why', 'how', 'all', 'each', 'every', 'both',
                 'few', 'more', 'most', 'other', 'some', 'such', 'no',
                 'any', 'this', 'that', 'these', 'those', 'i', 'you', 'he',
                 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them'}

    for word in words:
        clean_word = re.sub(r'[^\w]', '', word.lower())
        if clean_word and clean_word not in stopwords and len(clean_word) > 2:
            word_freq[clean_word] += 1

    keywords = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:20]

    # Language detection (simple heuristic)
    french_words = {'le', 'la', 'les', 'de', 'du', 'des', 'un', 'une', 'et', 'est', 'sont', 'avec', 'pour', 'dans', 'sur', 'ce', 'cette', 'ces'}
    english_words = {'the', 'is', 'are', 'and', 'or', 'but', 'for', 'with', 'this', 'that', 'have', 'has'}

    text_lower = text.lower()
    fr_count = sum(1 for w in french_words if f' {w} ' in f' {text_lower} ')
    en_count = sum(1 for w in english_words if f' {w} ' in f' {text_lower} ')

    lang = 'fr' if fr_count > en_count else 'en'

    return {
        'stats': {
            'char_count': len(text),
            'word_count': len(words),
            'sentence_count': len([s for s in sentences if s.strip()]),
            'avg_word_length': sum(len(w) for w in words) / max(len(words), 1),
            'language': lang
        },
        'entities': entities,
        'entity_counts': {k: len(v) for k, v in entities.items()},
        'keywords': [{'word': w, 'count': c} for w, c in keywords],
    }


# ═══════════════════════════════════════════════════════════════════
# RELATIONSHIP EXTRACTION
# ═══════════════════════════════════════════════════════════════════

def extract_relationships(text: str, entities: Dict) -> List[Dict]:
    """Extract relationships between entities based on proximity"""
    relationships = []

    # Get all entities with positions
    all_entities = []
    for entity_type, items in entities.items():
        for item in items:
            all_entities.append({
                'type': entity_type,
                'value': item['value'],
                'start': item['start'],
                'end': item['end']
            })

    # Sort by position
    all_entities.sort(key=lambda x: x['start'])

    # Find co-occurring entities (within 100 chars)
    for i, e1 in enumerate(all_entities):
        for e2 in all_entities[i+1:]:
            distance = e2['start'] - e1['end']
            if distance > 200:
                break
            if distance > 0:
                # Extract context between entities
                context = text[e1['end']:e2['start']].strip()

                # Detect relationship type from context
                rel_type = detect_relationship(context)

                if rel_type:
                    relationships.append({
                        'from': {'type': e1['type'], 'value': e1['value']},
                        'to': {'type': e2['type'], 'value': e2['value']},
                        'relationship': rel_type,
                        'context': context[:50],
                        'distance': distance
                    })

    return relationships


def detect_relationship(context: str) -> str:
    """Detect relationship type from context using patterns"""
    context_lower = context.lower()

    patterns = {
        'works_at': r'\b(?:works?\s+(?:at|for)|employed\s+(?:at|by)|(?:is|was)\s+(?:at|with))\b',
        'located_in': r'\b(?:(?:is|are|was|were)\s+(?:in|at|from)|based\s+in|located\s+in)\b',
        'contacted': r'\b(?:contact(?:ed)?|reach(?:ed)?|call(?:ed)?|email(?:ed)?)\b',
        'sent_to': r'\b(?:sent?\s+to|forward(?:ed)?\s+to|cc[:\s]|bcc[:\s])\b',
        'received_from': r'\b(?:from|received\s+from|got\s+from)\b',
        'mentions': r'\b(?:mention(?:ed|s)?|refer(?:red|s)?\s+to|about)\b',
        'owns': r'\b(?:owns?|has|possesses?|belongs?\s+to)\b',
        'created_by': r'\b(?:created?\s+by|made\s+by|authored?\s+by|written\s+by)\b',
    }

    for rel_type, pattern in patterns.items():
        if re.search(pattern, context_lower):
            return rel_type

    return 'associated_with' if len(context) < 50 else None


# ═══════════════════════════════════════════════════════════════════
# HTTP SERVER
# ═══════════════════════════════════════════════════════════════════

class NLPHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Silent logging

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def do_GET(self):
        if self.path == '/health':
            self._send_json({
                'status': 'healthy',
                'service': 'nlp-engine',
                'patterns': len(PATTERNS)
            })
        else:
            self._send_json({'error': 'Not found'}, 404)

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')

        try:
            data = json.loads(body)
            text = data.get('text', '')

            if self.path == '/extract':
                entities = extract_entities(text)
                self._send_json({'entities': entities})

            elif self.path == '/analyze':
                analysis = analyze_text(text)
                self._send_json(analysis)

            elif self.path == '/relationships':
                entities = extract_entities(text)
                relationships = extract_relationships(text, entities)
                self._send_json({
                    'entities': entities,
                    'relationships': relationships
                })

            else:
                self._send_json({'error': 'Unknown endpoint'}, 404)

        except Exception as e:
            self._send_json({'error': str(e)}, 500)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()


def main():
    host = '127.0.0.1'
    port = 8003

    print(f"""
╔═══════════════════════════════════════════════════════════╗
║        HybridCore NLP Engine - Pattern Analysis           ║
║        {len(PATTERNS)} regex patterns loaded                          ║
╠═══════════════════════════════════════════════════════════╣
║  Endpoints:                                               ║
║    POST /extract      - Extract entities                  ║
║    POST /analyze      - Full text analysis                ║
║    POST /relationships - Entity relationships             ║
║    GET  /health       - Health check                      ║
╚═══════════════════════════════════════════════════════════╝
    """)

    server = HTTPServer((host, port), NLPHandler)
    print(f"[NLP] Server running on http://{host}:{port}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[NLP] Shutting down...")
        server.shutdown()


if __name__ == '__main__':
    main()
