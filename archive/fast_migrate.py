#!/usr/bin/env python3
"""
Fast SQLite → PostgreSQL migration
Creates proper PostgreSQL schema, copies data only
"""

import sqlite3
import psycopg2
from psycopg2.extras import execute_batch
import sys

PG_CONFIG = {
    'dbname': 'ldb',
    'user': 'lframework',
    'password': 'secure_pw_2026',
    'host': 'localhost',
}

def migrate_emails(sqlite_conn, pg_conn):
    """Migrate emails from sources.db"""
    print("\n" + "="*70)
    print("  EMAILS (sources.db → emails table)")
    print("="*70)

    pg_cur = pg_conn.cursor()

    # Create table
    pg_cur.execute("""
        CREATE TABLE IF NOT EXISTS emails (
            doc_id INTEGER PRIMARY KEY,
            subject TEXT,
            sender TEXT,
            recipients TEXT,
            date TEXT,
            body TEXT,
            embedding_id INTEGER,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Get data from SQLite
    sqlite_cur = sqlite_conn.cursor()
    sqlite_cur.execute("SELECT doc_id, subject, sender, recipients, date, body, embedding_id FROM emails")
    rows = sqlite_cur.fetchall()

    if rows:
        # Insert to PostgreSQL
        execute_batch(pg_cur, """
            INSERT INTO emails (doc_id, subject, sender, recipients, date, body, embedding_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (doc_id) DO NOTHING
        """, rows, page_size=1000)
        pg_conn.commit()
        print(f"  ✓ Migrated {len(rows):,} emails")
    else:
        print("  → No emails found")

    # Create FTS index
    print("  → Creating full-text search index...")
    pg_cur.execute("""
        ALTER TABLE emails ADD COLUMN IF NOT EXISTS tsv tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english', COALESCE(subject, '')), 'A') ||
            setweight(to_tsvector('english', COALESCE(body, '')), 'B')
        ) STORED
    """)
    pg_cur.execute("CREATE INDEX IF NOT EXISTS emails_tsv_idx ON emails USING GIN (tsv)")
    pg_conn.commit()
    print("  ✓ FTS index created")

def migrate_graph(sqlite_conn, pg_conn):
    """Migrate graph from graph.db"""
    print("\n" + "="*70)
    print("  GRAPH (graph.db → nodes/edges/properties)")
    print("="*70)

    pg_cur = pg_conn.cursor()

    # Create nodes table
    pg_cur.execute("""
        CREATE TABLE IF NOT EXISTS nodes (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            confidence INTEGER DEFAULT 50,
            source_refs TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            created_by TEXT DEFAULT 'system'
        )
    """)

    # Create edges table
    pg_cur.execute("""
        CREATE TABLE IF NOT EXISTS edges (
            id SERIAL PRIMARY KEY,
            from_node_id INTEGER REFERENCES nodes(id) ON DELETE CASCADE,
            to_node_id INTEGER REFERENCES nodes(id) ON DELETE CASCADE,
            relation_type TEXT NOT NULL,
            confidence INTEGER DEFAULT 50,
            context TEXT,
            source_refs TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Create properties table
    pg_cur.execute("""
        CREATE TABLE IF NOT EXISTS properties (
            id SERIAL PRIMARY KEY,
            node_id INTEGER REFERENCES nodes(id) ON DELETE CASCADE,
            key TEXT NOT NULL,
            value TEXT,
            value_type TEXT DEFAULT 'text',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Migrate nodes
    sqlite_cur = sqlite_conn.cursor()
    sqlite_cur.execute("""
        SELECT id, name, type, confidence, source_refs, created_at, created_by
        FROM nodes
    """)
    rows = sqlite_cur.fetchall()

    if rows:
        execute_batch(pg_cur, """
            INSERT INTO nodes (id, name, type, confidence, source_refs, created_at, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, rows, page_size=1000)
        pg_conn.commit()
        print(f"  ✓ Migrated {len(rows):,} nodes")

        # Update sequence
        pg_cur.execute("SELECT setval('nodes_id_seq', (SELECT MAX(id) FROM nodes))")
        pg_conn.commit()

    # Migrate edges
    sqlite_cur.execute("""
        SELECT id, from_node_id, to_node_id, relation_type, confidence, context, source_refs, created_at
        FROM edges
    """)
    rows = sqlite_cur.fetchall()

    if rows:
        execute_batch(pg_cur, """
            INSERT INTO edges (id, from_node_id, to_node_id, relation_type, confidence, context, source_refs, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, rows, page_size=1000)
        pg_conn.commit()
        print(f"  ✓ Migrated {len(rows):,} edges")

        # Update sequence
        pg_cur.execute("SELECT setval('edges_id_seq', (SELECT MAX(id) FROM edges))")
        pg_conn.commit()

    # Migrate properties
    sqlite_cur.execute("""
        SELECT id, node_id, key, value, value_type, created_at
        FROM properties
    """)
    rows = sqlite_cur.fetchall()

    if rows:
        execute_batch(pg_cur, """
            INSERT INTO properties (id, node_id, key, value, value_type, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, rows, page_size=1000)
        pg_conn.commit()
        print(f"  ✓ Migrated {len(rows):,} properties")

        # Update sequence
        pg_cur.execute("SELECT setval('properties_id_seq', (SELECT MAX(id) FROM properties))")
        pg_conn.commit()

def migrate_audit(sqlite_conn, pg_conn):
    """Migrate audit trail from audit.db"""
    print("\n" + "="*70)
    print("  AUDIT (audit.db → evidence_chain/haiku_calls)")
    print("="*70)

    pg_cur = pg_conn.cursor()

    # Create evidence_chain table
    pg_cur.execute("""
        CREATE TABLE IF NOT EXISTS evidence_chain (
            id SERIAL PRIMARY KEY,
            source_id INTEGER,
            node_id INTEGER,
            edge_id INTEGER,
            query TEXT,
            context TEXT,
            reasoning TEXT,
            confidence INTEGER DEFAULT 50,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Create haiku_calls table
    pg_cur.execute("""
        CREATE TABLE IF NOT EXISTS haiku_calls (
            id SERIAL PRIMARY KEY,
            query TEXT,
            response TEXT,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            cost_usd REAL,
            duration_ms INTEGER,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Migrate evidence_chain
    sqlite_cur = sqlite_conn.cursor()
    sqlite_cur.execute("""
        SELECT id, source_id, node_id, edge_id, query, context, reasoning, confidence, created_at
        FROM evidence_chain
    """)
    rows = sqlite_cur.fetchall()

    if rows:
        execute_batch(pg_cur, """
            INSERT INTO evidence_chain (id, source_id, node_id, edge_id, query, context, reasoning, confidence, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, rows, page_size=1000)
        pg_conn.commit()
        print(f"  ✓ Migrated {len(rows):,} evidence records")

        # Update sequence
        pg_cur.execute("SELECT setval('evidence_chain_id_seq', (SELECT MAX(id) FROM evidence_chain))")
        pg_conn.commit()

    # Migrate haiku_calls
    sqlite_cur.execute("""
        SELECT id, query, response, prompt_tokens, completion_tokens, cost_usd, duration_ms, created_at
        FROM haiku_calls
    """)
    rows = sqlite_cur.fetchall()

    if rows:
        execute_batch(pg_cur, """
            INSERT INTO haiku_calls (id, query, response, prompt_tokens, completion_tokens, cost_usd, duration_ms, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, rows, page_size=1000)
        pg_conn.commit()
        print(f"  ✓ Migrated {len(rows):,} API calls")

        # Update sequence
        pg_cur.execute("SELECT setval('haiku_calls_id_seq', (SELECT MAX(id) FROM haiku_calls))")
        pg_conn.commit()

def main():
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║  Fast SQLite → PostgreSQL Migration                             ║")
    print("╚══════════════════════════════════════════════════════════════════╝")

    # Connect to PostgreSQL
    try:
        pg_conn = psycopg2.connect(**PG_CONFIG)
        print(f"\n✓ Connected to PostgreSQL: {PG_CONFIG['dbname']}")
    except Exception as e:
        print(f"\n✗ PostgreSQL connection failed: {e}")
        sys.exit(1)

    # Migrate sources.db (emails)
    try:
        sources_conn = sqlite3.connect('/opt/rag/db/sources.db')
        migrate_emails(sources_conn, pg_conn)
        sources_conn.close()
    except Exception as e:
        print(f"  ✗ Error: {e}")

    # Migrate graph.db
    try:
        graph_conn = sqlite3.connect('/opt/rag/db/graph.db')
        migrate_graph(graph_conn, pg_conn)
        graph_conn.close()
    except Exception as e:
        print(f"  ✗ Error: {e}")

    # Migrate audit.db
    try:
        audit_conn = sqlite3.connect('/opt/rag/db/audit.db')
        migrate_audit(audit_conn, pg_conn)
        audit_conn.close()
    except Exception as e:
        print(f"  ✗ Error: {e}")

    pg_conn.close()

    print("\n" + "="*70)
    print("  MIGRATION COMPLETE")
    print("="*70)

    print("\nVerify:")
    print("  PGPASSWORD='secure_pw_2026' psql -U lframework -d ldb -c '\\dt'")
    print("  PGPASSWORD='secure_pw_2026' psql -U lframework -d ldb -c 'SELECT COUNT(*) FROM emails;'")
    print("  PGPASSWORD='secure_pw_2026' psql -U lframework -d ldb -c 'SELECT COUNT(*) FROM nodes;'")

if __name__ == "__main__":
    main()
