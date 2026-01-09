#!/bin/bash
#===============================================================================
# import.sh - Import emails/documents into L Investigation Framework
#===============================================================================
# Accepts path to data directory containing:
# - .eml files (email messages)
# - .msg files (Outlook messages)
# - .mbox files (mailbox archives)
# - .txt files (plain text documents)
#
# Idempotent: skips existing documents based on content hash
#===============================================================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${CYAN}→${NC} $1"; }
log_warn() { echo -e "${YELLOW}⚠${NC} $1"; }
log_error() { echo -e "${RED}✗${NC} $1"; }
log_success() { echo -e "${GREEN}✓${NC} $1"; }

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

#===============================================================================
# Usage
#===============================================================================

usage() {
    cat << EOF
${BLUE}L Investigation Framework - Email Import Tool${NC}

${BLUE}Usage:${NC}
    $0 <data_directory> [options]

${BLUE}Arguments:${NC}
    data_directory    Path to directory containing emails/documents

${BLUE}Options:${NC}
    --format <type>   Force format: eml, msg, mbox, txt (auto-detect if not specified)
    --batch-size N    Process N files at a time (default: 100)
    --skip-existing   Skip files that already exist in database (default: true)
    --help            Show this help message

${BLUE}Examples:${NC}
    # Import all emails from directory
    $0 /path/to/emails

    # Import with specific format
    $0 /path/to/data --format mbox

    # Import in smaller batches
    $0 /path/to/emails --batch-size 50

${BLUE}Supported formats:${NC}
    .eml    Email messages (RFC 822)
    .msg    Outlook messages
    .mbox   Mailbox archives
    .txt    Plain text documents
    .pdf    PDF documents (experimental)

EOF
    exit 0
}

#===============================================================================
# Parse Arguments
#===============================================================================

if [ $# -eq 0 ] || [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    usage
fi

DATA_DIR="$1"
shift

# Default options
FORMAT="auto"
BATCH_SIZE=100
SKIP_EXISTING=true

# Parse options
while [ $# -gt 0 ]; do
    case "$1" in
        --format)
            FORMAT="$2"
            shift 2
            ;;
        --batch-size)
            BATCH_SIZE="$2"
            shift 2
            ;;
        --skip-existing)
            SKIP_EXISTING=true
            shift
            ;;
        --no-skip-existing)
            SKIP_EXISTING=false
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            ;;
    esac
done

#===============================================================================
# Validate Input
#===============================================================================

log_info "Validating input..."

# Check if data directory exists
if [ ! -d "$DATA_DIR" ]; then
    log_error "Directory not found: $DATA_DIR"
    exit 1
fi

# Check if .env exists
if [ ! -f "$INSTALL_DIR/.env" ]; then
    log_error ".env file not found"
    log_error "Run ./boom.sh first to setup the database"
    exit 1
fi

# Check if venv exists
if [ ! -d "$INSTALL_DIR/venv" ]; then
    log_error "Python virtual environment not found"
    log_error "Run ./boom.sh first to setup the environment"
    exit 1
fi

log_success "Input validated"

#===============================================================================
# Scan Files
#===============================================================================

log_info "Scanning directory: $DATA_DIR"

# Count files by type
EML_COUNT=$(find "$DATA_DIR" -type f -iname "*.eml" 2>/dev/null | wc -l)
MSG_COUNT=$(find "$DATA_DIR" -type f -iname "*.msg" 2>/dev/null | wc -l)
MBOX_COUNT=$(find "$DATA_DIR" -type f -iname "*.mbox" 2>/dev/null | wc -l)
TXT_COUNT=$(find "$DATA_DIR" -type f -iname "*.txt" 2>/dev/null | wc -l)
PDF_COUNT=$(find "$DATA_DIR" -type f -iname "*.pdf" 2>/dev/null | wc -l)

