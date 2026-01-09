#!/bin/bash
# L Investigation Framework - Build Script
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Colors
G='\033[0;32m'; Y='\033[0;33m'; NC='\033[0m'
log() { echo -e "${G}[+]${NC} $1"; }

# Build frontend
if [[ -d "$DIR/frontend" ]]; then
    log "Building SvelteKit frontend..."
    cd "$DIR/frontend"
    npm install --silent 2>/dev/null
    npm run build 2>&1 | grep -E "built|error|warning" || true
    log "Frontend built to: $DIR/frontend/build"
fi

# Reload Caddy
if pgrep -x caddy >/dev/null; then
    log "Reloading Caddy..."
    caddy reload --config /etc/caddy/Caddyfile 2>/dev/null || true
fi

log "Build complete."
