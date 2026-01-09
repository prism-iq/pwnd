#!/bin/bash
# PostgreSQL Migration Script
# Migrates SQLite databases to PostgreSQL for better performance and concurrency
# DO NOT RUN without .env configured with POSTGRES_URL

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}  PostgreSQL Migration Tool           ${NC}"
echo -e "${BLUE}=======================================${NC}"
echo ""

# Check for .env
if [ ! -f "/opt/rag/.env" ]; then
    echo -e "${RED}Error: .env file not found${NC}"
    echo "Create .env with POSTGRES_URL=postgresql://user:pass@host:5432/dbname"
    exit 1
fi

# Load .env
set -a
source /opt/rag/.env
set +a

if [ -z "$POSTGRES_URL" ]; then
    echo -e "${RED}Error: POSTGRES_URL not set in .env${NC}"
    exit 1
fi

VALIDATE_ONLY=${1:-""}
TEMP_DIR="/tmp/l_migration_$(date +%s)"

echo -e "${YELLOW}Configuration:${NC}"
echo "  PostgreSQL: ${POSTGRES_URL%%\?*}"
echo "  Temp dir: $TEMP_DIR"
echo "  Validate only: ${VALIDATE_ONLY:-no}"
echo ""

if [ "$VALIDATE_ONLY" != "--validate" ]; then
    read -p "Continue with migration? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Aborted."
        exit 0
    fi
fi

mkdir -p "$TEMP_DIR"

echo -e "${GREEN}[1/7]${NC} Checking PostgreSQL connection..."
psql "$POSTGRES_URL" -c "SELECT version();" > /dev/null || {
    echo -e "${RED}Failed to connect to PostgreSQL${NC}"
    exit 1
}
echo "  ✓ Connected"

echo -e "${GREEN}[2/7]${NC} Creating schemas..."
psql "$POSTGRES_URL" << 'EOSQL'
-- Create schemas
CREATE SCHEMA IF NOT EXISTS sources;
CREATE SCHEMA IF NOT EXISTS graph;
CREATE SCHEMA IF NOT EXISTS sessions;
CREATE SCHEMA IF NOT EXISTS scores;
CREATE SCHEMA IF NOT EXISTS audit;

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- Trigram similarity for fuzzy search
CREATE EXTENSION IF NOT EXISTS btree_gin;  -- GIN indexes for JSONB
EOSQL
echo "  ✓ Schemas created"

echo -e "${GREEN}[3/7]${NC} Creating tables..."

# sources.emails
psql "$POSTGRES_URL" << 'EOSQL'
CREATE TABLE IF NOT EXISTS sources.emails (
    doc_id SERIAL PRIMARY KEY,
    message_id TEXT,
    subject TEXT,
    date_sent TIMESTAMP,
    sender_email TEXT,
    sender_name TEXT,
    recipients_to JSONB,
    recipients_cc JSONB,
    recipients_bcc JSONB,
    reply_to TEXT,
    in_reply_to TEXT,
    thread_id TEXT,
    body_text TEXT,
    body_html TEXT,
    has_attachments BOOLEAN DEFAULT FALSE,
    attachment_count INTEGER DEFAULT 0,
    domains_extracted JSONB,
    urls_extracted JSONB,
    ips_extracted JSONB,
    extraction_quality REAL DEFAULT 1.0,
    parsed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fts_vector tsvector GENERATED ALWAYS AS (
        to_tsvector('english', COALESCE(subject, '') || ' ' || COALESCE(body_text, ''))
    ) STORED
);

CREATE INDEX IF NOT EXISTS idx_emails_fts ON sources.emails USING gin(fts_vector);
CREATE INDEX IF NOT EXISTS idx_emails_date ON sources.emails(date_sent);
CREATE INDEX IF NOT EXISTS idx_emails_sender ON sources.emails(sender_email);
CREATE INDEX IF NOT EXISTS idx_emails_subject_trgm ON sources.emails USING gin(subject gin_trgm_ops);
EOSQL

# graph.nodes
psql "$POSTGRES_URL" << 'EOSQL'
CREATE TABLE IF NOT EXISTS graph.nodes (
    id SERIAL PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    name_normalized TEXT,
    source_db TEXT,
    source_id INTEGER,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT DEFAULT 'system'
);

