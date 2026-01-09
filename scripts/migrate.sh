#!/bin/bash
#===============================================================================
# migrate.sh - Migrate SQLite data to PostgreSQL
#===============================================================================
# Migrates existing SQLite databases to PostgreSQL:
# - db/sources.db → PostgreSQL emails table
# - db/graph.db → PostgreSQL nodes/edges tables
# - db/sessions.db → PostgreSQL conversations/messages tables
#===============================================================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() { echo -e "${CYAN}→${NC} $1"; }
log_warn() { echo -e "${YELLOW}⚠${NC} $1"; }
log_error() { echo -e "${RED}✗${NC} $1"; }
log_success() { echo -e "${GREEN}✓${NC} $1"; }

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

#===============================================================================
# Check Prerequisites
#===============================================================================

log_info "Checking prerequisites..."

# Check if .env exists
if [ ! -f "$INSTALL_DIR/.env" ]; then
    log_error ".env file not found"
    log_error "Run ./boom.sh first to setup the database"
    exit 1
fi

# Check if PostgreSQL is configured
if ! grep -q "^DATABASE_URL=postgresql://" "$INSTALL_DIR/.env"; then
    log_error "PostgreSQL not configured in .env"
    log_error "DATABASE_URL should start with 'postgresql://'"
    exit 1
fi

# Check if venv exists
if [ ! -d "$INSTALL_DIR/venv" ]; then
    log_error "Python virtual environment not found"
    log_error "Run ./boom.sh first to setup the environment"
    exit 1
fi

log_success "Prerequisites OK"

#===============================================================================
# Check for SQLite Databases
#===============================================================================

log_info "Scanning for SQLite databases..."

SQLITE_DIR="$INSTALL_DIR/db"
FOUND_DBS=0

if [ -f "$SQLITE_DIR/sources.db" ]; then
    log_info "Found: sources.db (emails)"
    FOUND_DBS=$((FOUND_DBS + 1))
fi

if [ -f "$SQLITE_DIR/graph.db" ]; then
    log_info "Found: graph.db (knowledge graph)"
    FOUND_DBS=$((FOUND_DBS + 1))
fi

if [ -f "$SQLITE_DIR/sessions.db" ]; then
    log_info "Found: sessions.db (conversations)"
    FOUND_DBS=$((FOUND_DBS + 1))
fi

if [ "$FOUND_DBS" -eq 0 ]; then
    log_warn "No SQLite databases found in $SQLITE_DIR"
    log_info "Nothing to migrate"
    exit 0
fi

log_info "Found $FOUND_DBS database(s) to migrate"

#===============================================================================
# Migration
#===============================================================================

log_info "Starting migration to PostgreSQL..."

cd "$INSTALL_DIR"
source venv/bin/activate

# Check for migration scripts
MIGRATION_SCRIPT=""

if [ -f "$INSTALL_DIR/fast_migrate.py" ]; then
    MIGRATION_SCRIPT="fast_migrate.py"
elif [ -f "$INSTALL_DIR/auto_migrate.py" ]; then
    MIGRATION_SCRIPT="auto_migrate.py"
elif [ -f "$INSTALL_DIR/migrate_to_postgres.py" ]; then
    MIGRATION_SCRIPT="migrate_to_postgres.py"
else
    log_error "No migration script found"
    log_error "Expected: fast_migrate.py, auto_migrate.py, or migrate_to_postgres.py"
    exit 1
fi

log_info "Using migration script: $MIGRATION_SCRIPT"

# Run migration
python "$MIGRATION_SCRIPT"

if [ $? -eq 0 ]; then
    log_success "Migration completed successfully"

    # Create backup of SQLite databases
    BACKUP_DIR="$INSTALL_DIR/backup/sqlite_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$BACKUP_DIR"

    log_info "Creating backup of SQLite databases..."

    if [ -f "$SQLITE_DIR/sources.db" ]; then
        cp "$SQLITE_DIR/sources.db" "$BACKUP_DIR/"
    fi

    if [ -f "$SQLITE_DIR/graph.db" ]; then
        cp "$SQLITE_DIR/graph.db" "$BACKUP_DIR/"
    fi

    if [ -f "$SQLITE_DIR/sessions.db" ]; then
        cp "$SQLITE_DIR/sessions.db" "$BACKUP_DIR/"
    fi

    log_success "Backup saved to: $BACKUP_DIR"

    echo ""
    log_info "Migration summary:"
    echo "  • SQLite databases backed up to: $BACKUP_DIR"
    echo "  • PostgreSQL database updated"
    echo "  • You can now delete the SQLite files if everything works correctly"
    echo ""

else
    log_error "Migration failed"
    log_error "Check the error messages above"
    exit 1
fi

#===============================================================================
# Verify Migration
#===============================================================================

log_info "Verifying migration..."

# Source .env to get DATABASE_URL
source "$INSTALL_DIR/.env"

# Count records in PostgreSQL
echo ""
echo "Record counts in PostgreSQL:"

# Extract connection details from DATABASE_URL
DB_USER=$(echo $DATABASE_URL | sed -n 's/.*:\/\/\([^:]*\):.*/\1/p')
DB_PASS=$(echo $DATABASE_URL | sed -n 's/.*:\/\/[^:]*:\([^@]*\)@.*/\1/p')
DB_HOST=$(echo $DATABASE_URL | sed -n 's/.*@\([^:]*\):.*/\1/p')
DB_PORT=$(echo $DATABASE_URL | sed -n 's/.*:\([0-9]*\)\/.*/\1/p')
DB_NAME=$(echo $DATABASE_URL | sed -n 's/.*\/\([^?]*\).*/\1/p')

export PGPASSWORD=$DB_PASS

# Count emails
EMAIL_COUNT=$(psql -U $DB_USER -h $DB_HOST -p $DB_PORT -d $DB_NAME -tAc "SELECT COUNT(*) FROM emails" 2>/dev/null || echo "0")
echo "  • Emails: $EMAIL_COUNT"

# Count nodes
NODE_COUNT=$(psql -U $DB_USER -h $DB_HOST -p $DB_PORT -d $DB_NAME -tAc "SELECT COUNT(*) FROM nodes" 2>/dev/null || echo "0")
echo "  • Graph nodes: $NODE_COUNT"

# Count edges
EDGE_COUNT=$(psql -U $DB_USER -h $DB_HOST -p $DB_PORT -d $DB_NAME -tAc "SELECT COUNT(*) FROM edges" 2>/dev/null || echo "0")
echo "  • Graph edges: $EDGE_COUNT"

# Count conversations
CONV_COUNT=$(psql -U $DB_USER -h $DB_HOST -p $DB_PORT -d $DB_NAME -tAc "SELECT COUNT(*) FROM conversations" 2>/dev/null || echo "0")
echo "  • Conversations: $CONV_COUNT"

echo ""

if [ "$EMAIL_COUNT" -gt 0 ] || [ "$NODE_COUNT" -gt 0 ]; then
    log_success "Migration verified - data successfully transferred"
else
    log_warn "No data found in PostgreSQL tables"
    log_warn "Migration may have failed or source databases were empty"
fi

#===============================================================================
# Done
#===============================================================================

echo ""
log_success "Migration process complete"
echo ""
echo -e "${CYAN}Next steps:${NC}"
echo "  1. Test your application to ensure everything works"
echo "  2. If everything is OK, delete SQLite files:"
echo "     rm $SQLITE_DIR/sources.db $SQLITE_DIR/graph.db $SQLITE_DIR/sessions.db"
echo "  3. Restart services:"
echo "     sudo systemctl restart l-llm l-api"
echo ""
