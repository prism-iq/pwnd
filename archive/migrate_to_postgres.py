#!/usr/bin/env python3
"""
Fast SQLite to PostgreSQL migration
Migrates all databases from /opt/rag/db/*.db to PostgreSQL
"""

import sqlite3
import psycopg2
from pathlib import Path
import sys

# PostgreSQL connection
PG_CONFIG = {
    'dbname': 'ldb',
    'user': 'lframework',
    'password': 'secure_pw_2026',
    'host': 'localhost',
    'port': 5432
}

SQLITE_DBS = [
    '/opt/rag/db/sources.db',
    '/opt/rag/db/graph.db',
    '/opt/rag/db/audit.db',
    '/opt/rag/db/sessions.db',
    '/opt/rag/db/scores.db',
]

def get_sqlite_schema(db_path: str) -> list:
    """Get CREATE TABLE statements from SQLite"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all table names
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = [row[0] for row in cursor.fetchall()]

    schemas = []
    for table in tables:
        cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name=?;", (table,))
        sql = cursor.fetchone()[0]
        schemas.append((table, sql))

    conn.close()
    return schemas

def transform_schema(sqlite_sql: str, table_name: str) -> str:
    """Transform SQLite schema to PostgreSQL"""
    import re

    sql = sqlite_sql

    # Skip FTS virtual tables (will handle FTS differently in PostgreSQL)
    if 'VIRTUAL TABLE' in sql or '_fts_' in table_name or table_name.endswith('_fts'):
        return None

    # Replace AUTOINCREMENT with SERIAL
    sql = sql.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY')
    sql = sql.replace('AUTOINCREMENT', '')

    # Replace DATETIME with TIMESTAMP
    sql = sql.replace('DATETIME', 'TIMESTAMP')

    # Replace datetime('now') with NOW()
    sql = re.sub(r"datetime\('now'\)", 'NOW()', sql)
    sql = re.sub(r'DEFAULT \(NOW\(\)\)', 'DEFAULT NOW()', sql)

    # Replace CURRENT_TIMESTAMP properly
    sql = re.sub(r'DEFAULT CURRENT_TIMESTAMP', 'DEFAULT NOW()', sql)

    # Replace BLOB with BYTEA
    sql = sql.replace('BLOB', 'BYTEA')

    # Remove quoted table names
    sql = re.sub(r"'([a-zA-Z0-9_]+)'", r'\1', sql)

    # Replace WITHOUT ROWID
    sql = sql.replace('WITHOUT ROWID', '')

    # Add IF NOT EXISTS
    sql = sql.replace(f'CREATE TABLE {table_name}', f'CREATE TABLE IF NOT EXISTS {table_name}')

    return sql

def get_sqlite_data(db_path: str, table: str) -> list:
    """Get all data from SQLite table"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(f"SELECT * FROM {table};")
    rows = cursor.fetchall()

    # Get column names
    if rows:
        columns = list(rows[0].keys())
    else:
        cursor.execute(f"PRAGMA table_info({table});")
        columns = [col[1] for col in cursor.fetchall()]

    conn.close()
    return columns, [tuple(row) for row in rows]

def migrate_database(db_path: str, pg_conn):
    """Migrate single SQLite database to PostgreSQL"""
    db_name = Path(db_path).stem
    print(f"\n{'='*70}")
    print(f"  Migrating: {db_name}.db")
    print(f"{'='*70}")

    if not Path(db_path).exists():
        print(f"⚠ Skipped (file not found)")
        return

    # Get schemas
    schemas = get_sqlite_schema(db_path)
    pg_cursor = pg_conn.cursor()

    for table_name, sqlite_schema in schemas:
        print(f"\n  Table: {table_name}")

        # Transform and create table
        pg_schema = transform_schema(sqlite_schema, table_name)

        # Skip FTS tables
        if pg_schema is None:
            print(f"    → Skipped (FTS virtual table)")
            continue

        # Prefix table name with database name to avoid conflicts
        prefixed_table = f"{db_name}_{table_name}"
        pg_schema = pg_schema.replace(f"CREATE TABLE IF NOT EXISTS {table_name}",
                                      f"CREATE TABLE IF NOT EXISTS {prefixed_table}")

        try:
            pg_cursor.execute(pg_schema)
            print(f"    ✓ Schema created: {prefixed_table}")
        except Exception as e:
            print(f"    ⚠ Schema error: {e}")
            pg_conn.rollback()  # Rollback failed transaction
            continue

        # Get and insert data
        columns, rows = get_sqlite_data(db_path, table_name)

        if not rows:
            print(f"    → 0 rows (empty table)")
            continue

        # Build INSERT statement
        placeholders = ','.join(['%s'] * len(columns))
        insert_sql = f"INSERT INTO {prefixed_table} ({','.join(columns)}) VALUES ({placeholders})"

        # Batch insert
        try:
            pg_cursor.executemany(insert_sql, rows)
            print(f"    ✓ Inserted {len(rows):,} rows")
        except Exception as e:
            print(f"    ⚠ Insert error: {e}")
            # Try one by one to find problematic rows
            success = 0
            for i, row in enumerate(rows):
                try:
                    pg_cursor.execute(insert_sql, row)
                    success += 1
                except Exception as row_err:
                    if i < 3:  # Only show first 3 errors
                        print(f"      Row {i}: {row_err}")
            print(f"    ✓ Inserted {success:,}/{len(rows):,} rows (some failed)")

    pg_conn.commit()

def main():
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║                                                                  ║")
    print("║  SQLite → PostgreSQL Migration                                  ║")
    print("║                                                                  ║")
    print("╚══════════════════════════════════════════════════════════════════╝")

    # Connect to PostgreSQL
    try:
        pg_conn = psycopg2.connect(**PG_CONFIG)
        print(f"\n✓ Connected to PostgreSQL: {PG_CONFIG['dbname']}")
    except Exception as e:
        print(f"\n✗ PostgreSQL connection failed: {e}")
        sys.exit(1)

    # Migrate each database
    for db_path in SQLITE_DBS:
        migrate_database(db_path, pg_conn)

    pg_conn.close()

    print("\n" + "="*70)
    print("  MIGRATION COMPLETE")
    print("="*70)
    print("\nVerify row counts:")
    print("  psql -U lframework -d ldb -c '\\dt'")
    print("  psql -U lframework -d ldb -c 'SELECT COUNT(*) FROM sources_emails;'")

if __name__ == "__main__":
    main()
