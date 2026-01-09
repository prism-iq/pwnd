#!/bin/bash
#===============================================================================
# setup-db.sh - Setup PostgreSQL database for L Investigation Framework
#===============================================================================
# Creates database, user, schema, and imports existing SQLite data if present
#===============================================================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${GREEN}→${NC} $1"; }
log_warn() { echo -e "${YELLOW}⚠${NC} $1"; }
log_error() { echo -e "${RED}✗${NC} $1"; }
log_success() { echo -e "${GREEN}✓${NC} $1"; }

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# PostgreSQL configuration
DB_NAME="lframework"
DB_USER="lframework"
DB_PASS="$(openssl rand -base64 32 | tr -d '=+/' | cut -c1-32)"  # Generate random password
DB_HOST="localhost"
DB_PORT="5432"

#===============================================================================
# Check PostgreSQL is running
#===============================================================================

log_info "Checking PostgreSQL service..."

if ! systemctl is-active --quiet postgresql; then
    log_error "PostgreSQL is not running"
    log_error "Start it with: sudo systemctl start postgresql"
    exit 1
fi

log_success "PostgreSQL is running"

#===============================================================================
# Create Database User
#===============================================================================

log_info "Creating database user: $DB_USER"

# Check if user exists
if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1; then
    log_warn "User $DB_USER already exists"
else
    sudo -u postgres psql <<EOF
CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';
ALTER USER $DB_USER CREATEDB;
EOF
    log_success "User $DB_USER created"
fi

#===============================================================================
# Create Database
#===============================================================================

log_info "Creating database: $DB_NAME"

# Check if database exists
if sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw $DB_NAME; then
    log_warn "Database $DB_NAME already exists"
else
    sudo -u postgres psql <<EOF
CREATE DATABASE $DB_NAME OWNER $DB_USER;
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;
EOF
    log_success "Database $DB_NAME created"
fi

#===============================================================================
# Create Schema
#===============================================================================

log_info "Creating database schema..."

# Check if schema files exist (from old db/schema/)
SCHEMA_DIR="$INSTALL_DIR/db/schema"

