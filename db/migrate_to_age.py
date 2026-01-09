#!/usr/bin/env python3
"""
L Investigation - SQLite to PostgreSQL + Apache AGE Migration
Migrates graph.db and sources.db to PostgreSQL with AGE graph extension
"""

import os
import sqlite3
import psycopg2
from psycopg2.extras import execute_batch
import json
from datetime import datetime

# =============================================================================
# Configuration
# =============================================================================

SQLITE_GRAPH = '/opt/rag/db/graph.db'
SQLITE_SOURCES = '/opt/rag/db/sources.db'

PG_CONFIG = {
    'host': os.getenv('PG_HOST', 'localhost'),
    'port': os.getenv('PG_PORT', 5432),
    'database': os.getenv('PG_DATABASE', 'l_investigation'),
    'user': os.getenv('PG_USER', 'postgres'),
    'password': os.getenv('PG_PASSWORD', ''),
}

GRAPH_NAME = 'investigation'

# =============================================================================
# PostgreSQL + AGE Setup
# =============================================================================

def setup_postgresql():
    """Create database and install AGE extension"""
    print("[1/6] Setting up PostgreSQL...")

    # Connect to default database first
    conn = psycopg2.connect(
        host=PG_CONFIG['host'],
        port=PG_CONFIG['port'],
        database='postgres',
        user=PG_CONFIG['user'],
        password=PG_CONFIG['password']
    )
    conn.autocommit = True
    cur = conn.cursor()

    # Create database if not exists
    cur.execute(f"SELECT 1 FROM pg_database WHERE datname = '{PG_CONFIG['database']}'")
    if not cur.fetchone():
        cur.execute(f"CREATE DATABASE {PG_CONFIG['database']}")
        print(f"  Created database: {PG_CONFIG['database']}")
    else:
        print(f"  Database exists: {PG_CONFIG['database']}")

    cur.close()
    conn.close()

    # Connect to target database
    conn = psycopg2.connect(**PG_CONFIG)
    conn.autocommit = True
    cur = conn.cursor()

    # Install AGE extension
    try:
        cur.execute("CREATE EXTENSION IF NOT EXISTS age")
        cur.execute("LOAD 'age'")
        cur.execute("SET search_path = ag_catalog, '$user', public")
        print("  AGE extension loaded")
    except Exception as e:
        print(f"  AGE extension error (may need manual install): {e}")

    cur.close()
    conn.close()

    return True

def create_relational_tables():
    """Create relational tables for sources and documents"""
    print("[2/6] Creating relational tables...")

    conn = psycopg2.connect(**PG_CONFIG)
    cur = conn.cursor()

    # Sources table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            origin_url TEXT,
            path_prefix TEXT,
            doc_count INTEGER DEFAULT 0,
            total_size_bytes BIGINT DEFAULT 0,
            date_acquired DATE,
            notes TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # Documents table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id SERIAL PRIMARY KEY,
            source_id INTEGER REFERENCES sources(id),
            filename TEXT NOT NULL,
            filepath TEXT,
            file_hash TEXT UNIQUE,
            doc_type TEXT NOT NULL,
            origin TEXT,
            date_original DATE,
            date_added TIMESTAMPTZ DEFAULT NOW(),
            status TEXT DEFAULT 'pending',
            title TEXT,
            summary TEXT,
            content TEXT,
            content_vector TSVECTOR,
            metadata JSONB DEFAULT '{}'
        )
    """)

    # Nodes table (relational mirror of graph)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS nodes (
            id SERIAL PRIMARY KEY,
            type TEXT NOT NULL,
            name TEXT NOT NULL,
            name_normalized TEXT,
            source_db TEXT,
            source_id TEXT,
            properties JSONB DEFAULT '{}',
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            created_by TEXT DEFAULT 'system'
        )
    """)

    # Edges table (relational mirror) - all TEXT for messy SQLite data
    cur.execute("""
        CREATE TABLE IF NOT EXISTS edges (
            id SERIAL PRIMARY KEY,
            from_node_id TEXT NOT NULL,
            to_node_id TEXT NOT NULL,
            type TEXT NOT NULL,
            directed BOOLEAN DEFAULT TRUE,
            source_node_id TEXT,
            excerpt TEXT,
            properties JSONB DEFAULT '{}',
            created_at TIMESTAMPTZ DEFAULT NOW(),
            created_by TEXT DEFAULT 'system',
            UNIQUE(from_node_id, to_node_id, type)
        )
    """)

    # Indexes
    cur.execute("CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name_normalized)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_hash ON documents(file_hash)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_content ON documents USING GIN(content_vector)")

    conn.commit()
    cur.close()
    conn.close()

    print("  Relational tables created")
    return True

