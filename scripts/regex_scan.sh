#!/bin/bash
#═══════════════════════════════════════════════════════════════════════════════
# HybridCore Regex Scanner - OSINT Pattern Extraction
# Heavy regex lifting in pure Bash
#═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

#═══════════════════════════════════════════════════════════════════════════════
# REGEX PATTERNS - The Arsenal
#═══════════════════════════════════════════════════════════════════════════════

# Communication
REGEX_EMAIL='[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
REGEX_PHONE='(\+?[0-9]{1,3}[-.\s]?)?\(?[0-9]{2,4}\)?[-.\s]?[0-9]{2,4}[-.\s]?[0-9]{2,4}'
REGEX_URL='https?://[A-Za-z0-9._~:/?#\[\]@!$&()*+,;=-]+'
REGEX_IP='([0-9]{1,3}\.){3}[0-9]{1,3}'
REGEX_IPV6='([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}'
REGEX_MAC='([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}'
REGEX_DOMAIN='[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z]{2,})+'

# Dates & Times
REGEX_DATE_ISO='[0-9]{4}-[0-9]{2}-[0-9]{2}'
REGEX_DATE_EU='[0-9]{1,2}[/.-][0-9]{1,2}[/.-][0-9]{2,4}'
REGEX_TIME='([01]?[0-9]|2[0-3]):[0-5][0-9](:[0-5][0-9])?'
REGEX_TIMESTAMP='[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}'

# Financial
REGEX_BTC='[13][a-km-zA-HJ-NP-Z1-9]{25,34}'
REGEX_ETH='0x[a-fA-F0-9]{40}'
REGEX_IBAN='[A-Z]{2}[0-9]{2}[A-Z0-9]{4}[0-9]{7}([A-Z0-9]?){0,16}'
REGEX_CREDIT_CARD='([0-9]{4}[-\s]?){3}[0-9]{4}'
REGEX_SSN='[0-9]{3}-[0-9]{2}-[0-9]{4}'

# Social Media
REGEX_TWITTER='@[A-Za-z0-9_]{1,15}'
REGEX_HASHTAG='#[A-Za-z0-9_]+'
REGEX_INSTAGRAM='@[A-Za-z0-9_.]{1,30}'

# Technical
REGEX_UUID='[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
REGEX_MD5='[a-fA-F0-9]{32}'
REGEX_SHA1='[a-fA-F0-9]{40}'
REGEX_SHA256='[a-fA-F0-9]{64}'
REGEX_BASE64='[A-Za-z0-9+/]{40,}={0,2}'
REGEX_JWT='eyJ[A-Za-z0-9_-]*\.eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*'

# Security / Sensitive
REGEX_AWS_KEY='AKIA[0-9A-Z]{16}'
REGEX_AWS_SECRET='[A-Za-z0-9/+=]{40}'
REGEX_GITHUB_TOKEN='ghp_[a-zA-Z0-9]{36}'
REGEX_PRIVATE_KEY='-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----'
REGEX_API_KEY='[Aa]pi[_-]?[Kk]ey["\s:=]+[A-Za-z0-9_-]{20,}'
REGEX_PASSWORD='[Pp]assword["\s:=]+[^\s"]{6,}'

# File Types
REGEX_FILE_PATH='/[a-zA-Z0-9._/-]+'
REGEX_WINDOWS_PATH='[A-Z]:\\[a-zA-Z0-9._\\-]+'
REGEX_FILE_EXT='\.[a-zA-Z0-9]{1,10}$'

#═══════════════════════════════════════════════════════════════════════════════
# FUNCTIONS
#═══════════════════════════════════════════════════════════════════════════════

banner() {
    echo -e "${MAGENTA}"
    cat << 'BANNER'
    ██████╗ ███████╗ ██████╗ ███████╗██╗  ██╗
    ██╔══██╗██╔════╝██╔════╝ ██╔════╝╚██╗██╔╝
    ██████╔╝█████╗  ██║  ███╗█████╗   ╚███╔╝
    ██╔══██╗██╔══╝  ██║   ██║██╔══╝   ██╔██╗
    ██║  ██║███████╗╚██████╔╝███████╗██╔╝ ██╗
    ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝
    HybridCore Pattern Scanner v2.0
BANNER
    echo -e "${NC}"
}

extract_pattern() {
    local pattern="$1"
    local name="$2"
    local color="$3"

    local matches
    matches=$(grep -oE "$pattern" "$INPUT_FILE" 2>/dev/null | sort -u)

    if [[ -n "$matches" ]]; then
        local count
        count=$(echo "$matches" | wc -l)
        echo -e "${color}[${name}]${NC} Found ${count} matches:"
        echo "$matches" | head -20 | while read -r match; do
            echo "  → $match"
        done
        if [[ $count -gt 20 ]]; then
            echo -e "  ${YELLOW}... and $((count - 20)) more${NC}"
        fi
        echo ""
        return 0
    fi
    return 1
}

