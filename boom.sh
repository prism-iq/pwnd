#!/bin/bash
#===============================================================================
# boom.sh - L Investigation Framework Single Entry Point
#===============================================================================
# "Evil must be fought wherever it is found." - The Code
#
# This script handles:
# - Fresh installation (detect & install dependencies)
# - Updates (rebuild & restart services)
# - Health checks (verify services running)
# - Offline operation (works after first setup)
#===============================================================================

set -e  # Exit on error

# Colors for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly CYAN='\033[0;36m'
readonly BOLD='\033[1m'
readonly NC='\033[0m'  # No Color

# Installation directory
readonly INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly ENV_FILE="$INSTALL_DIR/.env"
readonly ENV_EXAMPLE="$INSTALL_DIR/.env.example"

#===============================================================================
# Helper Functions
#===============================================================================

log_info() {
    echo -e "${CYAN}→${NC} $1"
}

log_success() {
    echo -e "${GREEN}✓${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

log_error() {
    echo -e "${RED}✗${NC} $1"
}

log_header() {
    echo ""
    echo -e "${BOLD}${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}${BLUE}  $1${NC}"
    echo -e "${BOLD}${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

print_banner() {
    echo -e "${CYAN}"
    cat << "EOF"
╦   ╦╔╗╔╦  ╦╔═╗╔═╗╔╦╗╦╔═╗╔═╗╔╦╗╦╔═╗╔╗╔
║   ║║║║╚╗╔╝║╣ ╚═╗ ║ ║║ ╦╠═╣ ║ ║║ ║║║║
╩═╝ ╩╝╚╝ ╚╝ ╚═╝╚═╝ ╩ ╩╚═╝╩ ╩ ╩ ╩╚═╝╝╚╝
╔═╗╦═╗╔═╗╔╦╗╔═╗╦ ╦╔═╗╦═╗╦╔═
╠╣ ╠╦╝╠═╣║║║║╣ ║║║║ ║╠╦╝╠╩╗
╚  ╩╚═╩ ╩╩ ╩╚═╝╚╩╝╚═╝╩╚═╩ ╩
EOF
    echo -e "${NC}"
    echo -e "${BOLD}The Code: ${NC}Protect the weak. Report truth. Fight evil."
    echo ""
}

#===============================================================================
# Detection Functions
#===============================================================================

is_fresh_install() {
    # Check if .env exists
    if [ ! -f "$ENV_FILE" ]; then
        return 0  # Fresh install
    fi

    # Check if venv exists
    if [ ! -d "$INSTALL_DIR/venv" ]; then
        return 0  # Fresh install
    fi

    # Check if PostgreSQL database exists
    if ! sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw lframework 2>/dev/null; then
        return 0  # Fresh install
    fi

    return 1  # Already installed
}

check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "Please run as root: sudo ./boom.sh"
        exit 1
    fi
}

#===============================================================================
# Installation Functions
#===============================================================================

fresh_install() {
    log_header "FRESH INSTALLATION"

    # Step 1: Copy .env.example
    if [ -f "$ENV_EXAMPLE" ] && [ ! -f "$ENV_FILE" ]; then
        log_info "Creating .env from template..."
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        log_success ".env created (edit with your settings)"
    fi

    # Step 2: Run install.sh (system dependencies)
    if [ -f "$INSTALL_DIR/scripts/install.sh" ]; then
        log_info "Installing system dependencies..."
        bash "$INSTALL_DIR/scripts/install.sh"
        log_success "Dependencies installed"
    else
        log_error "scripts/install.sh not found"
        exit 1
    fi

    # Step 3: Download model
    if [ -f "$INSTALL_DIR/scripts/download-model.sh" ]; then
        log_info "Downloading LLM model (Phi-3-Mini)..."
        bash "$INSTALL_DIR/scripts/download-model.sh"
        log_success "Model ready"
    else
        log_warn "scripts/download-model.sh not found, skipping"
    fi

    # Step 4: Setup PostgreSQL database
    if [ -f "$INSTALL_DIR/scripts/setup-db.sh" ]; then
        log_info "Setting up PostgreSQL database..."
        bash "$INSTALL_DIR/scripts/setup-db.sh"
        log_success "Database initialized"
    else
        log_error "scripts/setup-db.sh not found"
        exit 1
    fi

    log_success "Fresh installation complete"
}

rebuild() {
    log_header "REBUILD & RESTART"

    # Run rebuild script if exists
    if [ -f "$INSTALL_DIR/rebuild.sh" ]; then
        log_info "Running rebuild..."
        bash "$INSTALL_DIR/rebuild.sh"
    else
        log_warn "rebuild.sh not found, skipping"
    fi

    # Restart services
    log_info "Restarting services..."
    systemctl daemon-reload
    systemctl restart l-llm l-api caddy 2>/dev/null || true

    sleep 3  # Wait for services to start

    log_success "Services restarted"
}

health_check() {
    log_header "HEALTH CHECK"

    local all_healthy=true

    # Check l-llm service
    if systemctl is-active --quiet l-llm; then
        log_success "l-llm.service: ACTIVE"
    else
        log_error "l-llm.service: INACTIVE"
        all_healthy=false
    fi

    # Check l-api service
    if systemctl is-active --quiet l-api; then
        log_success "l-api.service: ACTIVE"
    else
        log_error "l-api.service: INACTIVE"
        all_healthy=false
    fi

    # Check caddy service
    if systemctl is-active --quiet caddy; then
        log_success "caddy.service: ACTIVE"
    else
        log_error "caddy.service: INACTIVE"
        all_healthy=false
    fi

    # Check API health endpoint
    if curl -s -f http://localhost:8002/api/health >/dev/null 2>&1; then
        log_success "API health check: OK"
    else
        log_error "API health check: FAILED"
        all_healthy=false
    fi

    echo ""

    if [ "$all_healthy" = true ]; then
        log_success "All systems operational"
        echo ""
        echo -e "${GREEN}Access your instance:${NC}"
        echo "  • Local:  http://localhost"
        echo "  • API:    http://localhost:8002"
        echo ""
        return 0
    else
        log_error "Some services are unhealthy"
        echo ""
        echo -e "${YELLOW}Debug commands:${NC}"
        echo "  sudo journalctl -u l-llm -n 50"
        echo "  sudo journalctl -u l-api -n 50"
        echo "  sudo systemctl status l-llm l-api caddy"
        echo ""
        return 1
    fi
}

#===============================================================================
# Main Entry Point
#===============================================================================

main() {
    print_banner

    # Must run as root
    check_root

    # Change to installation directory
    cd "$INSTALL_DIR"

    # Detect fresh install vs update
    if is_fresh_install; then
        log_info "Detected: FRESH INSTALLATION"
        fresh_install
    else
        log_info "Detected: UPDATE/REBUILD"
    fi

    # Always rebuild and restart
    rebuild

    # Health check
    if health_check; then
        log_header "DEPLOYMENT COMPLETE"
        echo -e "${BOLD}${GREEN}Evil must be fought wherever it is found.${NC}"
        echo -e "${GREEN}— The Code${NC}"
        echo ""
        exit 0
    else
        log_header "DEPLOYMENT FAILED"
        exit 1
    fi
}

#===============================================================================
# Error Handling
#===============================================================================

trap 'log_error "Script failed at line $LINENO. Check logs above."' ERR

#===============================================================================
# Run
#===============================================================================

main "$@"
