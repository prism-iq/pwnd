#!/usr/bin/env python3
"""
Fully automated SQLite → PostgreSQL migration
Reads actual schemas, creates tables, copies all data
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

TYPE_MAP = {
    'INTEGER': 'INTEGER',
    'TEXT': 'TEXT',
    'REAL': 'REAL',
    'BLOB': 'BYTEA',
    'DATETIME': 'TIMESTAMP',
    'BOOLEAN': 'BOOLEAN',
    'JSON': 'JSONB',
}

def get_table_schema(sqlite_conn, table_name):
    """Get column info from SQLite table"""
    cur = sqlite_conn.cursor()
    cur.execute(f"PRAGMA table_info({table_name})")
    return cur.fetchall()

def create_postgres_table(pg_cur, table_name, schema):
    """Create PostgreSQL table from SQLite schema"""
    columns = []
    pk_col = None

    for col in schema:
        col_id, name, type_, notnull, default, pk = col

        # Map type
        pg_type = TYPE_MAP.get(type_, 'TEXT')

        # Build column definition
        parts = [name, pg_type]

        if pk:
            if pg_type == 'INTEGER':
                parts = [name, 'SERIAL PRIMARY KEY']
                pk_col = name
            else:
                parts.append('PRIMARY KEY')
        elif notnull:
            parts.append('NOT NULL')

        # Skip SQLite-specific defaults
        if default and default not in ("CURRENT_TIMESTAMP", "datetime('now')", "FALSE", "0", "1.0", "'system'"):
            if default.startswith("'"):
                parts.append(f'DEFAULT {default}')
            elif default.replace('.', '').isdigit():
                parts.append(f'DEFAULT {default}')

        columns.append(' '.join(parts))

    # Create table
    sql = f"CREATE TABLE IF NOT EXISTS {table_name} (\n  " + ",\n  ".join(columns) + "\n)"
    try:
        pg_cur.execute(sql)
        return True, pk_col
    except Exception as e:
        print(f"    ⚠ Create error: {e}")
        return False, None

def copy_table_data(sqlite_conn, pg_conn, table_name, pk_col):
    """Copy all data from SQLite to PostgreSQL"""
    sqlite_cur = sqlite_conn.cursor()
    pg_cur = pg_conn.cursor()

    # Get all data
    sqlite_cur.execute(f"SELECT * FROM {table_name}")
    rows = sqlite_cur.fetchall()

    if not rows:
        return 0

    # Get column names
    col_names = [desc[0] for desc in sqlite_cur.description]

    # Build INSERT with ON CONFLICT
    placeholders = ', '.join(['%s'] * len(col_names))
    col_list = ', '.join(col_names)

    if pk_col and pk_col in col_names:
        sql = f"INSERT INTO {table_name} ({col_list}) VALUES ({placeholders}) ON CONFLICT ({pk_col}) DO NOTHING"
    else:
        sql = f"INSERT INTO {table_name} ({col_list}) VALUES ({placeholders})"

    # Batch insert
    try:
        execute_batch(pg_cur, sql, rows, page_size=1000)
        pg_conn.commit()

        # Update sequence if PK is INTEGER
        if pk_col:
            try:
                pg_cur.execute(f"SELECT setval(pg_get_serial_sequence('{table_name}', '{pk_col}'), (SELECT MAX({pk_col}) FROM {table_name}))")
                pg_conn.commit()
            except:
                pass  # Skip if no sequence

        return len(rows)
    except Exception as e:
        pg_conn.rollback()
        print(f"    ⚠ Insert error: {e}")
        return 0

def migrate_database(db_path, db_name, pg_conn):
    """Migrate entire SQLite database to PostgreSQL"""
    print("\n" + "="*70)
    print(f"  {db_name}.db")
    print("="*70)

    try:
        sqlite_conn = sqlite3.connect(db_path)
    except Exception as e:
        print(f"  ✗ Cannot open: {e}")
        return

    # Get all tables
    cur = sqlite_conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '%_fts%'")
    tables = [row[0] for row in cur.fetchall()]

    pg_cur = pg_conn.cursor()

    for table in tables:
        print(f"\n  Table: {table}")

        # Get schema
        schema = get_table_schema(sqlite_conn, table)

        # Create table in PostgreSQL
        success, pk_col = create_postgres_table(pg_cur, table, schema)
        if not success:
            continue

        pg_conn.commit()
        print(f"    ✓ Schema created")

        # Copy data
        count = copy_table_data(sqlite_conn, pg_conn, table, pk_col)
        if count > 0:
            print(f"    ✓ Migrated {count:,} rows")
        else:
            print(f"    → 0 rows")

    sqlite_conn.close()

def main():
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║  Automated SQLite → PostgreSQL Migration                        ║")
    print("╚══════════════════════════════════════════════════════════════════╝")

    # Connect to PostgreSQL
    try:
        pg_conn = psycopg2.connect(**PG_CONFIG)
        print(f"\n✓ Connected to PostgreSQL: {PG_CONFIG['dbname']}")
    except Exception as e:
        print(f"\n✗ PostgreSQL connection failed: {e}")
        sys.exit(1)

    # Migrate all databases
    databases = [
        ('/opt/rag/db/sources.db', 'sources'),
        ('/opt/rag/db/graph.db', 'graph'),
        ('/opt/rag/db/audit.db', 'audit'),
        ('/opt/rag/db/sessions.db', 'sessions'),
        ('/opt/rag/db/scores.db', 'scores'),
    ]

    for db_path, db_name in databases:
        migrate_database(db_path, db_name, pg_conn)

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
