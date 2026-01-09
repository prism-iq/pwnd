#!/opt/rag/venv/bin/python3
"""
Enrich graph using local Phi-3 LLM with L's investigative style
Processes documents and extracts entities/relationships into PostgreSQL
"""

import os
import sys
import json
import time
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from pathlib import Path
from datetime import datetime

# Load env
env_file = Path("/opt/rag/.env")
for line in env_file.read_text().splitlines():
    if '=' in line and not line.startswith('#'):
        k, v = line.split('=', 1)
        os.environ.setdefault(k, v)

DATABASE_URL = os.environ.get('DATABASE_URL')
PHI3_URL = "http://127.0.0.1:8001"

# L's investigative extraction prompt
L_SYSTEM_PROMPT = """You are L, the detective. Brilliant. Obsessive about truth and patterns.

When analyzing documents, you notice:
- Names that appear too often or too rarely
- Amounts that don't add up
- Dates that cluster suspiciously
- Locations that connect people
- Relationships hidden in plain text
- The things people DON'T say

Extract EVERYTHING. Every name. Every place. Every date. Every amount.
A good detective misses nothing."""


def get_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def get_unprocessed_docs(source_id=2, limit=100, offset=0):
    """Get docs that need entity extraction"""
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT d.id, d.filename, d.doc_type,
               LEFT(c.full_text, 2500) as text_preview
        FROM documents d
        JOIN contents c ON d.id = c.doc_id
        WHERE d.source_id = %s
        AND d.status = 'indexed'
        ORDER BY d.id
        LIMIT %s OFFSET %s
    """, (source_id, limit, offset))

    docs = cur.fetchall()
    conn.close()
    return docs


def get_processed_count(source_id=2):
    """Count docs that have been enriched"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(DISTINCT source_id)
        FROM nodes
        WHERE created_by = 'phi3_enrich'
        AND source_id IN (SELECT id FROM documents WHERE source_id = %s)
    """, (source_id,))
    result = cur.fetchone()
    conn.close()
    return result['count'] if result else 0


def normalize_name(s):
    """Normalize entity name for deduplication"""
    import re
    return re.sub(r'[^a-z0-9\s]', '', s.lower()).strip()


def extract_with_phi3(text):
    """Call Phi-3 for entity extraction"""
    try:
        resp = requests.post(
            f"{PHI3_URL}/extract/entities",
            json={"text": text},
            timeout=300  # 5 minutes for slow CPU inference
        )
        if resp.ok:
            data = resp.json()
            return data.get('entities', [])
        else:
            print(f"  Phi-3 HTTP {resp.status_code}")
    except requests.exceptions.Timeout:
        print(f"  Phi-3 timeout (>300s)")
    except Exception as e:
        print(f"  Phi-3 error: {e}")
    return []


def extract_relationships_phi3(text):
    """Call Phi-3 for relationship extraction"""
    try:
        resp = requests.post(
            f"{PHI3_URL}/extract/relationships",
            json={"text": text},
            timeout=300  # 5 minutes for slow CPU inference
        )
        if resp.ok:
            data = resp.json()
            return data.get('relationships', [])
        else:
            print(f"  Phi-3 rel HTTP {resp.status_code}")
    except requests.exceptions.Timeout:
        print(f"  Phi-3 rel timeout (>300s)")
    except Exception as e:
        print(f"  Phi-3 rel error: {e}")
    return []


def save_entities(doc_id, entities):
    """Save extracted entities to nodes table"""
    if not entities:
        return 0

    conn = get_conn()
    cur = conn.cursor()
    added = 0

    for ent in entities:
        name = ent.get('name', '').strip()
        etype = ent.get('type', 'unknown')
        confidence = ent.get('confidence', 50)

        if not name or len(name) < 2:
            continue

        norm = normalize_name(name)
        if not norm or len(norm) < 2:
            continue

        # Map entity types
        type_map = {
            'person': 'person',
            'organization': 'organization',
            'location': 'location',
            'event': 'event',
            'document': 'document',
            'concept': 'concept',
            'asset': 'amount',
            'communication': 'communication',
            'company': 'organization',
            'date': 'date',
            'amount': 'amount',
            'email': 'email',
            'phone': 'phone',
        }
        etype = type_map.get(etype, etype)

        # Check if exists
        cur.execute(
            "SELECT id FROM nodes WHERE type=%s AND name_normalized=%s",
            (etype, norm)
        )
        existing = cur.fetchone()

        if not existing:
            cur.execute("""
                INSERT INTO nodes (type, name, name_normalized, source_id, created_at, created_by)
                VALUES (%s, %s, %s, %s, NOW(), 'phi3_enrich')
                RETURNING id
            """, (etype, name, norm, doc_id))
            added += 1

    conn.commit()
    conn.close()
    return added


def save_relationships(doc_id, relationships, entities):
    """Save extracted relationships to edges table"""
    if not relationships:
        return 0

    conn = get_conn()
    cur = conn.cursor()
    added = 0

    # Build entity name -> id map
    entity_map = {}
    for ent in entities:
        name = ent.get('name', '').strip()
        norm = normalize_name(name)
        if norm:
            cur.execute(
                "SELECT id FROM nodes WHERE name_normalized=%s LIMIT 1",
                (norm,)
            )
            result = cur.fetchone()
            if result:
                entity_map[norm] = result['id']

    for rel in relationships:
        from_name = normalize_name(rel.get('from', ''))
        to_name = normalize_name(rel.get('to', ''))
        rel_type = rel.get('type', 'related_to')
        context = rel.get('context', '')[:500]

        from_id = entity_map.get(from_name)
        to_id = entity_map.get(to_name)

        if from_id and to_id and from_id != to_id:
            # Check if edge exists
            cur.execute("""
                SELECT id FROM edges
                WHERE from_node_id=%s AND to_node_id=%s AND type=%s
            """, (from_id, to_id, rel_type))

            if not cur.fetchone():
                cur.execute("""
                    INSERT INTO edges (from_node_id, to_node_id, type, source_node_id, excerpt, created_at, created_by)
                    VALUES (%s, %s, %s, %s, %s, NOW(), 'phi3_enrich')
                """, (from_id, to_id, rel_type, doc_id, context))
                added += 1

    conn.commit()
    conn.close()
    return added


def process_document(doc):
    """Process a single document"""
    doc_id = doc['id']
    text = doc['text_preview'] or ''

    if len(text.strip()) < 50:
        return 0, 0

    # Extract entities
    entities = extract_with_phi3(text)
    nodes_added = save_entities(doc_id, entities)

    # Extract relationships (only if we have entities)
    edges_added = 0
    if entities and len(entities) >= 2:
        relationships = extract_relationships_phi3(text)
        edges_added = save_relationships(doc_id, relationships, entities)

    return nodes_added, edges_added


def main(source_id=2, limit=10000, batch_size=10):
    """Main enrichment loop"""

    print(f"=== L Investigation Graph Enrichment ===")
    print(f"Using Phi-3 local LLM at {PHI3_URL}")
    print()

    # Check Phi-3 is running
    try:
        health = requests.get(f"{PHI3_URL}/health", timeout=5).json()
        if not health.get('model_loaded'):
            print("ERROR: Phi-3 model not loaded!")
            return
        print(f"Phi-3 status: {health}")
    except Exception as e:
        print(f"ERROR: Cannot connect to Phi-3: {e}")
        return

    # Get total docs
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM documents WHERE source_id=%s", (source_id,))
    total_docs = cur.fetchone()['count']
    conn.close()

    print(f"Total documents in source {source_id}: {total_docs}")
    print()

    total_nodes = 0
    total_edges = 0
    processed = 0
    offset = 0

    start_time = time.time()

    while processed < limit:
        docs = get_unprocessed_docs(source_id, batch_size, offset)

        if not docs:
            break

        for doc in docs:
            doc_id = doc['id']
            filename = doc['filename']

            nodes, edges = process_document(doc)
            total_nodes += nodes
            total_edges += edges
            processed += 1

            # Progress
            elapsed = time.time() - start_time
            rate = processed / elapsed if elapsed > 0 else 0
            eta = (limit - processed) / rate if rate > 0 else 0

            print(f"[{processed}/{min(limit, total_docs)}] {filename}: +{nodes} nodes, +{edges} edges (ETA: {int(eta)}s)")

        offset += batch_size

        # Small delay to not overload Phi-3
        time.sleep(0.5)

    elapsed = time.time() - start_time
    print()
    print(f"=== Complete ===")
    print(f"Processed: {processed} documents")
    print(f"Added: {total_nodes} nodes, {total_edges} edges")
    print(f"Time: {int(elapsed)}s ({processed/elapsed:.1f} docs/s)")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Enrich graph with Phi-3")
    parser.add_argument('--source', type=int, default=2, help='Source ID (default: 2 = epstein_vol8)')
    parser.add_argument('--limit', type=int, default=10000, help='Max docs to process')
    parser.add_argument('--batch', type=int, default=10, help='Batch size')
    args = parser.parse_args()

    main(args.source, args.limit, args.batch)
