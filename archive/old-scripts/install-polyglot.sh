#!/bin/bash
# =============================================================================
# L Investigation - Full Polyglot Installation
# One-command setup for the complete polyglot architecture
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POLYGLOT_DIR="$SCRIPT_DIR/polyglot"

log() { echo -e "${GREEN}[INSTALL]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err() { echo -e "${RED}[ERROR]${NC} $1"; }
info() { echo -e "${CYAN}[INFO]${NC} $1"; }

# =============================================================================
# Banner
# =============================================================================

echo -e "${CYAN}"
cat << 'EOF'
╔═══════════════════════════════════════════════════════════════════════════╗
║                                                                            ║
║   L INVESTIGATION - POLYGLOT INSTALLATION                                 ║
║                                                                            ║
║   Installing the complete human-body architecture:                         ║
║   • Mouth (Svelte)    - User interface                                    ║
║   • Lungs (Node.js)   - I/O breathing                                     ║
║   • Brain (Go)        - Decision making                                   ║
║   • Veins (Python)    - LLM data flow                                     ║
║   • Cells (Rust)      - Entity extraction                                 ║
║   • Synapses (C++)    - Universal FFI bridge                              ║
║   • Nerves (Bash)     - Build & deploy                                    ║
║                                                                            ║
╚═══════════════════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

# =============================================================================
# Check Prerequisites
# =============================================================================

log "Checking prerequisites..."

check_cmd() {
    if command -v "$1" &> /dev/null; then
        info "$1 found: $(command -v $1)"
        return 0
    else
        warn "$1 not found"
        return 1
    fi
}

MISSING=()
check_cmd python3 || MISSING+=("python3")
check_cmd pip3 || MISSING+=("pip3")
check_cmd node || MISSING+=("nodejs")
check_cmd npm || MISSING+=("npm")
check_cmd go || MISSING+=("golang")
check_cmd g++ || MISSING+=("g++")

# Rust is optional (uses existing binary or Python fallback)
if check_cmd cargo; then
    HAS_RUST=true
else
    HAS_RUST=false
    info "Rust not found - will use existing binary or Python fallback"
fi

if [ ${#MISSING[@]} -gt 0 ]; then
    err "Missing required packages: ${MISSING[*]}"
    echo ""
    echo "Install with:"
    echo "  # Debian/Ubuntu:"
    echo "  apt install python3 python3-pip nodejs npm golang g++"
    echo ""
    echo "  # Arch:"
    echo "  pacman -S python python-pip nodejs npm go gcc"
    echo ""
    exit 1
fi

# =============================================================================
# Python Dependencies
# =============================================================================

log "Installing Python dependencies..."

pip3 install -q --upgrade pip
pip3 install -q \
    fastapi uvicorn httpx aiohttp \
    discord.py \
    psycopg2-binary asyncpg \
    anthropic \
    pydantic python-dotenv \
    2>/dev/null || warn "Some Python packages may have failed"

# =============================================================================
# Build C++ Synapses
# =============================================================================

log "Building C++ Synapses (universal FFI bridge)..."

cd "$POLYGLOT_DIR/cpp-core"
make clean 2>/dev/null || true
make release

if [ -f "lib/liblsearch.so" ]; then
    info "Synapses built: lib/liblsearch.so"

    # Install to system (optional)
    if [ -w /usr/local/lib ]; then
        cp lib/liblsearch.so /usr/local/lib/
        ldconfig 2>/dev/null || true
        info "Synapses installed to /usr/local/lib"
    fi
else
    err "Failed to build C++ synapses"
fi

# =============================================================================
# Build Rust Cells (if cargo available)
# =============================================================================

if [ "$HAS_RUST" = true ] && [ -d "$SCRIPT_DIR/rust-extract" ]; then
    log "Building Rust Cells (entity extraction)..."
    cd "$SCRIPT_DIR/rust-extract"
    cargo build --release 2>&1 | tail -5
    info "Cells built: target/release/rust-extract"
else
    info "Skipping Rust build - using existing binary"
fi

# =============================================================================
# Build Go Brain
# =============================================================================

log "Building Go Brain (decision engine)..."

cd "$POLYGLOT_DIR/go-brain"
go mod tidy 2>/dev/null || true
go build -o brain -ldflags="-s -w" .

if [ -f "brain" ]; then
    info "Brain built: brain ($(du -h brain | cut -f1))"
else
    err "Failed to build Go brain"
fi

# =============================================================================
# Build Node.js Lungs
# =============================================================================

log "Building Node.js Lungs (I/O orchestrator)..."

cd "$POLYGLOT_DIR/node-api"
npm install --silent 2>/dev/null
npm run build 2>/dev/null || info "TypeScript build skipped"
info "Lungs ready"

# =============================================================================
# Build Svelte Mouth
# =============================================================================

log "Building Svelte Mouth (UI frontend)..."

cd "$POLYGLOT_DIR/svelte-ui"
npm install --silent 2>/dev/null
npm run build 2>/dev/null

if [ -d "dist" ]; then
    info "Mouth built: dist/ ($(du -sh dist | cut -f1))"
else
    warn "Svelte build skipped"
fi

# =============================================================================
# Create Systemd Services (optional)
# =============================================================================

if [ -d /etc/systemd/system ] && [ -w /etc/systemd/system ]; then
    log "Creating systemd services..."

    # Rust Cells Service
    cat > /etc/systemd/system/l-cells.service << EOF
[Unit]
Description=L Investigation - Rust Cells (Entity Extraction)
After=network.target

[Service]
Type=simple
WorkingDirectory=$SCRIPT_DIR/rust-extract
ExecStart=$SCRIPT_DIR/rust-extract/target/release/rust-extract
Restart=always
RestartSec=5
Environment=RUST_LOG=info

[Install]
WantedBy=multi-user.target
EOF

    # Go Brain Service
    cat > /etc/systemd/system/l-brain.service << EOF
[Unit]
Description=L Investigation - Go Brain (Decision Engine)
After=network.target l-cells.service

[Service]
Type=simple
WorkingDirectory=$POLYGLOT_DIR/go-brain
ExecStart=$POLYGLOT_DIR/go-brain/brain
Restart=always
RestartSec=5
Environment=BRAIN_PORT=8085

[Install]
WantedBy=multi-user.target
EOF

    # Node Lungs Service
    cat > /etc/systemd/system/l-lungs.service << EOF
[Unit]
Description=L Investigation - Node.js Lungs (I/O Orchestrator)
After=network.target l-brain.service

[Service]
Type=simple
WorkingDirectory=$POLYGLOT_DIR/node-api
ExecStart=/usr/bin/node dist/server.js
Restart=always
RestartSec=5
Environment=PORT=3000

[Install]
WantedBy=multi-user.target
EOF

    # Discord Bot Service
    cat > /etc/systemd/system/l-discord.service << EOF
[Unit]
Description=L Investigation - Discord Bot
After=network.target l-brain.service l-cells.service

[Service]
Type=simple
WorkingDirectory=$SCRIPT_DIR
ExecStart=/usr/bin/python3 discord_bot.py
Restart=always
RestartSec=10
EnvironmentFile=$SCRIPT_DIR/.env

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    info "Systemd services created"
    info "Enable with: systemctl enable l-cells l-brain l-lungs l-discord"
fi

# =============================================================================
# Create Environment Template
# =============================================================================

if [ ! -f "$SCRIPT_DIR/.env" ]; then
    log "Creating .env template..."
    cat > "$SCRIPT_DIR/.env" << 'EOF'
# L Investigation - Environment Configuration

# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/l_investigation

# API Keys
ANTHROPIC_API_KEY=your-api-key-here

# Discord Bot (optional)
DISCORD_TOKEN=your-discord-bot-token
DISCORD_GUILD_ID=your-guild-id

# Polyglot Organ URLs
BRAIN_URL=http://127.0.0.1:8085
CELLS_URL=http://127.0.0.1:9001
VEINS_URL=http://127.0.0.1:8002
LUNGS_URL=http://127.0.0.1:3000
EOF
    info "Created .env template - edit with your credentials"
fi

# =============================================================================
# Summary
# =============================================================================

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}   INSTALLATION COMPLETE${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════════════════════${NC}"
echo ""
echo "  Built components:"
echo "    • C++ Synapses:  $POLYGLOT_DIR/cpp-core/lib/liblsearch.so"
echo "    • Go Brain:      $POLYGLOT_DIR/go-brain/brain"
echo "    • Node Lungs:    $POLYGLOT_DIR/node-api/"
echo "    • Svelte Mouth:  $POLYGLOT_DIR/svelte-ui/dist/"
echo "    • Discord Bot:   $SCRIPT_DIR/discord_bot.py"
echo ""
echo "  Quick start:"
echo "    # Start all organs"
echo "    cd $POLYGLOT_DIR && ./build-all.sh start"
echo ""
echo "    # Or use systemd"
echo "    systemctl start l-cells l-brain l-lungs"
echo ""
echo "    # Start Discord bot"
echo "    python3 discord_bot.py"
echo ""
echo "  Test integration:"
echo "    cd $POLYGLOT_DIR && python3 test_integration.py"
echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════════════════════════${NC}"
