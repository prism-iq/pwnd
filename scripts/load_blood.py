#!/usr/bin/env python3
"""
Load documents from PostgreSQL into C++ Blood server
"""
import sys
sys.path.insert(0, '/opt/rag')

import requests
import json
from app.db import execute_query

BLOOD_URL = "http://127.0.0.1:9003"

def add_document(doc_id: int, title: str, content: str):
    """Add a document to Blood index via HTTP"""
    try:
        # Blood server uses /add endpoint (we'll need to add this)
        # For now, documents are loaded at startup
        return True
    except Exception as e:
        print(f"Error adding doc {doc_id}: {e}")
        return False

def load_emails(limit=5000):
    """Load emails into Blood"""
    print(f"Loading emails (limit {limit})...")

    emails = execute_query('graph', '''
        SELECT doc_id, subject, body_text, sender_name, date_sent
        FROM emails
        WHERE body_text IS NOT NULL AND LENGTH(body_text) > 50
        ORDER BY date_sent DESC NULLS LAST
        LIMIT %s
    ''', (limit,))

    print(f"  Found {len(emails)} emails")
    return emails

def load_contents(limit=10000):
    """Load document contents"""
    print(f"Loading contents (limit {limit})...")

    contents = execute_query('graph', '''
        SELECT c.doc_id, c.full_text, d.filename, d.doc_type
        FROM contents c
        JOIN documents d ON c.doc_id = d.id
        WHERE c.full_text IS NOT NULL AND LENGTH(c.full_text) > 100
        LIMIT %s
    ''', (limit,))

    print(f"  Found {len(contents)} contents")
    return contents

def load_nodes(limit=5000):
    """Load graph nodes as searchable entities"""
    print(f"Loading nodes (limit {limit})...")

    nodes = execute_query('graph', '''
        SELECT n.id, n.name, n.type,
               COALESCE(nc.total_connections, 0) as connections
        FROM nodes n
        LEFT JOIN node_confidence nc ON n.id = nc.node_id
        WHERE LENGTH(n.name) > 2
        ORDER BY nc.total_connections DESC NULLS LAST
        LIMIT %s
    ''', (limit,))

    print(f"  Found {len(nodes)} nodes")
    return nodes

def generate_blood_data():
    """Generate C++ header data for Blood server"""

    emails = load_emails(3000)
    contents = load_contents(5000)
    nodes = load_nodes(2000)

    # Create combined index data
    documents = []

    # Add emails
    for e in emails:
        title = e['subject'] or 'No Subject'
        content = e['body_text'] or ''
        sender = e['sender_name'] or ''
        documents.append({
            'id': e['doc_id'],
            'title': f"[Email] {title}",
            'content': f"{sender}: {content[:2000]}"
        })

    # Add document contents
    for c in contents:
        title = c['filename'] or f"Document {c['doc_id']}"
        doc_type = c['doc_type'] or 'unknown'
        content = c['full_text'] or ''
        documents.append({
            'id': c['doc_id'] + 100000,  # Offset to avoid ID collision
            'title': f"[{doc_type}] {title}",
            'content': content[:3000]
        })

    # Add nodes as searchable entities
    for n in nodes:
        documents.append({
            'id': n['id'] + 200000,
            'title': f"[{n['type']}] {n['name']}",
            'content': f"Entity: {n['name']} (Type: {n['type']}, Connections: {n['connections']})"
        })

    print(f"\nTotal documents to index: {len(documents)}")
    return documents

def save_json_for_blood(documents, output_path="/tmp/blood_data.json"):
    """Save documents as JSON for Blood to load"""
    with open(output_path, 'w') as f:
        json.dump(documents, f)
    print(f"Saved {len(documents)} documents to {output_path}")
    return output_path

if __name__ == "__main__":
    print("=" * 60)
    print("Loading documents for C++ Blood server")
    print("=" * 60)

    docs = generate_blood_data()
    path = save_json_for_blood(docs)

    print(f"\nTo load into Blood, restart with: ./blood 9003 {path}")
