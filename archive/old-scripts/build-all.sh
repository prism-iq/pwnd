#!/bin/bash
# L Investigation - Full Polyglot Build
#
# Builds all components:
# 1. Rust extraction engine (port 9001)
# 2. Go API gateway (port 8080)
# 3. Go search service (port 9002)
# 4. Svelte frontend
# 5. WASM NER module
# 6. Python LLM service (port 8002)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "╔═══════════════════════════════════════════════════════════╗"
echo "║     L Investigation - Polyglot Build System               ║"
echo "║     Rust + Go + Python + Svelte + WASM                    ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

success() { echo -e "${GREEN}✓ $1${NC}"; }
warning() { echo -e "${YELLOW}⚠ $1${NC}"; }
error() { echo -e "${RED}✗ $1${NC}"; }

# =============================================================================
# 1. RUST EXTRACTION ENGINE
# =============================================================================
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "Building Rust Extraction Engine..."
echo "═══════════════════════════════════════════════════════════"

if command -v cargo &> /dev/null; then
    cd rust-extract
    cargo build --release 2>&1 | tail -5
    if [ -f target/release/l-extract ]; then
        success "Rust extraction engine built: rust-extract/target/release/l-extract"
    else
        warning "Rust library built (no binary - library mode)"
    fi
    cd ..
else
    warning "Rust not installed - skipping rust-extract"
    echo "  Install with: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
fi

# =============================================================================
# 2. GO API GATEWAY
# =============================================================================
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "Building Go API Gateway..."
echo "═══════════════════════════════════════════════════════════"

if command -v go &> /dev/null; then
    cd go-gateway
    go mod tidy 2>/dev/null || true
    go build -o l-gateway . 2>&1 | tail -5 || warning "Go gateway build had warnings"
    if [ -f l-gateway ]; then
        success "Go gateway built: go-gateway/l-gateway"
    fi
    cd ..
else
    warning "Go not installed - skipping go-gateway"
    echo "  Install with: pacman -S go"
fi

# =============================================================================
# 3. GO SEARCH SERVICE
# =============================================================================
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "Building Go Search Service..."
echo "═══════════════════════════════════════════════════════════"

if [ -d "go-search" ] && command -v go &> /dev/null; then
    cd go-search
    go build -o l-search . 2>&1 | tail -5 || warning "Go search build had warnings"
    if [ -f l-search ]; then
        success "Go search built: go-search/l-search"
    fi
    cd ..
else
    warning "Go search not found or Go not installed"
fi

# =============================================================================
# 4. SVELTE FRONTEND
# =============================================================================
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "Building Svelte Frontend..."
echo "═══════════════════════════════════════════════════════════"

if command -v npm &> /dev/null; then
    cd svelte-ui
    if [ ! -d "node_modules" ]; then
        echo "Installing dependencies..."
        npm install 2>&1 | tail -3
    fi
    npm run build 2>&1 | tail -5 || warning "Svelte build had warnings"
    if [ -d "../static/svelte" ]; then
        success "Svelte frontend built: static/svelte/"
    fi
    cd ..
else
    warning "npm not installed - skipping Svelte build"
    echo "  Install with: pacman -S npm"
fi

# =============================================================================
# 5. WASM NER MODULE
# =============================================================================
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "Building WASM NER Module..."
echo "═══════════════════════════════════════════════════════════"

if command -v wasm-pack &> /dev/null; then
    cd wasm-ner
    wasm-pack build --target web --release 2>&1 | tail -5
    if [ -d "pkg" ]; then
        cp -r pkg ../static/wasm
        success "WASM NER built: static/wasm/"
    fi
    cd ..
elif command -v cargo &> /dev/null; then
    warning "wasm-pack not installed"
    echo "  Install with: cargo install wasm-pack"
else
    warning "Rust not installed - skipping WASM build"
fi

# =============================================================================
# 6. PYTHON VIRTUAL ENV
# =============================================================================
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "Checking Python Environment..."
echo "═══════════════════════════════════════════════════════════"

if [ -d "venv" ]; then
    source venv/bin/activate
    pip install -q -r requirements.txt 2>/dev/null || true
    success "Python venv ready"
else
    warning "Python venv not found - creating..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -q -r requirements.txt 2>/dev/null || true
    success "Python venv created"
fi

# =============================================================================
# SUMMARY
# =============================================================================
echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║                    BUILD COMPLETE                         ║"
echo "╠═══════════════════════════════════════════════════════════╣"
echo "║  Components:                                              ║"
echo "║    Rust Extract  → rust-extract/target/release/           ║"
echo "║    Go Gateway    → go-gateway/l-gateway                   ║"
echo "║    Go Search     → go-search/l-search                     ║"
echo "║    Svelte UI     → static/svelte/                         ║"
echo "║    WASM NER      → static/wasm/                           ║"
echo "║    Python LLM    → venv/ + app/                           ║"
echo "╠═══════════════════════════════════════════════════════════╣"
echo "║  Start services:                                          ║"
echo "║    ./start-all.sh                                         ║"
echo "╚═══════════════════════════════════════════════════════════╝"