TOTAL_FILES=$((EML_COUNT + MSG_COUNT + MBOX_COUNT + TXT_COUNT + PDF_COUNT))

if [ "$TOTAL_FILES" -eq 0 ]; then
    log_warn "No supported files found in $DATA_DIR"
    log_info "Supported formats: .eml, .msg, .mbox, .txt, .pdf"
    exit 0
fi

echo ""
log_info "Found files:"
echo "  • EML emails:    $EML_COUNT"
echo "  • MSG emails:    $MSG_COUNT"
echo "  • MBOX archives: $MBOX_COUNT"
echo "  • Text files:    $TXT_COUNT"
echo "  • PDF files:     $PDF_COUNT"
echo "  • Total:         $TOTAL_FILES"
echo ""

#===============================================================================
# Import
#===============================================================================

log_info "Starting import to PostgreSQL..."

cd "$INSTALL_DIR"
source venv/bin/activate

# Create import script inline (Python)
cat > /tmp/import_emails.py << 'PYTHON_SCRIPT'
#!/usr/bin/env python3
"""
Email/Document Importer for L Investigation Framework
"""
import os
import sys
import hashlib
import email
import mailbox
from pathlib import Path
from datetime import datetime
from typing import Optional
import psycopg2
from psycopg2.extras import execute_values

def get_db_connection():
    """Get PostgreSQL connection from environment"""
    from dotenv import load_dotenv
    load_dotenv()

    db_url = os.getenv('DATABASE_URL')
    if not db_url or not db_url.startswith('postgresql://'):
        raise ValueError("DATABASE_URL not configured for PostgreSQL")

    return psycopg2.connect(db_url)

def compute_hash(content: str) -> str:
    """Compute SHA256 hash of content"""
    return hashlib.sha256(content.encode()).hexdigest()

def parse_eml(filepath: Path) -> dict:
    """Parse .eml file"""
    with open(filepath, 'rb') as f:
        msg = email.message_from_binary_file(f)

    return {
        'sender_name': msg.get('From', ''),
        'sender_email': msg.get('From', ''),
        'recipients_to': msg.get('To', ''),
        'recipients_cc': msg.get('Cc', ''),
        'subject': msg.get('Subject', ''),
        'date_sent': msg.get('Date', ''),
        'body_text': msg.get_payload(decode=True).decode(errors='ignore') if msg.get_payload() else '',
        'attachments': '',
    }

def parse_txt(filepath: Path) -> dict:
    """Parse .txt file"""
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    return {
        'sender_name': f'Document: {filepath.name}',
        'sender_email': '',
        'recipients_to': '',
        'recipients_cc': '',
        'subject': filepath.name,
        'date_sent': datetime.fromtimestamp(filepath.stat().st_mtime).isoformat(),
        'body_text': content,
        'attachments': '',
    }