def create_age_graph():
    """Create Apache AGE graph schema"""
    print("[3/6] Creating AGE graph...")

    conn = psycopg2.connect(**PG_CONFIG)
    cur = conn.cursor()

    try:
        cur.execute("LOAD 'age'")
        cur.execute("SET search_path = ag_catalog, '$user', public")

        # Check if graph exists
        cur.execute(f"SELECT * FROM ag_catalog.ag_graph WHERE name = '{GRAPH_NAME}'")
        if not cur.fetchone():
            cur.execute(f"SELECT create_graph('{GRAPH_NAME}')")
            print(f"  Graph '{GRAPH_NAME}' created")
        else:
            print(f"  Graph '{GRAPH_NAME}' exists")

        conn.commit()
    except Exception as e:
        print(f"  AGE graph error: {e}")
        conn.rollback()

    cur.close()
    conn.close()
    return True

def migrate_sources():
    """Migrate sources.db to PostgreSQL"""
    print("[4/6] Migrating sources...")

    sqlite_conn = sqlite3.connect(SQLITE_SOURCES)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cur = sqlite_conn.cursor()

    pg_conn = psycopg2.connect(**PG_CONFIG)
    pg_cur = pg_conn.cursor()

    # Migrate sources table
    sqlite_cur.execute("SELECT * FROM sources")
    sources = sqlite_cur.fetchall()

    for row in sources:
        pg_cur.execute("""
            INSERT INTO sources (id, name, description, origin_url, path_prefix,
                                doc_count, total_size_bytes, date_acquired, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (name) DO NOTHING
        """, (row['id'], row['name'], row['description'], row['origin_url'],
              row['path_prefix'], row['doc_count'], row['total_size_bytes'],
              row['date_acquired'], row['notes']))

    print(f"  Migrated {len(sources)} sources")

    # Migrate documents (batch for performance)
    sqlite_cur.execute("SELECT COUNT(*) FROM documents")
    total_docs = sqlite_cur.fetchone()[0]

    batch_size = 1000
    migrated = 0

    sqlite_cur.execute("SELECT * FROM documents")

    while True:
        rows = sqlite_cur.fetchmany(batch_size)
        if not rows:
            break

        data = []
        for row in rows:
            data.append((
                row['id'], row['source_id'], row['filename'], row['filepath'],
                row['file_hash'], row['doc_type'], row['origin'], row['date_original'],
                row['status'], row['title'] if 'title' in row.keys() else None,
                row['summary'] if 'summary' in row.keys() else None,
                row['content'] if 'content' in row.keys() else None
            ))

        execute_batch(pg_cur, """
            INSERT INTO documents (id, source_id, filename, filepath, file_hash,
                                   doc_type, origin, date_original, status, title, summary, content)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (file_hash) DO NOTHING
        """, data)

        migrated += len(rows)
        print(f"  Documents: {migrated}/{total_docs}", end='\r')

    pg_conn.commit()
    print(f"\n  Migrated {migrated} documents")

    # Reset sequence
    pg_cur.execute("SELECT setval('documents_id_seq', (SELECT MAX(id) FROM documents))")
    pg_cur.execute("SELECT setval('sources_id_seq', (SELECT MAX(id) FROM sources))")

    pg_conn.commit()
    pg_cur.close()
    pg_conn.close()
    sqlite_cur.close()
    sqlite_conn.close()

    return True

