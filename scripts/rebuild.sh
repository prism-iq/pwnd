#!/bin/bash
#===============================================================================
# L Investigation Framework - Rebuild Script
# Stops services, verifies dependencies, rebuilds, and restarts everything
#===============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

WORKDIR="/opt/rag"

log() { echo -e "${GREEN}[$(date +%H:%M:%S)]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

#-------------------------------------------------------------------------------
cd "$WORKDIR" || error "Cannot access $WORKDIR"

echo ""
echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║          L INVESTIGATION FRAMEWORK - REBUILD                  ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════╝${NC}"
echo ""

#-------------------------------------------------------------------------------
# STEP 1: Stop Services
#-------------------------------------------------------------------------------
log "[1/7] Stopping services..."
systemctl stop l-api l-go-search l-llm caddy 2>/dev/null || true
sleep 2

#-------------------------------------------------------------------------------
# STEP 2: Environment
#-------------------------------------------------------------------------------
log "[2/7] Loading environment..."
[ -f .env ] && source .env && export DATABASE_URL || error ".env not found"

#-------------------------------------------------------------------------------
# STEP 3: Python Dependencies
#-------------------------------------------------------------------------------
log "[3/7] Checking Python environment..."
[ -d "venv" ] || { python3 -m venv venv; }
source venv/bin/activate
pip install -q --upgrade pip 2>/dev/null
pip install -q httpx psycopg2-binary fastapi uvicorn llama-cpp-python 2>/dev/null

log "    Verifying Python syntax..."
python3 -m py_compile app/pipeline.py app/search.py app/workers.py app/db.py app/routes.py || error "Python syntax errors"

#-------------------------------------------------------------------------------
# STEP 4: PostgreSQL
#-------------------------------------------------------------------------------
log "[4/7] Verifying PostgreSQL..."
systemctl is-active --quiet postgresql || { systemctl start postgresql; sleep 2; }

EMAIL_COUNT=$(sudo -u postgres psql ldb -t -c "SELECT COUNT(*) FROM emails;" 2>/dev/null | tr -d ' ')
NODE_COUNT=$(sudo -u postgres psql ldb -t -c "SELECT COUNT(*) FROM nodes;" 2>/dev/null | tr -d ' ')
[ -z "$EMAIL_COUNT" ] && error "PostgreSQL connection failed"
log "    Database: ${EMAIL_COUNT} emails, ${NODE_COUNT} nodes"

# Optimize
sudo -u postgres psql ldb -c "ANALYZE emails; ANALYZE nodes; ANALYZE edges;" 2>/dev/null || true

#-------------------------------------------------------------------------------
# STEP 5: Go Service
#-------------------------------------------------------------------------------
log "[5/7] Building Go search service..."
cd "$WORKDIR/go-search"
go build -o search-service . 2>/dev/null && log "    Go build OK" || warn "Go build skipped"
cd "$WORKDIR"

#-------------------------------------------------------------------------------
# STEP 6: Start Services
#-------------------------------------------------------------------------------
log "[6/7] Starting services..."
systemctl daemon-reload

systemctl start l-llm
log "    LLM loading models..."
sleep 6

systemctl start l-go-search
sleep 1

systemctl start l-api
log "    API starting..."
sleep 4

systemctl start caddy

#-------------------------------------------------------------------------------
# STEP 7: Health Checks
#-------------------------------------------------------------------------------
log "[7/7] Health checks..."

FAILURES=0

# Go Search
curl -sf "http://127.0.0.1:8003/health" | grep -q "ok" && echo -e "    ${GREEN}✓${NC} Go Search" || { echo -e "    ${RED}✗${NC} Go Search"; ((FAILURES++)); }

# API
curl -sf "http://127.0.0.1:8002/api/health" | grep -q "ok" && echo -e "    ${GREEN}✓${NC} API" || { echo -e "    ${RED}✗${NC} API"; ((FAILURES++)); }

# Caddy
curl -sf "http://127.0.0.1:80" >/dev/null && echo -e "    ${GREEN}✓${NC} Caddy" || { echo -e "    ${RED}✗${NC} Caddy"; ((FAILURES++)); }

# Search test
SEARCH_RESULTS=$(curl -sf "http://127.0.0.1:8002/api/search?q=test" 2>/dev/null | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
[ "$SEARCH_RESULTS" -gt 0 ] && echo -e "    ${GREEN}✓${NC} Search (${SEARCH_RESULTS} results)" || { echo -e "    ${RED}✗${NC} Search"; ((FAILURES++)); }

# Workers
WORKERS=$(curl -sf "http://127.0.0.1:8002/api/stats" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('workers',{}).get('workers',[])))" 2>/dev/null || echo "0")
[ "$WORKERS" -gt 0 ] && echo -e "    ${GREEN}✓${NC} LLM Workers (${WORKERS})" || { echo -e "    ${RED}✗${NC} LLM Workers"; ((FAILURES++)); }

#-------------------------------------------------------------------------------
# SUMMARY
#-------------------------------------------------------------------------------
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"

if [ $FAILURES -eq 0 ]; then
    echo -e "${GREEN}                    REBUILD COMPLETE                           ${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "  Database:  ${GREEN}${EMAIL_COUNT}${NC} emails | ${GREEN}${NODE_COUNT}${NC} nodes"
    echo -e "  Workers:   ${GREEN}${WORKERS}${NC} Phi-3 instances"
    echo -e "  URL:       ${GREEN}https://pwnd.icu${NC}"
    echo ""
else
    echo -e "${RED}                 REBUILD WITH $FAILURES ERRORS                  ${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "  Debug: journalctl -u l-api -f"
    exit 1
fi