if [ -d "$SCHEMA_DIR" ]; then
    log_info "Found schema directory, applying SQL files..."

    for sql_file in "$SCHEMA_DIR"/*.sql; do
        if [ -f "$sql_file" ]; then
            filename=$(basename "$sql_file")
            log_info "Applying $filename..."
            sudo -u postgres psql -d $DB_NAME -f "$sql_file" || log_warn "Failed to apply $filename (may already exist)"
        fi
    done
else
    log_warn "Schema directory not found at $SCHEMA_DIR"
    log_info "Creating basic schema..."

    # Create basic tables if schema dir doesn't exist
    sudo -u postgres psql -d $DB_NAME <<'EOF'
-- Sources table (emails)
CREATE TABLE IF NOT EXISTS emails (
    doc_id SERIAL PRIMARY KEY,
    sender_name TEXT,
    sender_email TEXT,
    recipients_to TEXT,
    recipients_cc TEXT,
    recipients_bcc TEXT,
    date_sent TIMESTAMP,
    subject TEXT,
    body_text TEXT,
    body_html TEXT,
    attachments TEXT,
    labels TEXT,
    score_pertinence INTEGER DEFAULT 50,
    score_confidence INTEGER DEFAULT 50,
    score_suspicion INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Graph nodes
CREATE TABLE IF NOT EXISTS nodes (
    id SERIAL PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    name_normalized TEXT,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Graph edges
CREATE TABLE IF NOT EXISTS edges (
    id SERIAL PRIMARY KEY,
    from_node_id INTEGER REFERENCES nodes(id),
    to_node_id INTEGER REFERENCES nodes(id),
    type TEXT NOT NULL,
    excerpt TEXT,
    source_doc_id INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Sessions
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    conversation_id TEXT REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    is_auto INTEGER DEFAULT 0,
    auto_depth INTEGER DEFAULT 0,
    tokens_in INTEGER,
    tokens_out INTEGER,
    model TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Audit tracking
CREATE TABLE IF NOT EXISTS haiku_calls (
    id SERIAL PRIMARY KEY,
    tokens_in INTEGER,
    tokens_out INTEGER,
    cost_usd DECIMAL(10,6),
    query_preview TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS query_log (
    id SERIAL PRIMARY KEY,
    ip_hash TEXT NOT NULL,
    query_preview TEXT,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Full-text search indexes
CREATE INDEX IF NOT EXISTS idx_emails_fts ON emails USING gin(to_tsvector('english', subject || ' ' || body_text));
CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name_normalized);
CREATE INDEX IF NOT EXISTS idx_edges_from ON edges(from_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(to_node_id);
CREATE INDEX IF NOT EXISTS idx_haiku_created ON haiku_calls(created_at);
EOF

    log_success "Basic schema created"
fi

#===============================================================================
# Migrate SQLite Data (if exists)
#===============================================================================

log_info "Checking for existing SQLite data..."

SQLITE_SOURCES="$INSTALL_DIR/db/sources.db"

if [ -f "$SQLITE_SOURCES" ]; then
    log_warn "Found SQLite database at $SQLITE_SOURCES"
    log_info "To migrate data, use: $INSTALL_DIR/scripts/migrate.sh"
    log_info "Skipping automatic migration (manual step)"
else
    log_info "No SQLite database found (fresh install)"
fi

#===============================================================================
# Update .env with Database URL
#===============================================================================

log_info "Updating .env with database configuration..."

ENV_FILE="$INSTALL_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
    log_warn ".env not found, copying from .env.example..."
    cp "$INSTALL_DIR/.env.example" "$ENV_FILE"
fi

# Update DATABASE_URL in .env
DB_URL="postgresql://$DB_USER:$DB_PASS@$DB_HOST:$DB_PORT/$DB_NAME"

if grep -q "^DATABASE_URL=" "$ENV_FILE"; then
    sed -i "s|^DATABASE_URL=.*|DATABASE_URL=$DB_URL|" "$ENV_FILE"
else
    echo "DATABASE_URL=$DB_URL" >> "$ENV_FILE"
fi

log_success ".env updated with database connection"

#===============================================================================
# Save Database Credentials (for reference)
#===============================================================================

CREDENTIALS_FILE="$INSTALL_DIR/.db_credentials"

cat > "$CREDENTIALS_FILE" << EOF
# PostgreSQL Credentials - L Investigation Framework
# Generated: $(date)

Database: $DB_NAME
User: $DB_USER
Password: $DB_PASS
Host: $DB_HOST
Port: $DB_PORT

Connection String:
postgresql://$DB_USER:$DB_PASS@$DB_HOST:$DB_PORT/$DB_NAME

# Connect with psql:
psql -U $DB_USER -d $DB_NAME -h $DB_HOST -p $DB_PORT
EOF

chmod 600 "$CREDENTIALS_FILE"

log_success "Credentials saved to $CREDENTIALS_FILE (keep secure!)"

#===============================================================================
# Test Connection
#===============================================================================

log_info "Testing database connection..."

if PGPASSWORD=$DB_PASS psql -U $DB_USER -d $DB_NAME -h $DB_HOST -p $DB_PORT -c "SELECT 1" > /dev/null 2>&1; then
    log_success "Database connection successful"
else
    log_error "Database connection failed"
    exit 1
fi

#===============================================================================
# Done
#===============================================================================

echo ""
log_success "PostgreSQL database setup complete"
echo ""
echo -e "${GREEN}Database: ${NC}$DB_NAME"
echo -e "${GREEN}User: ${NC}$DB_USER"
echo -e "${GREEN}Connection: ${NC}postgresql://$DB_USER:****@$DB_HOST:$DB_PORT/$DB_NAME"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Import your email data: ./scripts/import.sh /path/to/emails"
echo "  2. Build graph database: ./scripts/build-graph.sh"
echo ""