def migrate_graph():
    """Migrate graph.db nodes and edges to PostgreSQL + AGE"""
    print("[5/6] Migrating graph...")

    sqlite_conn = sqlite3.connect(SQLITE_GRAPH)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cur = sqlite_conn.cursor()

    pg_conn = psycopg2.connect(**PG_CONFIG)
    pg_cur = pg_conn.cursor()

    # Migrate nodes
    sqlite_cur.execute("SELECT * FROM nodes")
    nodes = sqlite_cur.fetchall()

    # Get properties for each node
    node_props = {}
    sqlite_cur.execute("SELECT node_id, key, value FROM properties")
    for row in sqlite_cur.fetchall():
        if row['node_id'] not in node_props:
            node_props[row['node_id']] = {}
        node_props[row['node_id']][row['key']] = row['value']

    for node in nodes:
        props = node_props.get(node['id'], {})
        pg_cur.execute("""
            INSERT INTO nodes (id, type, name, name_normalized, source_db, source_id,
                              properties, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (node['id'], node['type'], node['name'], node['name_normalized'],
              node['source_db'], node['source_id'], json.dumps(props), node['created_by']))

    print(f"  Migrated {len(nodes)} nodes")

    # Migrate edges
    sqlite_cur.execute("SELECT * FROM edges")
    edges = sqlite_cur.fetchall()

    for edge in edges:
        pg_cur.execute("""
            INSERT INTO edges (id, from_node_id, to_node_id, type, directed,
                              source_node_id, excerpt, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (edge['id'], str(edge['from_node_id']), str(edge['to_node_id']), edge['type'],
              bool(edge['directed']), str(edge['source_node_id']) if edge['source_node_id'] else None,
              edge['excerpt'], edge['created_by']))

    print(f"  Migrated {len(edges)} edges")

    # Reset sequences
    pg_cur.execute("SELECT setval('nodes_id_seq', (SELECT MAX(id) FROM nodes))")
    pg_cur.execute("SELECT setval('edges_id_seq', (SELECT MAX(id) FROM edges))")

    pg_conn.commit()

    # Now create AGE graph vertices and edges
    print("  Creating AGE graph vertices...")
    try:
        pg_cur.execute("LOAD 'age'")
        pg_cur.execute("SET search_path = ag_catalog, '$user', public")

        # Create vertices from nodes
        for node in nodes[:100]:  # Start with first 100 for testing
            props = node_props.get(node['id'], {})
            props['name'] = node['name']
            props['type'] = node['type']
            props['pg_id'] = node['id']

            cypher = f"""
                SELECT * FROM cypher('{GRAPH_NAME}', $$
                    CREATE (n:{node['type'].replace(' ', '_')} $props)
                    RETURN n
                $$, %s) as (n agtype)
            """
            pg_cur.execute(cypher, (json.dumps({'props': props}),))

        pg_conn.commit()
        print("  AGE vertices created (sample)")
    except Exception as e:
        print(f"  AGE vertex creation error: {e}")
        pg_conn.rollback()

    pg_cur.close()
    pg_conn.close()
    sqlite_cur.close()
    sqlite_conn.close()

    return True

def verify_migration():
    """Verify migration completed successfully"""
    print("[6/6] Verifying migration...")

    pg_conn = psycopg2.connect(**PG_CONFIG)
    pg_cur = pg_conn.cursor()

    pg_cur.execute("SELECT COUNT(*) FROM nodes")
    nodes = pg_cur.fetchone()[0]

    pg_cur.execute("SELECT COUNT(*) FROM edges")
    edges = pg_cur.fetchone()[0]

    pg_cur.execute("SELECT COUNT(*) FROM documents")
    docs = pg_cur.fetchone()[0]

    pg_cur.execute("SELECT COUNT(*) FROM sources")
    sources = pg_cur.fetchone()[0]

    print(f"""
  Migration Complete:
    • Nodes:     {nodes:,}
    • Edges:     {edges:,}
    • Documents: {docs:,}
    • Sources:   {sources}
    """)

    pg_cur.close()
    pg_conn.close()

    return nodes > 0 and edges > 0

# =============================================================================
# Main
# =============================================================================

def main():
    print("=" * 60)
    print("  L Investigation - SQLite → PostgreSQL + AGE Migration")
    print("=" * 60)
    print()

    try:
        setup_postgresql()
        create_relational_tables()
        create_age_graph()
        migrate_sources()
        migrate_graph()
        verify_migration()

        print("\n[SUCCESS] Migration complete!")
        print("\nConnection string:")
        print(f"  postgresql://{PG_CONFIG['user']}@{PG_CONFIG['host']}:{PG_CONFIG['port']}/{PG_CONFIG['database']}")

    except Exception as e:
        print(f"\n[ERROR] Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0

if __name__ == '__main__':
    exit(main())
