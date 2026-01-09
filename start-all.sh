#!/bin/bash
# L Investigation - Start All Services
#
# Architecture:
#   Browser → Go Gateway (8080) → Rust Extract (9001)
#                               → Go Search (9002)
#                               → Python LLM (8002)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "╔═══════════════════════════════════════════════════════════╗"
echo "║     L Investigation - Service Orchestrator                ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

# Kill any existing processes
echo "Stopping existing services..."
pkill -f "l-extract" 2>/dev/null || true
pkill -f "l-gateway" 2>/dev/null || true
pkill -f "l-search" 2>/dev/null || true
pkill -f "uvicorn app.main" 2>/dev/null || true
sleep 1

# =============================================================================
# 1. RUST EXTRACTION ENGINE (Port 9001)
# =============================================================================
if [ -f "rust-extract/target/release/l-extract" ]; then
    echo "Starting Rust Extraction Engine on :9001..."
    cd rust-extract
    PORT=9001 ./target/release/l-extract &
    cd ..
    sleep 1
else
    echo "⚠ Rust extraction engine not built - skipping"
fi

# =============================================================================
# 2. GO SEARCH SERVICE (Port 9002)
# =============================================================================
if [ -f "go-search/l-search" ]; then
    echo "Starting Go Search Service on :9002..."
    cd go-search
    ./l-search &
    cd ..
    sleep 1
else
    echo "⚠ Go search service not built - skipping"
fi

# =============================================================================
# 3. PYTHON LLM SERVICE (Port 8002)
# =============================================================================
if [ -d "venv" ]; then
    echo "Starting Python LLM Service on :8002..."
    source venv/bin/activate
    uvicorn app.main:app --host 127.0.0.1 --port 8002 &
    sleep 2
else
    echo "⚠ Python venv not found - skipping"
fi

# =============================================================================
# 4. GO API GATEWAY (Port 8080)
# =============================================================================
if [ -f "go-gateway/l-gateway" ]; then
    echo "Starting Go API Gateway on :8080..."
    cd go-gateway
    GATEWAY_PORT=8080 \
    RUST_EXTRACT_URL=http://127.0.0.1:9001 \
    PYTHON_LLM_URL=http://127.0.0.1:8002 \
    GO_SEARCH_URL=http://127.0.0.1:9002 \
    ./l-gateway &
    cd ..
else
    echo "⚠ Go gateway not built - using Python API directly"
fi

echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║                   SERVICES STARTED                        ║"
echo "╠═══════════════════════════════════════════════════════════╣"
echo "║  Rust Extract  → http://127.0.0.1:9001                    ║"
echo "║  Go Search     → http://127.0.0.1:9002                    ║"
echo "║  Python LLM    → http://127.0.0.1:8002                    ║"
echo "║  Go Gateway    → http://127.0.0.1:8080                    ║"
echo "╠═══════════════════════════════════════════════════════════╣"
echo "║  Frontend      → https://pwnd.icu                         ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""
echo "Logs: journalctl -f -u l-api -u l-llm -u caddy"
echo "Stop: ./stop-all.sh"
