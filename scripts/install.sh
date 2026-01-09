#!/bin/bash
#===============================================================================
# install.sh - Install system dependencies (multi-OS support)
#===============================================================================
# Supports: Arch Linux, Debian, Ubuntu, Fedora
#===============================================================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${GREEN}→${NC} $1"; }
log_warn() { echo -e "${YELLOW}⚠${NC} $1"; }
log_error() { echo -e "${RED}✗${NC} $1"; }

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

#===============================================================================
# Detect OS
#===============================================================================

log_info "Detecting operating system..."

if [ ! -f /etc/os-release ]; then
    log_error "Cannot detect OS (missing /etc/os-release)"
    exit 1
fi

. /etc/os-release
OS_ID=$ID
OS_NAME=$PRETTY_NAME

log_info "Detected: $OS_NAME"

#===============================================================================
# Install Dependencies by OS
#===============================================================================

install_arch() {
    log_info "Installing packages (Arch Linux)..."
    pacman -Syu --noconfirm
    pacman -S --noconfirm \
        python \
        python-pip \
        python-virtualenv \
        postgresql \
        caddy \
        wget \
        curl \
        git \
        sqlite
}

install_debian_ubuntu() {
    log_info "Installing packages (Debian/Ubuntu)..."
    apt-get update
    apt-get install -y \
        python3 \
        python3-pip \
        python3-venv \
        postgresql \
        postgresql-contrib \
        caddy \
        wget \
        curl \
        git \
        sqlite3 \
        libpq-dev \
        build-essential

    # Create python symlink if needed
    if ! command -v python &> /dev/null; then
        ln -sf /usr/bin/python3 /usr/bin/python
    fi
}

install_fedora() {
    log_info "Installing packages (Fedora)..."
    dnf install -y \
        python3 \
        python3-pip \
        python3-virtualenv \
        postgresql \
        postgresql-server \
        postgresql-contrib \
        caddy \
        wget \
        curl \
        git \
        sqlite \
        libpq-devel \
        gcc

    # Initialize PostgreSQL if first time
    if [ ! -d /var/lib/pgsql/data ]; then
        postgresql-setup --initdb
    fi
}

#===============================================================================
# Install Based on OS
#===============================================================================

case $OS_ID in
    arch|manjaro)
        install_arch
        ;;
    ubuntu|debian)
        install_debian_ubuntu
        ;;
    fedora|rhel|centos)
        install_fedora
        ;;
    *)
        log_error "Unsupported OS: $OS_ID"
        log_error "Supported: Arch, Debian, Ubuntu, Fedora, RHEL, CentOS"
        exit 1
        ;;
esac

#===============================================================================
# Start PostgreSQL
#===============================================================================

log_info "Starting PostgreSQL service..."

case $OS_ID in
    arch|manjaro|ubuntu|debian)
        systemctl enable postgresql
        systemctl start postgresql
        ;;
    fedora|rhel|centos)
        systemctl enable postgresql
        systemctl start postgresql
        ;;
esac

#===============================================================================
# Create Python Virtual Environment
#===============================================================================

log_info "Creating Python virtual environment..."
cd "$INSTALL_DIR"

if [ -d "venv" ]; then
    log_warn "venv already exists, skipping creation"
else
    python3 -m venv venv
fi

#===============================================================================
# Install Python Dependencies
#===============================================================================

log_info "Installing Python packages..."

source venv/bin/activate
pip install --upgrade pip

if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    log_warn "requirements.txt not found, skipping Python package install"
fi

#===============================================================================
# Create Systemd Services
#===============================================================================

log_info "Creating systemd services..."

# l-llm.service (Phi-3 Local LLM)
cat > /etc/systemd/system/l-llm.service << EOF
[Unit]
Description=L Investigation LLM Server (Phi-3-Mini)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
Environment=PATH=$INSTALL_DIR/venv/bin:/usr/bin
ExecStart=$INSTALL_DIR/venv/bin/python llm/backend.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# l-api.service (FastAPI)
cat > /etc/systemd/system/l-api.service << EOF
[Unit]
Description=L Investigation API (FastAPI)
After=network.target l-llm.service postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
Environment=PATH=$INSTALL_DIR/venv/bin:/usr/bin
ExecStart=$INSTALL_DIR/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8002
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable l-llm l-api

log_info "Systemd services created and enabled"

#===============================================================================
# Configure Caddy
#===============================================================================

log_info "Configuring Caddy reverse proxy..."

if [ ! -f "$INSTALL_DIR/Caddyfile" ]; then
    cat > "$INSTALL_DIR/Caddyfile" << 'EOF'
# Development configuration (localhost)
:80 {
    root * static
    file_server

    # API reverse proxy
    handle /api/* {
        reverse_proxy 127.0.0.1:8002
    }
}

# Production configuration (uncomment and set your domain)
# your-domain.com {
#     root * static
#     file_server
#
#     handle /api/* {
#         reverse_proxy 127.0.0.1:8002
#     }
# }
EOF
fi

# Create caddy systemd service if doesn't exist (some distros need it)
if ! systemctl list-unit-files | grep -q caddy.service; then
    log_warn "Caddy service not found, you may need to configure it manually"
else
    systemctl enable caddy
fi

#===============================================================================
# Done
#===============================================================================

echo ""
log_info "System dependencies installed successfully"
echo ""
