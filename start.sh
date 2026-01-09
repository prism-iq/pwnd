#!/bin/bash
# L Investigation Framework - Startup Script
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Colors
R='\033[0;31m'; G='\033[0;32m'; Y='\033[0;33m'; B='\033[0;34m'; NC='\033[0m'

log() { echo -e "${G}[+]${NC} $1"; }
err() { echo -e "${R}[!]${NC} $1"; exit 1; }
warn() { echo -e "${Y}[*]${NC} $1"; }

# Load environment
[[ -f "$DIR/.env" ]] && export $(grep -v '^#' "$DIR/.env" | xargs) || err "Missing .env"

# Check dependencies
command -v python >/dev/null || err "Python not found"
command -v caddy >/dev/null || err "Caddy not found"
psql -h localhost -U lframework -d ldb -c "SELECT 1" >/dev/null 2>&1 || err "PostgreSQL not available"

# Kill existing processes
log "Stopping existing services..."
pkill -f "uvicorn app.main" 2>/dev/null || true
sleep 1

# Start API server
log "Starting API server..."
cd "$DIR"
PYTHONPATH="$DIR" nohup python -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8002 \
    --workers 1 \
    > /tmp/rag-api.log 2>&1 &

API_PID=$!
sleep 3

# Verify API
if curl -sf http://localhost:8002/api/stats >/dev/null; then
    log "API server running (PID: $API_PID)"
else
    err "API failed to start. Check /tmp/rag-api.log"
fi

# Start Caddy if not running
if ! pgrep -x caddy >/dev/null; then
    log "Starting Caddy..."
    systemctl start caddy || caddy start --config /etc/caddy/Caddyfile
fi

# Verify frontend
if curl -sf https://pwnd.icu >/dev/null 2>&1; then
    log "Frontend accessible at https://pwnd.icu"
else
    warn "Frontend not accessible via HTTPS (check DNS/cert)"
fi

# Status
log "System status:"
echo -e "  API:      ${G}http://localhost:8002${NC}"
echo -e "  Frontend: ${G}https://pwnd.icu${NC}"
curl -s http://localhost:8002/api/stats | python -c "
import sys,json
d=json.load(sys.stdin)
print(f\"  Emails:   {d['sources']:,}\")
print(f\"  Entities: {d['nodes']:,}\")
print(f\"  Workers:  {len(d['workers']['workers'])}\")
" 2>/dev/null || true

log "Ready."
