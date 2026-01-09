#!/usr/bin/env python3
"""
Dataset Ingestion with Pipeline-Style Processing for Graph Enrichment

This script processes new datasets using the same multi-step discovery approach
as the conversation bot, but outputs to the graph database instead of generating
responses.

Pipeline steps:
1. Parse input documents (text, json, csv)
2. Extract search terms and entities
3. Cross-reference with existing corpus (discover connections)
4. Build context-enriched extraction prompts
5. Call Haiku for entity/relationship extraction
6. Insert into graph.db with full provenance

Usage:
    python scripts/ingest_dataset.py --input data/new_dataset.json --dry-run
    python scripts/ingest_dataset.py --input data/documents/ --format txt
    python scripts/ingest_dataset.py --input data/intel.csv --format csv --concurrency 10
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import asyncio
import json
import re
import time
import csv
from pathlib import Path

# Increase CSV field size limit for large text fields
csv.field_size_limit(10 * 1024 * 1024)  # 10MB
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional, AsyncGenerator

import httpx

# =============================================================================
# CONFIGURATION
# =============================================================================

BATCH_SIZE = 3  # documents per Haiku call (smaller for richer context)
DEFAULT_CONCURRENCY = 10
MAX_RETRIES = 3
HAIKU_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://lframework:lframework@localhost/lframework")

# SQLite paths (for sources.db only - read-only corpus search)
DB_SOURCES = Path("/opt/rag/db/sources.db")

# =============================================================================
# STOP WORDS (from pipeline.py)
# =============================================================================

STOP_WORDS = {
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare',
    'ought', 'used', 'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by',
    'from', 'as', 'into', 'through', 'during', 'before', 'after', 'above',
    'below', 'between', 'under', 'again', 'further', 'then', 'once',
    'here', 'there', 'when', 'where', 'why', 'how', 'all', 'each', 'few',
    'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only',
    'own', 'same', 'so', 'than', 'too', 'very', 'just', 'and', 'but',
    'if', 'or', 'because', 'until', 'while', 'although', 'though',
    'what', 'which', 'who', 'whom', 'this', 'that', 'these', 'those',
    'tell', 'show', 'find', 'give', 'know', 'about', 'look', 'want',
    'search', 'explain', 'describe', 'list', 'help', 'please',
}

# =============================================================================
# EXTRACTION PROMPT (enriched version with cross-reference context)
# =============================================================================

EXTRACTION_PROMPT = '''You are a forensic data extraction system for OSINT investigation.
Extract ALL entities, relationships, and signals from these documents.

{context_section}

=== ENTITY TYPES ===

CORE:
- person (normalize: "John Smith" not "JOHN SMITH")
- email_address
- phone_number
- company / organization
- location (address, city, country, property)
- amount (keep currency: "$5,000")
- date (ISO: 2003-04-12)
- time

OBJECTS:
- vehicle / aircraft (registration critical: N908JE)
- property (real estate with address)
- document (contract, invoice, report)
- account (bank, crypto, social handle)

EVENTS:
- meeting / flight / trip / party / call / transaction

STATEMENTS (capture exact meaning):
- claim (allegation: "X did Y")
- quote (exact words)
- instruction (request, order)
- plan (future intent)
- denial / threat / secret

FORENSIC SIGNALS:
- code_word (out of context, repeated unusually)
- vague_reference ("the thing", "you know who")
- urgency (ASAP, deadline pressure)
- deletion_request ("delete this")
- cash_mention / offshore_mention

=== OUTPUT FORMAT ===

Return ONLY valid JSON:

{{
  "extractions": [
    {{
      "source_id": "<document_id>",
      "nodes": [
        {{"name": "Jeffrey Epstein", "type": "person"}},
        {{"name": "$50,000", "type": "amount"}},
        {{"name": "massage", "type": "code_word", "context": "appears 3x"}}
      ],
      "edges": [
        {{"from": "Jeffrey Epstein", "to": "$50,000", "type": "paid"}},
        {{"from": "Jeffrey Epstein", "to": "Ghislaine Maxwell", "type": "associated_with"}}
      ],
      "properties": [
        {{"node": "N908JE", "key": "aircraft_type", "value": "Boeing 727"}}
      ],
      "signals": [
        {{"type": "urgency", "detail": "multiple ASAP references"}}
      ],
      "cross_references": [
        {{"entity": "Jeffrey Epstein", "related_emails": [123, 456], "relationship": "sender in emails"}}
      ]
    }}
  ]
}}

=== RULES ===

1. Extract EVERYTHING - mundane details matter
2. Preserve exact wording for claims/quotes/instructions
3. Normalize person names: "John Smith" (not JOHN SMITH)
4. Keep amounts with currency
5. Dates in ISO format
6. NO JUDGMENT - no scores, no opinions
7. For claims: capture WHO said WHAT about WHOM
8. Flag anything deliberately vague or coded
9. Use cross_references to link to existing corpus emails

=== DOCUMENTS TO PROCESS ===

{documents_formatted}
'''

# =============================================================================
# DATABASE HELPERS
# =============================================================================

def get_sqlite_connection(db_path):
    """Get SQLite connection (for sources.db corpus search)"""
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def get_pg_connection():
    """Get PostgreSQL connection for graph/scores/audit"""
    import psycopg2
    import psycopg2.extras
    return psycopg2.connect(DATABASE_URL)


def search_corpus_simple(term: str, limit: int = 10) -> List[Dict]:
    """Simple corpus search for cross-referencing"""
    conn = get_sqlite_connection(DB_SOURCES)
    cursor = conn.cursor()

    # Use FTS if available, fall back to LIKE
    try:
        cursor.execute("""
            SELECT doc_id, subject, sender_email, date_sent,
                   snippet(emails_fts, 0, '', '', '...', 30) as snippet
            FROM emails_fts
            WHERE emails_fts MATCH ?
            LIMIT ?
        """, (term, limit))
        results = [dict(r) for r in cursor.fetchall()]
    except:
        # Fallback to LIKE
        search_pattern = f"%{term}%"
        cursor.execute("""
            SELECT doc_id, subject, sender_email, date_sent,
                   substr(body_text, 1, 200) as snippet
            FROM emails
            WHERE subject LIKE ? OR body_text LIKE ?
            LIMIT ?
        """, (search_pattern, search_pattern, limit))
        results = [dict(r) for r in cursor.fetchall()]

    conn.close()
    return results


def get_processed_documents(dataset_name: str) -> set:
    """Get document IDs already processed for this dataset"""
    conn = get_pg_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT target_id
        FROM evidence_chain
        WHERE target_type = 'document'
        AND reason LIKE %s
        AND action = 'dataset_extracted'
    """, (f'%{dataset_name}%',))

    processed = {str(row[0]) for row in cursor.fetchall()}
    conn.close()
    return processed


