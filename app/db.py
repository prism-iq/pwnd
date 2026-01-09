"""Database connections and utilities - PostgreSQL"""
import os
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from typing import Optional, List, Dict, Any

# Get PostgreSQL connection from environment
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://lframework:changeme@localhost:5432/ldb')

@contextmanager
def get_db(db_name: str = None):
    """Context manager for PostgreSQL connection

    Note: db_name parameter is kept for compatibility but ignored
    since PostgreSQL uses single database with multiple tables
    """
    conn = psycopg2.connect(DATABASE_URL)
    conn.set_session(autocommit=False)
    try:
        yield conn
    finally:
        conn.close()

def execute_query(db_name: str, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
    """Execute a SELECT query and return results as list of dicts"""
    with get_db(db_name) as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def execute_update(db_name: str, query: str, params: tuple = ()) -> int:
    """Execute an INSERT/UPDATE/DELETE and return rowcount"""
    with get_db(db_name) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        return cursor.rowcount

def execute_insert(db_name: str, query: str, params: tuple = ()) -> int:
    """Execute an INSERT and return last inserted id

    Note: For PostgreSQL, prefer using RETURNING id in the query itself
    """
    with get_db(db_name) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()

        # For PostgreSQL, try to get last inserted id from sequence if available
        # This is a best-effort attempt - prefer using RETURNING clause in query
        try:
            cursor.execute("SELECT lastval();")
            result = cursor.fetchone()
            return result[0] if result else 0
        except Exception:
            # lastval() fails if no sequence was used in this session
            # Return 0 as fallback
            return 0

def init_databases():
    """Initialize PostgreSQL tables if needed"""
    with get_db() as conn:
        cursor = conn.cursor()

        # Conversations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );
        """)

        # Messages table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                is_auto INTEGER DEFAULT 0,
                auto_depth INTEGER DEFAULT 0,
                tokens_in INTEGER,
                tokens_out INTEGER,
                model TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)

        # Auto sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS auto_sessions (
                id SERIAL PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                status TEXT DEFAULT 'running',
                query_count INTEGER DEFAULT 0,
                max_queries INTEGER DEFAULT 20,
                started_at TIMESTAMP DEFAULT NOW(),
                stopped_at TIMESTAMP
            );
        """)

        # Settings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT NOW()
            );
        """)

        # Insert default settings
        cursor.execute("""
            INSERT INTO settings (key, value) VALUES
                ('theme', 'dark'),
                ('auto_max_queries', '20'),
                ('language', 'fr'),
                ('show_confidence', '1'),
                ('show_sources', '1')
            ON CONFLICT (key) DO NOTHING;
        """)

        # Haiku calls tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS haiku_calls (
                id SERIAL PRIMARY KEY,
                tokens_in INTEGER,
                tokens_out INTEGER,
                cost_usd DECIMAL(10,6),
                query_preview TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_haiku_calls_date
            ON haiku_calls(created_at);
        """)

        conn.commit()
        cursor.close()