scan_file() {
    local found=0

    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  Scanning: ${INPUT_FILE}${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo ""

    # Communication
    extract_pattern "$REGEX_EMAIL" "Email" "$GREEN" && ((found++)) || true
    extract_pattern "$REGEX_PHONE" "Phone" "$GREEN" && ((found++)) || true
    extract_pattern "$REGEX_URL" "URL" "$BLUE" && ((found++)) || true
    extract_pattern "$REGEX_IP" "IP Address" "$BLUE" && ((found++)) || true
    extract_pattern "$REGEX_DOMAIN" "Domain" "$BLUE" && ((found++)) || true

    # Dates
    extract_pattern "$REGEX_DATE_ISO" "Date (ISO)" "$CYAN" && ((found++)) || true
    extract_pattern "$REGEX_TIMESTAMP" "Timestamp" "$CYAN" && ((found++)) || true

    # Financial
    extract_pattern "$REGEX_BTC" "Bitcoin Address" "$YELLOW" && ((found++)) || true
    extract_pattern "$REGEX_ETH" "Ethereum Address" "$YELLOW" && ((found++)) || true
    extract_pattern "$REGEX_IBAN" "IBAN" "$YELLOW" && ((found++)) || true
    extract_pattern "$REGEX_CREDIT_CARD" "Credit Card" "$RED" && ((found++)) || true

    # Social
    extract_pattern "$REGEX_TWITTER" "Twitter Handle" "$CYAN" && ((found++)) || true
    extract_pattern "$REGEX_HASHTAG" "Hashtag" "$CYAN" && ((found++)) || true

    # Technical
    extract_pattern "$REGEX_UUID" "UUID" "$MAGENTA" && ((found++)) || true
    extract_pattern "$REGEX_MD5" "MD5 Hash" "$MAGENTA" && ((found++)) || true
    extract_pattern "$REGEX_SHA256" "SHA256 Hash" "$MAGENTA" && ((found++)) || true
    extract_pattern "$REGEX_JWT" "JWT Token" "$RED" && ((found++)) || true

    # Security (SENSITIVE!)
    echo -e "${RED}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${RED}  SENSITIVE DATA SCAN${NC}"
    echo -e "${RED}═══════════════════════════════════════════════════════════${NC}"
    echo ""

    extract_pattern "$REGEX_AWS_KEY" "AWS Key" "$RED" && ((found++)) || true
    extract_pattern "$REGEX_GITHUB_TOKEN" "GitHub Token" "$RED" && ((found++)) || true
    extract_pattern "$REGEX_PRIVATE_KEY" "Private Key" "$RED" && ((found++)) || true
    extract_pattern "$REGEX_API_KEY" "API Key" "$RED" && ((found++)) || true
    extract_pattern "$REGEX_PASSWORD" "Password" "$RED" && ((found++)) || true

    echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Scan complete: ${found} pattern types found${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
}

scan_stdin() {
    local temp_file
    temp_file=$(mktemp)
    cat > "$temp_file"
    INPUT_FILE="$temp_file"
    scan_file
    rm -f "$temp_file"
}

output_json() {
    echo "{"
    echo '  "patterns": {'

    local first=true
    for pattern_name in email phone url ip domain btc eth twitter hashtag uuid md5 sha256; do
        local pattern_var="REGEX_${pattern_name^^}"
        local pattern="${!pattern_var}"
        local matches
        matches=$(grep -oE "$pattern" "$INPUT_FILE" 2>/dev/null | sort -u | head -100)

        if [[ -n "$matches" ]]; then
            [[ "$first" != "true" ]] && echo ","
            first=false
            echo -n "    \"$pattern_name\": ["
            echo "$matches" | jq -R . | paste -sd, -
            echo -n "]"
        fi
    done

    echo ""
    echo "  }"
    echo "}"
}

#═══════════════════════════════════════════════════════════════════════════════
# MAIN
#═══════════════════════════════════════════════════════════════════════════════

INPUT_FILE=""

case "${1:-}" in
    scan)
        banner
        if [[ -z "${2:-}" ]]; then
            echo "Reading from stdin..."
            scan_stdin
        elif [[ -f "$2" ]]; then
            INPUT_FILE="$2"
            scan_file
        else
            echo -e "${RED}Error: File not found: $2${NC}"
            exit 1
        fi
        ;;
    json)
        if [[ -z "${2:-}" ]]; then
            temp_file=$(mktemp)
            cat > "$temp_file"
            INPUT_FILE="$temp_file"
            output_json
            rm -f "$temp_file"
        elif [[ -f "$2" ]]; then
            INPUT_FILE="$2"
            output_json
        fi
        ;;
    test)
        banner
        echo "Testing regex patterns..."
        echo ""
        echo "Test string: john@test.com +1-555-123-4567 https://pwnd.icu 192.168.1.1"
        echo ""
        echo "john@test.com +1-555-123-4567 https://pwnd.icu 192.168.1.1" | "$0" scan
        ;;
    *)
        echo "Usage: $0 {scan|json|test} [file]"
        echo ""
        echo "Commands:"
        echo "  scan [file]  - Scan file or stdin for patterns"
        echo "  json [file]  - Output matches as JSON"
        echo "  test         - Test with sample data"
        exit 1
        ;;
esac
