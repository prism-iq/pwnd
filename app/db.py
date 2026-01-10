"""Database connections and utilities - PostgreSQL with connection pooling"""
import logging
import os
from pathlib import Path
from contextlib import contextmanager
from typing import List, Dict, Any

from dotenv import load_dotenv
import psycopg2
import psycopg2.extras
import psycopg2.pool

log = logging.getLogger(__name__)

# Load .env before accessing env vars
from app.config import BASE_DIR
load_dotenv(BASE_DIR / ".env")

# Get PostgreSQL connection from environment (required)
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is required")

# Connection pool - min 2 connections, max 10
_pool = None

# Pool configuration - optimized for concurrent access
POOL_MIN_CONN = int(os.getenv('DB_POOL_MIN', 5))
POOL_MAX_CONN = int(os.getenv('DB_POOL_MAX', 30))

def _get_pool():
    """Get or create the connection pool (lazy initialization)"""
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=POOL_MIN_CONN,
            maxconn=POOL_MAX_CONN,
            dsn=DATABASE_URL
        )
        log.info(f"PostgreSQL connection pool initialized ({POOL_MIN_CONN}-{POOL_MAX_CONN} connections)")
    return _pool

@contextmanager
def get_db(db_name: str = None):
    """Context manager for PostgreSQL connection from pool

    Note: db_name parameter is kept for compatibility but ignored
    since PostgreSQL uses single database with multiple tables
    """
    pool = _get_pool()
    conn = pool.getconn()
    conn.set_session(autocommit=False)
    try:
        yield conn
    finally:
        pool.putconn(conn)

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
        try:
            cursor.execute("SELECT lastval();")
            result = cursor.fetchone()
            return result[0] if result else 0
        except psycopg2.ProgrammingError:
            # lastval() fails if no sequence was used in this session
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

        # Performance indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_conversation_id
            ON messages(conversation_id);
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_created_at
            ON messages(created_at DESC);
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

        # Opus/Sonnet calls tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS opus_calls (
                id SERIAL PRIMARY KEY,
                tokens_in INTEGER,
                tokens_out INTEGER,
                cost_usd DECIMAL(10,6),
                query_preview TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_opus_calls_date
            ON opus_calls(created_at);
        """)

        conn.commit()
        cursor.close()
        log.info("Database tables initialized")

def close_pool():
    """Close all connections in the pool (for graceful shutdown)"""
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None
        log.info("PostgreSQL connection pool closed")
