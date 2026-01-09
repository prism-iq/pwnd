#!/bin/bash
# L Investigation Framework - Stop Script
set -e

G='\033[0;32m'; NC='\033[0m'
log() { echo -e "${G}[+]${NC} $1"; }

log "Stopping API server..."
pkill -f "uvicorn app.main" 2>/dev/null || true

log "Services stopped."
