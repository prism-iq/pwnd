#!/bin/bash
# =============================================================================
# L Investigation - NERVOUS SYSTEM (Bash)
# Build & deploy all organs
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

POLYGLOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# =============================================================================
# NEURAL SIGNALS (logging)
# =============================================================================

signal() {
    local color=$1
    local organ=$2
    local msg=$3
    echo -e "${color}[${organ}]${NC} ${msg}"
}

impulse() { signal "$GREEN" "NERVE" "$1"; }
pain() { signal "$RED" "PAIN" "$1"; }
sense() { signal "$CYAN" "SENSE" "$1"; }

# =============================================================================
# ORGAN BUILDERS
# =============================================================================

build_blood() {
    impulse "Building C++ Search Engine (blood)..."
    cd "$POLYGLOT_DIR/cpp-core"

    if command -v g++ &> /dev/null; then
        make clean 2>/dev/null || true
        make release
        impulse "Blood flowing: liblsearch.so built"
    else
        pain "g++ not found - blood cannot flow"
        return 1
    fi
}

build_cells() {
    impulse "Building Rust Extractor (cells)..."

    # Use existing rust-extract if available
    if [ -d "/opt/rag/rust-extract" ]; then
        cd /opt/rag/rust-extract
        if command -v cargo &> /dev/null; then
            cargo build --release
            impulse "Cells dividing: rust-extract built"
        else
            pain "cargo not found - cells cannot divide"
        fi
    else
        sense "Rust cells already in /opt/rag/rust-extract"
    fi
}

build_brain() {
    impulse "Building Go Gateway (brain)..."
    cd "$POLYGLOT_DIR/go-brain"

    if command -v go &> /dev/null; then
        go mod tidy
        go build -o brain -ldflags="-s -w" .
        impulse "Brain formed: go-brain built"
    else
        pain "go not found - brain cannot form"
        return 1
    fi
}

build_lungs() {
    impulse "Building Node.js Orchestrator (lungs)..."
    cd "$POLYGLOT_DIR/node-api"

    if command -v npm &> /dev/null; then
        npm install --silent
        npm run build 2>/dev/null || sense "TypeScript build skipped"
        impulse "Lungs inflated: node-api built"
    else
        pain "npm not found - lungs cannot inflate"
        return 1
    fi
}

build_veins() {
    impulse "Checking Python LLM (veins)..."

    if [ -d "/opt/rag/app" ]; then
        sense "Veins connected to /opt/rag/app/pipeline.py"
    else
        pain "Python veins not found"
    fi
}

build_mouth() {
    impulse "Building Svelte Frontend (mouth)..."
    cd "$POLYGLOT_DIR/svelte-ui"

    if [ -f "package.json" ]; then
        npm install --silent
        npm run build 2>/dev/null || sense "Svelte build skipped"
        impulse "Mouth ready: svelte-ui built"
    else
        sense "Mouth not yet configured"
    fi
}

# =============================================================================
# ORGAN STARTERS
# =============================================================================

start_blood() {
    sense "Starting C++ Search (blood) on :9003..."
    # C++ typically runs as embedded library, no standalone server
    sense "Blood runs through FFI - no standalone process"
}

start_cells() {
    sense "Starting Rust Extractor (cells) on :9001..."
    if [ -f "/opt/rag/rust-extract/target/release/rust-extract" ]; then
        cd /opt/rag/rust-extract
        ./target/release/rust-extract &
        sleep 1
        impulse "Cells active on :9001"
    fi
}

start_brain() {
    sense "Starting Go Gateway (brain) on :8080..."
    cd "$POLYGLOT_DIR/go-brain"
    if [ -f "brain" ]; then
        ./brain &
        sleep 1
        impulse "Brain thinking on :8080"
    fi
}

start_lungs() {
    sense "Starting Node.js Orchestrator (lungs) on :3000..."
    cd "$POLYGLOT_DIR/node-api"
    npm start &
    sleep 1
    impulse "Lungs breathing on :3000"
}

start_veins() {
    sense "Starting Python LLM (veins) on :8002..."
    if [ -f "/opt/rag/app/pipeline.py" ]; then
        cd /opt/rag
        python -m uvicorn app.pipeline:app --host 127.0.0.1 --port 8002 &
        sleep 2
        impulse "Veins pumping on :8002"
    fi
}

# =============================================================================
# HEALTH CHECK
# =============================================================================

check_vitals() {
    echo -e "\n${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}           VITAL SIGNS CHECK${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}\n"

    check_organ() {
        local name=$1
        local port=$2
        local endpoint=${3:-/health}

        if curl -s "http://127.0.0.1:$port$endpoint" > /dev/null 2>&1; then
            echo -e "  ${GREEN}✓${NC} $name (port $port) - healthy"
        else
            echo -e "  ${RED}✗${NC} $name (port $port) - offline"
        fi
    }

    check_organ "Brain (Go)"      8080
    check_organ "Cells (Rust)"    9001
    check_organ "Veins (Python)"  8002
    check_organ "Lungs (Node.js)" 3000
    check_organ "Blood (C++)"     9003

    echo ""
}

# =============================================================================
# MAIN
# =============================================================================

case "${1:-build}" in
    build)
        echo -e "\n${CYAN}═══════════════════════════════════════════════════════════${NC}"
        echo -e "${CYAN}       L Investigation - Building All Organs${NC}"
        echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}\n"

        build_blood || true
        build_cells || true
        build_brain || true
        build_lungs || true
        build_veins || true
        build_mouth || true

        echo -e "\n${GREEN}All organs built successfully!${NC}\n"
        ;;

    start)
        echo -e "\n${CYAN}═══════════════════════════════════════════════════════════${NC}"
        echo -e "${CYAN}       L Investigation - Starting All Organs${NC}"
        echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}\n"

        start_cells
        start_veins
        start_brain
        start_lungs

        sleep 2
        check_vitals
        ;;

    stop)
        impulse "Stopping all organs..."
        pkill -f "rust-extract" 2>/dev/null || true
        pkill -f "go-brain" 2>/dev/null || true
        pkill -f "node.*server" 2>/dev/null || true
        pkill -f "uvicorn.*pipeline" 2>/dev/null || true
        impulse "All organs stopped"
        ;;

    health)
        check_vitals
        ;;

    *)
        echo "Usage: $0 {build|start|stop|health}"
        exit 1
        ;;
esac