CREATE INDEX IF NOT EXISTS idx_nodes_type ON graph.nodes(type);
CREATE INDEX IF NOT EXISTS idx_nodes_name_trgm ON graph.nodes USING gin(name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_nodes_normalized_trgm ON graph.nodes USING gin(name_normalized gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_nodes_source ON graph.nodes(source_db, source_id);
CREATE INDEX IF NOT EXISTS idx_nodes_metadata ON graph.nodes USING gin(metadata);
EOSQL

# graph.edges
psql "$POSTGRES_URL" << 'EOSQL'
CREATE TABLE IF NOT EXISTS graph.edges (
    id SERIAL PRIMARY KEY,
    from_node_id INTEGER NOT NULL REFERENCES graph.nodes(id) ON DELETE CASCADE,
    to_node_id INTEGER NOT NULL REFERENCES graph.nodes(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    directed BOOLEAN DEFAULT TRUE,
    source_node_id INTEGER,
    excerpt TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT DEFAULT 'system'
);

CREATE INDEX IF NOT EXISTS idx_edges_from ON graph.edges(from_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_to ON graph.edges(to_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_type ON graph.edges(type);
CREATE INDEX IF NOT EXISTS idx_edges_both ON graph.edges(from_node_id, to_node_id);
EOSQL

# graph.aliases
psql "$POSTGRES_URL" << 'EOSQL'
CREATE TABLE IF NOT EXISTS graph.aliases (
    id SERIAL PRIMARY KEY,
    canonical_node_id INTEGER NOT NULL REFERENCES graph.nodes(id) ON DELETE CASCADE,
    alias_name TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_aliases_canonical ON graph.aliases(canonical_node_id);
CREATE INDEX IF NOT EXISTS idx_aliases_name_trgm ON graph.aliases USING gin(alias_name gin_trgm_ops);
EOSQL

# sessions tables
psql "$POSTGRES_URL" << 'EOSQL'
CREATE TABLE IF NOT EXISTS sessions.conversations (
    conversation_id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions.messages (
    id SERIAL PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES sessions.conversations(conversation_id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON sessions.messages(conversation_id);
EOSQL

echo "  ✓ Tables created"

echo -e "${GREEN}[4/7]${NC} Exporting SQLite data..."

# Export emails
sqlite3 /opt/rag/db/sources.db << 'EOSQL' > "$TEMP_DIR/emails.csv"
.mode csv
.headers on
SELECT doc_id, message_id, subject, date_sent, sender_email, sender_name,
       recipients_to, recipients_cc, recipients_bcc, reply_to, in_reply_to, thread_id,
       body_text, body_html, has_attachments, attachment_count,
       domains_extracted, urls_extracted, ips_extracted, extraction_quality, parsed_at
FROM emails;
EOSQL
echo "  ✓ Exported $(wc -l < $TEMP_DIR/emails.csv) emails"

# Export nodes
sqlite3 /opt/rag/db/graph.db << 'EOSQL' > "$TEMP_DIR/nodes.csv"
.mode csv
.headers on
SELECT id, type, name, name_normalized, source_db, source_id, created_at, updated_at, created_by
FROM nodes;
EOSQL
echo "  ✓ Exported $(wc -l < $TEMP_DIR/nodes.csv) nodes"

# Export edges
sqlite3 /opt/rag/db/graph.db << 'EOSQL' > "$TEMP_DIR/edges.csv"
.mode csv
.headers on
SELECT id, from_node_id, to_node_id, type, directed, source_node_id, excerpt, created_at, created_by
FROM edges;
EOSQL
echo "  ✓ Exported $(wc -l < $TEMP_DIR/edges.csv) edges"

# Export aliases (if exists)
sqlite3 /opt/rag/db/graph.db << 'EOSQL' > "$TEMP_DIR/aliases.csv" 2>/dev/null || touch "$TEMP_DIR/aliases.csv"
.mode csv
.headers on
SELECT id, canonical_node_id, alias_name, confidence, created_at
FROM aliases;
EOSQL
echo "  ✓ Exported $(wc -l < $TEMP_DIR/aliases.csv) aliases"

if [ "$VALIDATE_ONLY" == "--validate" ]; then
    echo -e "${YELLOW}Validation mode - skipping import${NC}"
    echo -e "${GREEN}Validation successful!${NC}"
    rm -rf "$TEMP_DIR"
    exit 0
fi

echo -e "${GREEN}[5/7]${NC} Importing to PostgreSQL..."

# Import emails (skip header)
tail -n +2 "$TEMP_DIR/emails.csv" | psql "$POSTGRES_URL" -c "\COPY sources.emails (doc_id, message_id, subject, date_sent, sender_email, sender_name, recipients_to, recipients_cc, recipients_bcc, reply_to, in_reply_to, thread_id, body_text, body_html, has_attachments, attachment_count, domains_extracted, urls_extracted, ips_extracted, extraction_quality, parsed_at) FROM STDIN WITH (FORMAT csv, HEADER false);"
echo "  ✓ Imported emails"

# Import nodes
tail -n +2 "$TEMP_DIR/nodes.csv" | psql "$POSTGRES_URL" -c "\COPY graph.nodes (id, type, name, name_normalized, source_db, source_id, created_at, updated_at, created_by) FROM STDIN WITH (FORMAT csv, HEADER false);"
echo "  ✓ Imported nodes"

# Import edges
tail -n +2 "$TEMP_DIR/edges.csv" | psql "$POSTGRES_URL" -c "\COPY graph.edges (id, from_node_id, to_node_id, type, directed, source_node_id, excerpt, created_at, created_by) FROM STDIN WITH (FORMAT csv, HEADER false);"
echo "  ✓ Imported edges"

# Import aliases (if exists and has data)
if [ -s "$TEMP_DIR/aliases.csv" ]; then
    tail -n +2 "$TEMP_DIR/aliases.csv" | psql "$POSTGRES_URL" -c "\COPY graph.aliases (id, canonical_node_id, alias_name, confidence, created_at) FROM STDIN WITH (FORMAT csv, HEADER false);" 2>/dev/null || true
    echo "  ✓ Imported aliases"
fi

echo -e "${GREEN}[6/7]${NC} Updating sequences..."
psql "$POSTGRES_URL" << 'EOSQL'
SELECT setval('sources.emails_doc_id_seq', (SELECT MAX(doc_id) FROM sources.emails));
SELECT setval('graph.nodes_id_seq', (SELECT MAX(id) FROM graph.nodes));
SELECT setval('graph.edges_id_seq', (SELECT MAX(id) FROM graph.edges));
SELECT setval('graph.aliases_id_seq', (SELECT COALESCE(MAX(id), 1) FROM graph.aliases));
EOSQL
echo "  ✓ Sequences updated"

echo -e "${GREEN}[7/7]${NC} Validating migration..."
SQLITE_EMAILS=$(sqlite3 /opt/rag/db/sources.db "SELECT COUNT(*) FROM emails;")
SQLITE_NODES=$(sqlite3 /opt/rag/db/graph.db "SELECT COUNT(*) FROM nodes;")
SQLITE_EDGES=$(sqlite3 /opt/rag/db/graph.db "SELECT COUNT(*) FROM edges;")

PG_EMAILS=$(psql "$POSTGRES_URL" -t -c "SELECT COUNT(*) FROM sources.emails;")
PG_NODES=$(psql "$POSTGRES_URL" -t -c "SELECT COUNT(*) FROM graph.nodes;")
PG_EDGES=$(psql "$POSTGRES_URL" -t -c "SELECT COUNT(*) FROM graph.edges;")

echo ""
echo -e "${BLUE}Migration Summary:${NC}"
echo "  Emails: SQLite=$SQLITE_EMAILS, PostgreSQL=$PG_EMAILS"
echo "  Nodes: SQLite=$SQLITE_NODES, PostgreSQL=$PG_NODES"
echo "  Edges: SQLite=$SQLITE_EDGES, PostgreSQL=$PG_EDGES"

if [ "$SQLITE_EMAILS" -eq "$PG_EMAILS" ] && [ "$SQLITE_NODES" -eq "$PG_NODES" ] && [ "$SQLITE_EDGES" -eq "$PG_EDGES" ]; then
    echo -e "${GREEN}✓ Validation passed - all rows migrated${NC}"
else
    echo -e "${RED}✗ Validation failed - row count mismatch${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}=======================================${NC}"
echo -e "${GREEN}  Migration Complete!                  ${NC}"
echo -e "${GREEN}=======================================${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Update app/db.py to use PostgreSQL connection"
echo "  2. Test with: curl http://localhost:8002/api/ask?q=test"
echo "  3. If successful, backup SQLite files: tar -czf sqlite_backup.tar.gz db/*.db"
echo "  4. Restart services: ./scripts/rebuild.sh"
echo ""

# Cleanup
rm -rf "$TEMP_DIR"
