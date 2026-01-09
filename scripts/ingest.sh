#!/bin/bash
#═══════════════════════════════════════════════════════════════════════════════
# HybridCore Document Ingestion Pipeline
# Multi-format document processor with NLP and C++ acceleration
#═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Config
HYBRIDCORE_DIR="/opt/chatbot/hybridcore"
DATA_DIR="${HYBRIDCORE_DIR}/data"
CPP_PROCESSOR="${HYBRIDCORE_DIR}/cpp/text_processor"
DB_NAME="hybridcore"
DB_USER="hybridcore"

# Regex patterns for file validation
VALID_EXTENSIONS="md|txt|pdf|html|json|csv|xml|rst|adoc"

#═══════════════════════════════════════════════════════════════════════════════
# FUNCTIONS
#═══════════════════════════════════════════════════════════════════════════════

banner() {
    echo -e "${CYAN}"
    cat << 'EOF'
    ╦ ╦┬ ┬┌┐ ┬─┐┬┌┬┐╔═╗┌─┐┬─┐┌─┐
    ╠═╣└┬┘├┴┐├┬┘│ ││║  │ │├┬┘├┤
    ╩ ╩ ┴ └─┘┴└─┴─┴┘╚═╝└─┘┴└─└─┘
    Document Ingestion Pipeline v2.0
EOF
    echo -e "${NC}"
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Extract text from various formats
extract_text() {
    local file="$1"
    local ext="${file##*.}"

    case "${ext,,}" in
        md|txt|rst|adoc)
            cat "$file"
            ;;
        pdf)
            if command -v pdftotext &> /dev/null; then
                pdftotext -layout "$file" -
            else
                log_warn "pdftotext not installed, skipping PDF"
                return 1
            fi
            ;;
        html|htm)
            if command -v w3m &> /dev/null; then
                w3m -dump "$file"
            elif command -v lynx &> /dev/null; then
                lynx -dump "$file"
            else
                # Fallback: strip HTML tags with sed
                sed 's/<[^>]*>//g' "$file" | sed 's/&nbsp;/ /g'
            fi
            ;;
        json)
            # Extract text values from JSON
            if command -v jq &> /dev/null; then
                jq -r '.. | strings' "$file" 2>/dev/null | head -10000
            else
                cat "$file"
            fi
            ;;
        csv)
            cat "$file"
            ;;
        *)
            cat "$file"
            ;;
    esac
}

# Process single file
process_file() {
    local file="$1"
    local filename=$(basename "$file")
    local title="${filename%.*}"

    log_info "Processing: ${filename}"

    # Extract text
    local content
    content=$(extract_text "$file" 2>/dev/null) || {
        log_warn "Could not extract text from ${filename}"
        return 1
    }

    if [[ -z "$content" ]]; then
        log_warn "Empty content in ${filename}"
        return 1
    fi

    # Count words (bash regex magic)
    local word_count
    word_count=$(echo "$content" | wc -w)

    local char_count
    char_count=${#content}

    # Optional: C++ processing for stats
    if [[ -x "$CPP_PROCESSOR" ]]; then
        log_info "  → C++ analysis..."
        local cpp_stats
        cpp_stats=$(echo "$content" | "$CPP_PROCESSOR" 2>/dev/null) || true
    fi

    # Insert into PostgreSQL
    log_info "  → Inserting into database..."

    # Escape content for SQL
    local escaped_content
    escaped_content=$(printf '%s' "$content" | sed "s/'/''/g")
    local escaped_title
    escaped_title=$(printf '%s' "$title" | sed "s/'/''/g")

    psql -U "$DB_USER" -d "$DB_NAME" -q << EOSQL
INSERT INTO documents (filename, title, content, word_count, char_count)
VALUES ('${filename}', '${escaped_title}', '${escaped_content}', ${word_count}, ${char_count})
ON CONFLICT (filename) DO UPDATE SET
    content = EXCLUDED.content,
    word_count = EXCLUDED.word_count,
    char_count = EXCLUDED.char_count,
    updated_at = NOW();
EOSQL

    log_success "  ✓ ${filename} (${word_count} words)"
}

# Process directory
process_directory() {
    local dir="$1"
    local count=0
    local failed=0

    log_info "Scanning directory: ${dir}"

    # Find all valid files
    while IFS= read -r -d '' file; do
        if process_file "$file"; then
            ((count++))
        else
            ((failed++))
        fi
    done < <(find "$dir" -type f -regextype posix-extended -regex ".*\.(${VALID_EXTENSIONS})" -print0)

    echo ""
    log_success "Processed ${count} files (${failed} failed)"
}

# Build C++ processor
build_cpp() {
    log_info "Building C++ text processor..."

    local cpp_source="${HYBRIDCORE_DIR}/cpp/text_processor.cpp"

    if [[ ! -f "$cpp_source" ]]; then
        log_error "C++ source not found: ${cpp_source}"
        return 1
    fi

    g++ -O3 -std=c++17 -o "$CPP_PROCESSOR" "$cpp_source" 2>&1

    if [[ -x "$CPP_PROCESSOR" ]]; then
        log_success "C++ processor compiled: ${CPP_PROCESSOR}"
    else
        log_error "Compilation failed"
        return 1
    fi
}

# Database stats
show_stats() {
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}                    Database Statistics                     ${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"

    psql -U "$DB_USER" -d "$DB_NAME" << 'EOSQL'
SELECT
    'Documents' as metric,
    COUNT(*)::text as value
FROM documents
UNION ALL
SELECT
    'Total Words',
    SUM(word_count)::text
FROM documents
UNION ALL
SELECT
    'Total Characters',
    SUM(char_count)::text
FROM documents
UNION ALL
SELECT
    'Avg Words/Doc',
    ROUND(AVG(word_count))::text
FROM documents;
EOSQL
}

# Cleanup old documents
cleanup() {
    local days="${1:-30}"

    log_warn "Removing documents older than ${days} days..."

    psql -U "$DB_USER" -d "$DB_NAME" -c \
        "DELETE FROM documents WHERE created_at < NOW() - INTERVAL '${days} days';"

    log_success "Cleanup complete"
}

# Main
main() {
    banner

    case "${1:-}" in
        ingest)
            if [[ -z "${2:-}" ]]; then
                log_error "Usage: $0 ingest <file_or_directory>"
                exit 1
            fi

            if [[ -d "$2" ]]; then
                process_directory "$2"
            elif [[ -f "$2" ]]; then
                process_file "$2"
            else
                log_error "Not found: $2"
                exit 1
            fi
            ;;
        build)
            build_cpp
            ;;
        stats)
            show_stats
            ;;
        cleanup)
            cleanup "${2:-30}"
            ;;
        *)
            echo "Usage: $0 {ingest|build|stats|cleanup}"
            echo ""
            echo "Commands:"
            echo "  ingest <path>   - Ingest file or directory"
            echo "  build           - Build C++ text processor"
            echo "  stats           - Show database statistics"
            echo "  cleanup [days]  - Remove old documents"
            exit 1
            ;;
    esac
}

main "$@"