# =============================================================================
# PIPELINE-STYLE ENTITY DISCOVERY
# =============================================================================

def extract_search_terms(text: str) -> List[str]:
    """Extract meaningful search terms (like pipeline.py)"""
    # Find quoted phrases
    quoted = re.findall(r'"([^"]+)"', text)

    # Find capitalized words (names)
    caps = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b', text)

    # Get remaining words
    words = [w.lower() for w in re.findall(r'\b([a-zA-Z]{4,})\b', text.lower())
             if w.lower() not in STOP_WORDS]

    terms = quoted + caps + words
    seen = set()
    result = []
    for t in terms:
        tl = t.lower()
        if tl not in seen:
            seen.add(tl)
            result.append(t)

    return result[:8]


def extract_entities_local(text: str) -> Dict[str, List[str]]:
    """Extract entities locally without API (for cross-referencing)"""
    entities = {
        'emails': [],
        'names': [],
        'amounts': [],
        'dates': [],
        'domains': [],
        'phones': []
    }

    # Email addresses
    entities['emails'] = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)

    # Names (two capitalized words)
    names = re.findall(r'\b([A-Z][a-z]{2,15} [A-Z][a-z]{2,15})\b', text)
    skip_names = {'new york', 'los angeles', 'united states', 'virgin islands', 'prime minister'}
    entities['names'] = [n for n in names if n.lower() not in skip_names]

    # Money amounts
    entities['amounts'] = re.findall(r'\$[\d,]+(?:\.\d{2})?|\€[\d,]+(?:\.\d{2})?', text)

    # Dates
    entities['dates'] = re.findall(r'\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b', text)

    # Domains from emails
    for email in entities['emails']:
        domain = email.split('@')[1] if '@' in email else ''
        if domain and domain not in ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com']:
            entities['domains'].append(domain)

    # Phone numbers
    entities['phones'] = re.findall(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', text)

    return entities


def discover_connections(document: Dict[str, Any]) -> Dict[str, Any]:
    """
    Pipeline-style discovery: search corpus for related content.
    Returns context about existing connections.
    """
    connections = {
        'related_emails': [],
        'known_entities': [],
        'timeline_overlap': [],
        'search_trail': []
    }

    content = document.get('content', '') or document.get('body', '') or document.get('text', '')
    if not content:
        return connections

    # Step 1: Extract search terms
    terms = extract_search_terms(content)

    # Step 2: Search corpus for each term
    all_related = []
    for term in terms[:5]:
        results = search_corpus_simple(term, limit=5)
        if results:
            connections['search_trail'].append({
                'term': term,
                'hits': len(results),
                'email_ids': [r['doc_id'] for r in results]
            })
            all_related.extend(results)

    # Step 3: Extract local entities
    entities = extract_entities_local(content)

    # Step 4: Search for people mentioned
    for name in entities['names'][:3]:
        results = search_corpus_simple(name, limit=3)
        if results:
            connections['known_entities'].append({
                'entity': name,
                'type': 'person',
                'in_corpus': True,
                'email_ids': [r['doc_id'] for r in results]
            })

    # Step 5: Search for email domains
    for domain in entities['domains'][:2]:
        domain_term = domain.split('.')[0]
        if len(domain_term) > 3:
            results = search_corpus_simple(domain_term, limit=3)
            if results:
                connections['known_entities'].append({
                    'entity': domain,
                    'type': 'domain',
                    'in_corpus': True,
                    'email_ids': [r['doc_id'] for r in results]
                })

    # Dedupe related emails
    seen_ids = set()
    for r in all_related:
        if r['doc_id'] not in seen_ids:
            seen_ids.add(r['doc_id'])
            connections['related_emails'].append({
                'id': r['doc_id'],
                'subject': r.get('subject', '')[:60],
                'sender': r.get('sender_email', ''),
                'date': str(r.get('date_sent', ''))[:10]
            })

    return connections


# =============================================================================
# DOCUMENT PARSING
# =============================================================================

def parse_json_input(filepath: Path) -> List[Dict[str, Any]]:
    """Parse JSON file (array of documents or single object)"""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if isinstance(data, list):
        return data
    elif isinstance(data, dict):
        # Single document or wrapped array
        if 'documents' in data:
            return data['documents']
        elif 'items' in data:
            return data['items']
        elif 'records' in data:
            return data['records']
        else:
            return [data]
    return []


def parse_csv_input(filepath: Path) -> List[Dict[str, Any]]:
    """Parse CSV file into documents - smart field mapping"""
    documents = []
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []

        # Smart field detection
        content_fields = ['content', 'text', 'body', 'description', 'docketentry_description',
                          'recapdocument_description', 'message', 'note', 'details']
        id_fields = ['id', 'doc_id', 'docketentry_id', 'recapdocument_id', 'document_id', 'entry_id']
        title_fields = ['title', 'subject', 'name', 'headline', 'document_type', 'recapdocument_document_type']
        date_fields = ['date', 'timestamp', 'created_at', 'date_filed', 'docketentry_date_filed',
                       'recapdocument_date_upload', 'filed_date']

        def find_field(candidates):
            for c in candidates:
                if c in fieldnames:
                    return c
            return None

        content_field = find_field(content_fields)
        id_field = find_field(id_fields)
        title_field = find_field(title_fields)
        date_field = find_field(date_fields)

        for i, row in enumerate(reader):
            # Build content from multiple fields if needed
            content_parts = []
            if content_field and row.get(content_field):
                content_parts.append(row.get(content_field))
            # Also grab secondary description fields
            for f in ['recapdocument_description', 'docketentry_description']:
                if f != content_field and f in row and row.get(f):
                    content_parts.append(row.get(f))

            content = ' | '.join(content_parts) if content_parts else ''

            # If still no content, concatenate all non-empty string values
            if not content:
                content = ' '.join(str(v) for v in row.values() if v and isinstance(v, str) and len(str(v)) > 10)

            doc = {
                'id': row.get(id_field, str(i + 1)) if id_field else str(i + 1),
                'content': content,
                'title': row.get(title_field, '') if title_field else '',
                'date': row.get(date_field, '') if date_field else '',
                'source': filepath.name,
                'metadata': {k: v for k, v in row.items() if v and k not in [content_field, id_field, title_field, date_field]}
            }
            documents.append(doc)
    return documents


def parse_text_files(dirpath: Path) -> List[Dict[str, Any]]:
    """Parse directory of text files"""
    documents = []
    for filepath in sorted(dirpath.glob('**/*.txt')):
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        doc = {
            'id': filepath.stem,
            'content': content,
            'title': filepath.name,
            'source': str(filepath.relative_to(dirpath)),
            'metadata': {'filename': filepath.name}
        }
        documents.append(doc)

    # Also parse .eml files
    for filepath in sorted(dirpath.glob('**/*.eml')):
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        doc = {
            'id': filepath.stem,
            'content': content,
            'title': filepath.name,
            'source': str(filepath.relative_to(dirpath)),
            'metadata': {'filename': filepath.name, 'type': 'email'}
        }
        documents.append(doc)

    return documents


def load_documents(input_path: str, format_type: str = 'auto') -> List[Dict[str, Any]]:
    """Load documents from input path"""
    path = Path(input_path)

    if not path.exists():
        raise FileNotFoundError(f"Input not found: {input_path}")

    # Auto-detect format
    if format_type == 'auto':
        if path.is_dir():
            format_type = 'txt'
        elif path.suffix == '.json':
            format_type = 'json'
        elif path.suffix == '.csv':
            format_type = 'csv'
        else:
            format_type = 'txt'

    if format_type == 'json':
        return parse_json_input(path)
    elif format_type == 'csv':
        return parse_csv_input(path)
    elif format_type == 'txt':
        if path.is_dir():
            return parse_text_files(path)
        else:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            return [{'id': path.stem, 'content': content, 'title': path.name}]
    else:
        raise ValueError(f"Unknown format: {format_type}")


# =============================================================================
# HAIKU API
# =============================================================================

class RateLimitError(Exception):
    pass


async def call_haiku_extract(documents: List[Dict[str, Any]], context: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Call Haiku with enriched context"""
    if not HAIKU_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set")

    # Format documents
    docs_formatted = []
    for doc in documents:
        content = doc.get('content', '') or doc.get('body', '') or doc.get('text', '')
        content = content[:3000]  # Limit content size

        docs_formatted.append(f"""
---
Document ID: {doc.get('id', 'unknown')}
Title: {doc.get('title', '(no title)')}
Date: {doc.get('date', 'N/A')}
Source: {doc.get('source', 'N/A')}

Content:
{content}
---
""")

    # Format context section (cross-references)
    context_lines = []
    for ctx in context:
        if ctx.get('related_emails'):
            context_lines.append("=== CROSS-REFERENCES FROM EXISTING CORPUS ===")
            for email in ctx['related_emails'][:5]:
                context_lines.append(f"  Email #{email['id']}: {email['subject']} (from {email['sender']}, {email['date']})")

        if ctx.get('known_entities'):
            context_lines.append("\n=== KNOWN ENTITIES (already in graph) ===")
            for ent in ctx['known_entities']:
                context_lines.append(f"  {ent['type'].upper()}: {ent['entity']} (appears in {len(ent.get('email_ids', []))} emails)")

    context_section = '\n'.join(context_lines) if context_lines else "(No existing cross-references found)"

    prompt = EXTRACTION_PROMPT.format(
        context_section=context_section,
        documents_formatted='\n'.join(docs_formatted)
    )

    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": HAIKU_API_KEY,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json={
                        "model": "claude-3-5-haiku-20241022",
                        "max_tokens": 4096,
                        "messages": [{"role": "user", "content": prompt}]
                    }
                )

                if response.status_code == 429:
                    raise RateLimitError("API rate limit (429)")

                response.raise_for_status()
                data = response.json()

                content = data.get("content", [])
                usage = data.get("usage", {})

                if content and isinstance(content, list):
                    text = content[0].get("text", "")
                    tokens_in = usage.get("input_tokens", 0)
                    tokens_out = usage.get("output_tokens", 0)
                    cost_usd = (tokens_in * 0.80 / 1_000_000) + (tokens_out * 4.00 / 1_000_000)

                    return {
                        "text": text,
                        "usage": usage,
                        "cost_usd": cost_usd
                    }

                return {"error": "Invalid response format"}

        except RateLimitError:
            raise
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                return {"error": f"Failed after {MAX_RETRIES} attempts: {e}"}

    return {"error": "Unknown error"}


# =============================================================================
# GRAPH INSERTION (from enrich_graph.py)
# =============================================================================

def safe_db_value(value: Any) -> str:
    """Convert any value to safe database string"""
    if value is None:
        return ''
    if isinstance(value, str):
        return value
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return str(value)


def insert_nodes(nodes: List[Dict], source_id: str, source_type: str = 'document', dry_run: bool = False) -> Dict[str, int]:
    """Insert nodes into PostgreSQL graph database"""
    if dry_run:
        return {safe_db_value(n.get('name', '')): i for i, n in enumerate(nodes, 1)}

    conn = get_pg_connection()
    cursor = conn.cursor()
    node_id_map = {}

    for node in nodes:
        name = safe_db_value(node.get('name'))
        node_type = safe_db_value(node.get('type', 'unknown'))
        context = safe_db_value(node.get('context', ''))

        if not name:
            continue

        name_normalized = name.lower().strip()

        # Check exists
        cursor.execute("SELECT id FROM nodes WHERE name = %s AND type = %s", (name, node_type))
        existing = cursor.fetchone()

        if existing:
            node_id = existing[0]
        else:
            cursor.execute("""
                INSERT INTO nodes (type, name, name_normalized, source_db, created_by)
                VALUES (%s, %s, %s, %s, 'dataset_ingest')
                RETURNING id
            """, (node_type, name, name_normalized, source_type))
            node_id = cursor.fetchone()[0]

        node_id_map[name] = node_id

        if context:
            cursor.execute("""
                INSERT INTO properties (node_id, key, value, created_by)
                VALUES (%s, 'context', %s, 'dataset_ingest')
            """, (node_id, context))

    conn.commit()
    conn.close()
    return node_id_map


def insert_edges(edges: List[Dict], node_id_map: Dict[str, int], source_id: str, dry_run: bool = False) -> int:
    """Insert edges into PostgreSQL graph database"""
    if dry_run:
        return len(edges)

    conn = get_pg_connection()
    cursor = conn.cursor()
    inserted = 0

    for edge in edges:
        from_name = safe_db_value(edge.get('from'))
        to_name = safe_db_value(edge.get('to'))
        edge_type = safe_db_value(edge.get('type', 'related_to'))

        if not from_name or not to_name:
            continue

        from_id = node_id_map.get(from_name)
        to_id = node_id_map.get(to_name)

        # Create missing nodes
        if not from_id:
            cursor.execute("""
                INSERT INTO nodes (type, name, name_normalized, source_db, created_by)
                VALUES ('unknown', %s, %s, 'document', 'dataset_ingest')
                RETURNING id
            """, (from_name, from_name.lower().strip()))
            from_id = cursor.fetchone()[0]
            node_id_map[from_name] = from_id

        if not to_id:
            cursor.execute("""
                INSERT INTO nodes (type, name, name_normalized, source_db, created_by)
                VALUES ('unknown', %s, %s, 'document', 'dataset_ingest')
                RETURNING id
            """, (to_name, to_name.lower().strip()))
            to_id = cursor.fetchone()[0]
            node_id_map[to_name] = to_id

        try:
            cursor.execute("""
                INSERT INTO edges (from_node_id, to_node_id, type, directed, created_by)
                VALUES (%s, %s, %s, true, 'dataset_ingest')
            """, (from_id, to_id, edge_type))
            inserted += 1
        except:
            conn.rollback()

    conn.commit()
    conn.close()
    return inserted


def insert_properties(properties: List[Dict], node_id_map: Dict[str, int], source_id: str, dry_run: bool = False) -> int:
    """Insert properties into PostgreSQL graph database"""
    if dry_run:
        return len(properties)

    conn = get_pg_connection()
    cursor = conn.cursor()
    inserted = 0

    for prop in properties:
        node_name = safe_db_value(prop.get('node'))
        key = safe_db_value(prop.get('key'))
        value = safe_db_value(prop.get('value'))

        if not node_name or not key or not value:
            continue

        node_id = node_id_map.get(node_name)
        if not node_id:
            continue

        try:
            cursor.execute("""
                INSERT INTO properties (node_id, key, value, created_by)
                VALUES (%s, %s, %s, 'dataset_ingest')
            """, (node_id, key, value))
            inserted += 1
        except:
            conn.rollback()

    conn.commit()
    conn.close()
    return inserted


def insert_signals(signals: List[Dict], source_id: str, dry_run: bool = False) -> int:
    """Insert signals as flags into PostgreSQL"""
    if dry_run:
        return len(signals)

    conn = get_pg_connection()
    cursor = conn.cursor()
    inserted = 0

    for signal in signals:
        signal_type = safe_db_value(signal.get('type', 'unknown'))
        detail = safe_db_value(signal.get('detail', ''))

        try:
            cursor.execute("""
                INSERT INTO flags (target_type, target_id, flag_type, description, severity, created_by)
                VALUES ('document', %s, %s, %s, 0, 'dataset_ingest')
            """, (source_id, signal_type, detail))
            inserted += 1
        except:
            conn.rollback()

    conn.commit()
    conn.close()
    return inserted


def insert_cross_references(cross_refs: List[Dict], node_id_map: Dict[str, int], source_id: str, dry_run: bool = False) -> int:
    """Insert cross-references as edges to existing emails (PostgreSQL)"""
    if dry_run:
        return len(cross_refs)

    conn = get_pg_connection()
    cursor = conn.cursor()
    inserted = 0

    for xref in cross_refs:
        entity_name = safe_db_value(xref.get('entity'))
        email_ids = xref.get('related_emails', [])
        relationship = safe_db_value(xref.get('relationship', 'mentioned_in'))

        entity_id = node_id_map.get(entity_name)
        if not entity_id:
            continue

        for email_id in email_ids[:5]:  # Limit cross-refs
            try:
                cursor.execute("""
                    INSERT INTO edges (from_node_id, to_node_id, type, directed, excerpt, created_by)
                    VALUES (%s, %s, 'cross_reference', true, %s, 'dataset_ingest')
                """, (entity_id, email_id, f"Email #{email_id}: {relationship}"))
                inserted += 1
            except:
                conn.rollback()

    conn.commit()
    conn.close()
    return inserted


def log_extraction(source_id: str, dataset_name: str, stats: Dict, dry_run: bool = False):
    """Log extraction to PostgreSQL audit trail"""
    if dry_run:
        return

    conn = get_pg_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO evidence_chain (target_type, target_id, action, new_value, reason, created_by)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            'document',
            source_id,
            'dataset_extracted',
            json.dumps(stats),
            f'Dataset ingestion: {dataset_name}',
            'dataset_ingest'
        ))
        conn.commit()
    except:
        conn.rollback()

    conn.close()


# =============================================================================
# BATCH PROCESSING
# =============================================================================

def parse_extraction_result(result: Dict, doc_ids: List[str]) -> Tuple[Optional[Dict], Optional[str]]:
    """Parse Haiku JSON response"""
    if "error" in result:
        return None, result["error"]

    try:
        text = result.get("text", "").strip()

        # Remove markdown fences
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join([l for l in lines if not l.startswith("```")])

        # Find JSON
        json_start = text.find("{")
        json_end = text.rfind("}") + 1

        if json_start >= 0 and json_end > json_start:
            json_text = text[json_start:json_end]
            data = json.loads(json_text)
            return data, None
        else:
            return None, "No JSON found"

    except json.JSONDecodeError as e:
        return None, f"JSON parse error: {e}"
    except Exception as e:
        return None, f"Parse error: {e}"


async def process_batch(
    documents: List[Dict[str, Any]],
    dataset_name: str,
    dry_run: bool = False
) -> Dict[str, Any]:
    """Process a batch of documents with pipeline-style discovery"""

    batch_stats = {
        'documents': len(documents),
        'nodes': 0,
        'edges': 0,
        'properties': 0,
        'signals': 0,
        'cross_refs': 0,
        'cost_usd': 0.0,
        'errors': []
    }

    doc_ids = [str(d.get('id', i)) for i, d in enumerate(documents)]
    print(f"\n  Processing batch: {doc_ids}")

    # Step 1: Discover connections for each document
    print(f"    [1/3] Discovering cross-references...")
    contexts = []
    for doc in documents:
        ctx = discover_connections(doc)
        contexts.append(ctx)
        if ctx['related_emails']:
            print(f"      Doc {doc.get('id')}: {len(ctx['related_emails'])} related emails, {len(ctx['known_entities'])} known entities")

    # Step 2: Call Haiku with enriched context
    print(f"    [2/3] Extracting entities via Haiku...")
    result = await call_haiku_extract(documents, contexts)

    if "error" in result:
        print(f"    ERROR: {result['error']}")
        batch_stats['errors'].append(result['error'])
        return batch_stats

    batch_stats['cost_usd'] = result.get('cost_usd', 0.0)
    print(f"    Haiku: ${batch_stats['cost_usd']:.4f}")

    # Step 3: Parse and insert
    print(f"    [3/3] Inserting into graph...")
    data, error = parse_extraction_result(result, doc_ids)

    if error:
        print(f"    Parse error: {error}")
        batch_stats['errors'].append(error)
        return batch_stats

    extractions = data.get('extractions', [])
    if not extractions:
        print(f"    No extractions returned")
        return batch_stats

    for extraction in extractions:
        source_id = str(extraction.get('source_id', ''))

        nodes = extraction.get('nodes', [])
        edges = extraction.get('edges', [])
        properties = extraction.get('properties', [])
        signals = extraction.get('signals', [])
        cross_refs = extraction.get('cross_references', [])

        if dry_run:
            print(f"      [DRY-RUN] Doc {source_id}: {len(nodes)} nodes, {len(edges)} edges, {len(signals)} signals")
        else:
            node_id_map = insert_nodes(nodes, source_id, 'document', dry_run)
            edges_count = insert_edges(edges, node_id_map, source_id, dry_run)
            props_count = insert_properties(properties, node_id_map, source_id, dry_run)
            signals_count = insert_signals(signals, source_id, dry_run)
            xref_count = insert_cross_references(cross_refs, node_id_map, source_id, dry_run)

            batch_stats['nodes'] += len(nodes)
            batch_stats['edges'] += edges_count
            batch_stats['properties'] += props_count
            batch_stats['signals'] += signals_count
            batch_stats['cross_refs'] += xref_count

            print(f"      Doc {source_id}: +{len(nodes)} nodes, +{edges_count} edges, +{xref_count} cross-refs")

            log_extraction(source_id, dataset_name, {
                'nodes': len(nodes),
                'edges': edges_count,
                'properties': props_count,
                'signals': signals_count,
                'cross_refs': xref_count
            }, dry_run)

    return batch_stats


# =============================================================================
# MAIN
# =============================================================================

async def main(
    input_path: str,
    format_type: str = 'auto',
    limit: Optional[int] = None,
    dry_run: bool = False,
    resume: bool = True,
    batch_size: int = BATCH_SIZE,
    concurrency: int = DEFAULT_CONCURRENCY
):
    """Main ingestion pipeline"""

    print("=" * 80)
    print("DATASET INGESTION - Pipeline-Style Graph Enrichment")
    print("=" * 80)

    if dry_run:
        print("\n[DRY-RUN MODE - No data will be inserted]\n")

    # Load documents
    print(f"\nLoading documents from: {input_path}")
    documents = load_documents(input_path, format_type)

    if not documents:
        print("No documents found")
        return

    dataset_name = Path(input_path).stem
    print(f"Dataset: {dataset_name}")
    print(f"Documents loaded: {len(documents)}")

    # Filter already processed (resume)
    if resume:
        processed = get_processed_documents(dataset_name)
        if processed:
            documents = [d for d in documents if str(d.get('id', '')) not in processed]
            print(f"After resume filter: {len(documents)} remaining")

    if limit:
        documents = documents[:limit]
        print(f"Limited to: {len(documents)}")

    if not documents:
        print("No documents to process")
        return

    # Split into batches
    batches = [documents[i:i + batch_size] for i in range(0, len(documents), batch_size)]
    print(f"Batches: {len(batches)} (size {batch_size})")
    print(f"Concurrency: {concurrency}")

    # Process
    semaphore = asyncio.Semaphore(concurrency)
    total_stats = {
        'documents': 0,
        'nodes': 0,
        'edges': 0,
        'properties': 0,
        'signals': 0,
        'cross_refs': 0,
        'cost_usd': 0.0,
        'errors': []
    }
    stats_lock = asyncio.Lock()
    completed = 0

    async def process_with_semaphore(batch_idx: int, batch: List[Dict]):
        nonlocal completed
        async with semaphore:
            print(f"\n[Batch {batch_idx + 1}/{len(batches)}]")

            try:
                stats = await process_batch(batch, dataset_name, dry_run)

                async with stats_lock:
                    for key in ['documents', 'nodes', 'edges', 'properties', 'signals', 'cross_refs', 'cost_usd']:
                        total_stats[key] += stats.get(key, 0)
                    total_stats['errors'].extend(stats.get('errors', []))
                    completed += 1

                print(f"  Batch {batch_idx + 1} complete ({completed}/{len(batches)})")
                return stats

            except RateLimitError:
                await asyncio.sleep(5)
                return await process_batch(batch, dataset_name, dry_run)
            except Exception as e:
                print(f"  Batch {batch_idx + 1} failed: {e}")
                async with stats_lock:
                    total_stats['errors'].append(str(e))
                return {}

    start_time = time.time()

    tasks = [process_with_semaphore(i, batch) for i, batch in enumerate(batches)]
    await asyncio.gather(*tasks, return_exceptions=True)

    elapsed = time.time() - start_time

    # Report
    print("\n" + "=" * 80)
    print("INGESTION COMPLETE")
    print("=" * 80)
    print(f"\nDocuments processed: {total_stats['documents']}")
    print(f"Nodes created:       {total_stats['nodes']}")
    print(f"Edges created:       {total_stats['edges']}")
    print(f"Properties:          {total_stats['properties']}")
    print(f"Signals:             {total_stats['signals']}")
    print(f"Cross-references:    {total_stats['cross_refs']}")
    print(f"\nEstimated cost:      ${total_stats['cost_usd']:.4f}")
    print(f"Time elapsed:        {elapsed:.1f}s")

    if total_stats['errors']:
        print(f"\nErrors: {len(total_stats['errors'])}")
        for err in total_stats['errors'][:5]:
            print(f"  - {err}")

    if dry_run:
        print("\n[DRY-RUN - No data was inserted]")

    print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingest dataset with pipeline-style processing for graph enrichment"
    )
    parser.add_argument("--input", "-i", required=True, help="Input file or directory")
    parser.add_argument("--format", "-f", default="auto", choices=['auto', 'json', 'csv', 'txt'],
                        help="Input format (default: auto-detect)")
    parser.add_argument("--limit", "-l", type=int, help="Max documents to process")
    parser.add_argument("--dry-run", action="store_true", help="Don't insert, just show what would happen")
    parser.add_argument("--no-resume", action="store_true", help="Reprocess all documents")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE, help=f"Docs per batch (default: {BATCH_SIZE})")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY,
                        help=f"Parallel API calls (default: {DEFAULT_CONCURRENCY})")

    args = parser.parse_args()

    try:
        asyncio.run(main(
            input_path=args.input,
            format_type=args.format,
            limit=args.limit,
            dry_run=args.dry_run,
            resume=not args.no_resume,
            batch_size=args.batch_size,
            concurrency=args.concurrency
        ))
    except KeyboardInterrupt:
        print("\n\nInterrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\nFatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