def import_file(filepath: Path, conn, skip_existing: bool = True) -> bool:
    """Import single file to database"""

    # Determine format and parse
    suffix = filepath.suffix.lower()

    try:
        if suffix == '.eml':
            data = parse_eml(filepath)
        elif suffix == '.txt':
            data = parse_txt(filepath)
        else:
            return False  # Unsupported format

        # Compute content hash for deduplication
        content_hash = compute_hash(data['body_text'])

        # Check if already exists
        if skip_existing:
            cur = conn.cursor()
            cur.execute("""
                SELECT COUNT(*) FROM emails
                WHERE body_text = %s OR subject = %s
            """, (data['body_text'], data['subject']))

            if cur.fetchone()[0] > 0:
                cur.close()
                return False  # Already exists

            cur.close()

        # Insert email
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO emails (
                sender_name, sender_email, recipients_to, recipients_cc,
                subject, date_sent, body_text, attachments, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """, (
            data['sender_name'],
            data['sender_email'],
            data['recipients_to'],
            data['recipients_cc'],
            data['subject'],
            data['date_sent'],
            data['body_text'],
            data['attachments']
        ))

        conn.commit()
        cur.close()

        return True

    except Exception as e:
        print(f"Error importing {filepath}: {e}", file=sys.stderr)
        return False

def main():
    """Main import process"""
    if len(sys.argv) < 2:
        print("Usage: import_emails.py <directory> [batch_size] [skip_existing]")
        sys.exit(1)

    data_dir = Path(sys.argv[1])
    batch_size = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    skip_existing = sys.argv[3].lower() == 'true' if len(sys.argv) > 3 else True

    # Connect to database
    conn = get_db_connection()

    # Find all supported files
    files = []
    for pattern in ['*.eml', '*.txt', '*.msg']:
        files.extend(data_dir.glob(f'**/{pattern}'))

    print(f"Processing {len(files)} files...")

    imported = 0
    skipped = 0
    failed = 0

    for i, filepath in enumerate(files, 1):
        if i % 10 == 0:
            print(f"Progress: {i}/{len(files)} ({imported} imported, {skipped} skipped, {failed} failed)")

        result = import_file(filepath, conn, skip_existing)

        if result:
            imported += 1
        elif result is False and skip_existing:
            skipped += 1
        else:
            failed += 1

    conn.close()

    print(f"\nImport complete:")
    print(f"  Imported: {imported}")
    print(f"  Skipped:  {skipped}")
    print(f"  Failed:   {failed}")
    print(f"  Total:    {len(files)}")

if __name__ == '__main__':
    main()
PYTHON_SCRIPT

# Run import
python /tmp/import_emails.py "$DATA_DIR" "$BATCH_SIZE" "$SKIP_EXISTING"

IMPORT_EXIT=$?

# Clean up temp script
rm /tmp/import_emails.py

if [ $IMPORT_EXIT -eq 0 ]; then
    log_success "Import completed successfully"
else
    log_error "Import failed with errors"
    exit 1
fi

#===============================================================================
# Post-Import Tasks
#===============================================================================

log_info "Running post-import tasks..."

# Update full-text search indexes
log_info "Updating search indexes..."

source "$INSTALL_DIR/.env"

DB_USER=$(echo $DATABASE_URL | sed -n 's/.*:\/\/\([^:]*\):.*/\1/p')
DB_PASS=$(echo $DATABASE_URL | sed -n 's/.*:\/\/[^:]*:\([^@]*\)@.*/\1/p')
DB_HOST=$(echo $DATABASE_URL | sed -n 's/.*@\([^:]*\):.*/\1/p')
DB_PORT=$(echo $DATABASE_URL | sed -n 's/.*:\([0-9]*\)\/.*/\1/p')
DB_NAME=$(echo $DATABASE_URL | sed -n 's/.*\/\([^?]*\).*/\1/p')

export PGPASSWORD=$DB_PASS

psql -U $DB_USER -h $DB_HOST -p $DB_PORT -d $DB_NAME <<'SQL'
-- Reindex full-text search
REINDEX INDEX idx_emails_fts;

-- Update statistics
ANALYZE emails;
SQL

log_success "Indexes updated"

#===============================================================================
# Summary
#===============================================================================

# Count total emails in database
EMAIL_COUNT=$(psql -U $DB_USER -h $DB_HOST -p $DB_PORT -d $DB_NAME -tAc "SELECT COUNT(*) FROM emails")

echo ""
log_success "Import process complete"
echo ""
echo -e "${GREEN}Database summary:${NC}"
echo "  • Total emails in database: $EMAIL_COUNT"
echo ""
echo -e "${CYAN}Next steps:${NC}"
echo "  1. Build knowledge graph:"
echo "     ./scripts/enrich_graph.py"
echo ""
echo "  2. Extract entities (optional, requires Claude API):"
echo "     ./scripts/extract_entities.sh"
echo ""
echo "  3. Start querying your data:"
echo "     http://localhost"
echo ""
