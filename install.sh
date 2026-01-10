#!/bin/bash
set -e

# ============================================================================
#  PWND.ICU - OSINT Investigation Platform
#  Evidence-based investigation framework for prosecution readiness
# ============================================================================

# Colors & Formatting
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
DIM='\033[2m'
BOLD='\033[1m'
NC='\033[0m'

# Symbols
CHECK="${GREEN}✓${NC}"
CROSS="${RED}✗${NC}"
ARROW="${CYAN}→${NC}"
WARN="${YELLOW}⚠${NC}"

clear
echo ""
echo -e "${RED}██████╗ ${YELLOW}██╗    ${GREEN}██╗${CYAN}███╗   ██╗${BLUE}██████╗ ${NC}"
echo -e "${RED}██╔══██╗${YELLOW}██║    ${GREEN}██║${CYAN}████╗  ██║${BLUE}██╔══██╗${NC}"
echo -e "${RED}██████╔╝${YELLOW}██║ █╗ ${GREEN}██║${CYAN}██╔██╗ ██║${BLUE}██║  ██║${NC}"
echo -e "${RED}██╔═══╝ ${YELLOW}██║███╗${GREEN}██║${CYAN}██║╚██╗██║${BLUE}██║  ██║${NC}"
echo -e "${RED}██║     ${YELLOW}╚███╔███${GREEN}╔╝${CYAN}██║ ╚████║${BLUE}██████╔╝${NC}"
echo -e "${RED}╚═╝      ${YELLOW}╚══╝╚══${GREEN}╝ ${CYAN}╚═╝  ╚═══╝${BLUE}╚═════╝ ${NC}"
echo ""
echo -e "${DIM}────────────────────────────────────────────────────${NC}"
echo -e "${WHITE}  OSINT Investigation Platform ${DIM}v2.0${NC}"
echo -e "${DIM}  Evidence-based prosecution readiness framework${NC}"
echo -e "${DIM}────────────────────────────────────────────────────${NC}"
echo ""

# ============================================================================
# THE CODE
# ============================================================================
echo -e "${DIM}\"Never violate a woman, nor harm a child.${NC}"
echo -e "${DIM} Protect the weak against the evil strong.\"${NC}"
echo -e "${DIM}                        — The Drenai Code${NC}"
echo ""
sleep 1

# ============================================================================
# PREFLIGHT CHECKS
# ============================================================================
echo -e "${BOLD}${WHITE}PREFLIGHT CHECKS${NC}"
echo -e "${DIM}────────────────────────────────────────────────────${NC}"

# Check root
if [ "$EUID" -ne 0 ]; then
    echo -e "  ${CROSS} Root privileges required"
    echo -e "     ${DIM}Run: sudo ./install.sh${NC}"
    exit 1
fi
echo -e "  ${CHECK} Root privileges"

# Check internet
if ping -c 1 github.com &> /dev/null; then
    echo -e "  ${CHECK} Internet connection"
else
    echo -e "  ${CROSS} No internet connection"
    exit 1
fi

# Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
    echo -e "  ${CHECK} OS: ${CYAN}$PRETTY_NAME${NC}"
else
    echo -e "  ${CROSS} Cannot detect OS"
    exit 1
fi

# Check disk space (need at least 5GB)
AVAILABLE=$(df -BG . | tail -1 | awk '{print $4}' | tr -d 'G')
if [ "$AVAILABLE" -lt 5 ]; then
    echo -e "  ${WARN} Low disk space: ${AVAILABLE}GB (need 5GB+)"
else
    echo -e "  ${CHECK} Disk space: ${AVAILABLE}GB available"
fi

# Check RAM
RAM=$(free -g | awk '/^Mem:/{print $2}')
if [ "$RAM" -lt 4 ]; then
    echo -e "  ${WARN} Low RAM: ${RAM}GB (recommend 8GB+)"
else
    echo -e "  ${CHECK} RAM: ${RAM}GB"
fi

echo ""
sleep 1

# ============================================================================
# SYSTEM DEPENDENCIES
# ============================================================================
echo -e "${BOLD}${WHITE}INSTALLING SYSTEM DEPENDENCIES${NC}"
echo -e "${DIM}────────────────────────────────────────────────────${NC}"

install_package() {
    local name=$1
    echo -ne "  ${ARROW} $name... "
}

case $OS in
    arch|manjaro|endeavouros)
        echo -e "  ${ARROW} Updating pacman..."
        pacman -Syu --noconfirm > /dev/null 2>&1

        for pkg in python python-pip postgresql sqlite caddy curl git; do
            install_package $pkg
            if pacman -Q $pkg &> /dev/null; then
                echo -e "${CHECK}"
            else
                pacman -S --noconfirm $pkg > /dev/null 2>&1 && echo -e "${CHECK}" || echo -e "${CROSS}"
            fi
        done
        ;;

    ubuntu|debian|pop)
        echo -e "  ${ARROW} Updating apt..."
        apt-get update > /dev/null 2>&1

        for pkg in python3 python3-pip python3-venv postgresql sqlite3 curl git; do
            install_package $pkg
            if dpkg -l $pkg &> /dev/null; then
                echo -e "${CHECK}"
            else
                apt-get install -y $pkg > /dev/null 2>&1 && echo -e "${CHECK}" || echo -e "${CROSS}"
            fi
        done

        # Install Caddy
        install_package "caddy"
        if ! command -v caddy &> /dev/null; then
            apt-get install -y debian-keyring debian-archive-keyring apt-transport-https > /dev/null 2>&1
            curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg 2>/dev/null
            curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list > /dev/null
            apt-get update > /dev/null 2>&1
            apt-get install -y caddy > /dev/null 2>&1
        fi
        echo -e "${CHECK}"

        # Python symlink
        if ! command -v python &> /dev/null; then
            ln -sf /usr/bin/python3 /usr/bin/python
        fi
        ;;

    fedora|rhel|centos)
        echo -e "  ${ARROW} Updating dnf..."
        dnf update -y > /dev/null 2>&1

        for pkg in python3 python3-pip postgresql sqlite curl git; do
            install_package $pkg
            dnf install -y $pkg > /dev/null 2>&1 && echo -e "${CHECK}" || echo -e "${CROSS}"
        done
        ;;

    *)
        echo -e "  ${CROSS} Unsupported OS: $OS"
        echo -e "     ${DIM}Supported: Arch, Ubuntu, Debian, Fedora${NC}"
        exit 1
        ;;
esac

echo ""

# ============================================================================
# PYTHON ENVIRONMENT
# ============================================================================
echo -e "${BOLD}${WHITE}PYTHON ENVIRONMENT${NC}"
echo -e "${DIM}────────────────────────────────────────────────────${NC}"

INSTALL_DIR=$(pwd)
echo -e "  ${ARROW} Directory: ${CYAN}$INSTALL_DIR${NC}"

# Create venv
echo -ne "  ${ARROW} Creating virtual environment... "
python3 -m venv venv 2>/dev/null && echo -e "${CHECK}" || echo -e "${CROSS}"

# Activate
source venv/bin/activate

# Upgrade pip
echo -ne "  ${ARROW} Upgrading pip... "
pip install --upgrade pip > /dev/null 2>&1 && echo -e "${CHECK}" || echo -e "${CROSS}"

# Install requirements
echo -e "  ${ARROW} Installing Python packages..."
if [ -f requirements.txt ]; then
    pip install -r requirements.txt > /dev/null 2>&1
    PKGS=$(pip list 2>/dev/null | wc -l)
    echo -e "     ${CHECK} Installed ${CYAN}$PKGS${NC} packages"
else
    echo -e "     ${WARN} requirements.txt not found"
fi

echo ""

# ============================================================================
# LLM MODEL
# ============================================================================
echo -e "${BOLD}${WHITE}LLM MODEL (Phi-3)${NC}"
echo -e "${DIM}────────────────────────────────────────────────────${NC}"

MODEL_DIR="$INSTALL_DIR/llm"
MODEL_FILE="$MODEL_DIR/Phi-3-mini-4k-instruct-q4.gguf"
RELEASE_URL="https://github.com/prism-iq/pwnd/releases/download/v1.0"

mkdir -p "$MODEL_DIR"

if [ -f "$MODEL_FILE" ]; then
    SIZE=$(du -h "$MODEL_FILE" | cut -f1)
    echo -e "  ${CHECK} Model exists: ${CYAN}$SIZE${NC}"
else
    echo -e "  ${ARROW} Downloading Phi-3 (2.3GB)..."
    echo ""

    # Part 1
    echo -ne "     Part 1/2: "
    curl -L --progress-bar -o "$MODEL_DIR/model.partaa" "$RELEASE_URL/Phi-3-mini-4k-instruct-q4.gguf.partaa"

    # Part 2
    echo -ne "     Part 2/2: "
    curl -L --progress-bar -o "$MODEL_DIR/model.partab" "$RELEASE_URL/Phi-3-mini-4k-instruct-q4.gguf.partab"

    # Reassemble
    echo -ne "  ${ARROW} Reassembling... "
    cat "$MODEL_DIR"/model.part* > "$MODEL_FILE" 2>/dev/null
    rm -f "$MODEL_DIR"/model.part*

    if [ -f "$MODEL_FILE" ]; then
        SIZE=$(du -h "$MODEL_FILE" | cut -f1)
        echo -e "${CHECK} ${CYAN}$SIZE${NC}"
    else
        echo -e "${CROSS}"
    fi
fi

echo ""

# ============================================================================
# DATABASES
# ============================================================================
echo -e "${BOLD}${WHITE}DATABASES${NC}"
echo -e "${DIM}────────────────────────────────────────────────────${NC}"

mkdir -p db data/inbox

# Sessions DB
echo -ne "  ${ARROW} Sessions database... "
if [ -f "db/schema_sessions.sql" ]; then
    sqlite3 db/sessions.db < db/schema_sessions.sql 2>/dev/null
    echo -e "${CHECK}"
else
    touch db/sessions.db
    echo -e "${CHECK} ${DIM}(empty)${NC}"
fi

# Check other DBs
for db in sources graph scores audit; do
    echo -ne "  ${ARROW} ${db}.db... "
    if [ -f "db/${db}.db" ]; then
        SIZE=$(du -h "db/${db}.db" | cut -f1)
        echo -e "${CHECK} ${CYAN}$SIZE${NC}"
    else
        touch "db/${db}.db"
        echo -e "${WARN} ${DIM}needs data${NC}"
    fi
done

echo ""

# ============================================================================
# SYSTEMD SERVICES
# ============================================================================
echo -e "${BOLD}${WHITE}SYSTEMD SERVICES${NC}"
echo -e "${DIM}────────────────────────────────────────────────────${NC}"

# LLM Service
echo -ne "  ${ARROW} pwnd-llm.service... "
cat > /etc/systemd/system/pwnd-llm.service << EOF
[Unit]
Description=PWND.ICU LLM Server (Phi-3)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
Environment=PATH=$INSTALL_DIR/venv/bin:/usr/bin
ExecStart=$INSTALL_DIR/venv/bin/python llm/backend.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
echo -e "${CHECK}"

# API Service
echo -ne "  ${ARROW} pwnd-api.service... "
cat > /etc/systemd/system/pwnd-api.service << EOF
[Unit]
Description=PWND.ICU API Server (FastAPI)
After=network.target pwnd-llm.service

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
Environment=PATH=$INSTALL_DIR/venv/bin:/usr/bin
ExecStart=$INSTALL_DIR/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8002
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
echo -e "${CHECK}"

# Auto-improve Service (optional)
echo -ne "  ${ARROW} pwnd-auto.service... "
cat > /etc/systemd/system/pwnd-auto.service << EOF
[Unit]
Description=PWND.ICU Auto-Improvement Loop
After=network.target pwnd-api.service

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
Environment=PATH=$INSTALL_DIR/venv/bin:/usr/bin
ExecStart=$INSTALL_DIR/venv/bin/python auto_improve.py --loop
Restart=always
RestartSec=300

[Install]
WantedBy=multi-user.target
EOF
echo -e "${CHECK}"

# Reload systemd
systemctl daemon-reload

echo ""

# ============================================================================
# CADDY WEB SERVER
# ============================================================================
echo -e "${BOLD}${WHITE}WEB SERVER (Caddy)${NC}"
echo -e "${DIM}────────────────────────────────────────────────────${NC}"

echo -ne "  ${ARROW} Creating Caddyfile... "
cat > Caddyfile << 'EOF'
# PWND.ICU - Investigation Platform
# Change :80 to your domain for production

:80 {
    root * static
    file_server

    # API proxy
    handle /api/* {
        reverse_proxy 127.0.0.1:8002
    }

    # Security headers
    header {
        X-Content-Type-Options nosniff
        X-Frame-Options DENY
        Referrer-Policy strict-origin-when-cross-origin
    }
}

# Production config (uncomment and set your domain):
# pwnd.icu {
#     root * static
#     file_server
#
#     handle /api/* {
#         reverse_proxy 127.0.0.1:8002
#     }
#
#     header {
#         X-Content-Type-Options nosniff
#         X-Frame-Options DENY
#         Strict-Transport-Security "max-age=31536000; includeSubDomains"
#     }
# }
EOF
echo -e "${CHECK}"

echo -ne "  ${ARROW} Enabling Caddy... "
systemctl enable caddy > /dev/null 2>&1 && echo -e "${CHECK}" || echo -e "${CROSS}"

echo ""

# ============================================================================
# FINAL SETUP
# ============================================================================
echo -e "${BOLD}${WHITE}FINAL SETUP${NC}"
echo -e "${DIM}────────────────────────────────────────────────────${NC}"

# Create .env if missing
echo -ne "  ${ARROW} Environment file... "
if [ ! -f ".env" ]; then
    cat > .env << 'EOF'
# PWND.ICU Configuration
LLM_BACKEND=http://127.0.0.1:8001
DATABASE_PATH=./db
LOG_LEVEL=INFO
EOF
    echo -e "${CHECK} ${DIM}created${NC}"
else
    echo -e "${CHECK} ${DIM}exists${NC}"
fi

# Create start/stop scripts
echo -ne "  ${ARROW} Control scripts... "

cat > start.sh << 'EOF'
#!/bin/bash
echo "Starting PWND.ICU services..."
sudo systemctl start pwnd-llm pwnd-api caddy
sleep 2
echo ""
echo "Services status:"
systemctl is-active pwnd-llm pwnd-api caddy
echo ""
echo "Access: http://localhost or https://your-domain"
EOF
chmod +x start.sh

cat > stop.sh << 'EOF'
#!/bin/bash
echo "Stopping PWND.ICU services..."
sudo systemctl stop pwnd-llm pwnd-api caddy pwnd-auto
echo "Done."
EOF
chmod +x stop.sh

cat > status.sh << 'EOF'
#!/bin/bash
echo "PWND.ICU Service Status"
echo "━━━━━━━━━━━━━━━━━━━━━━━"
for svc in pwnd-llm pwnd-api caddy pwnd-auto; do
    status=$(systemctl is-active $svc 2>/dev/null || echo "not installed")
    if [ "$status" = "active" ]; then
        echo -e "  ✓ $svc: \033[0;32m$status\033[0m"
    else
        echo -e "  ✗ $svc: \033[0;31m$status\033[0m"
    fi
done
echo ""
echo "API Health:"
curl -s http://localhost:8002/api/health 2>/dev/null || echo "  API not responding"
EOF
chmod +x status.sh

echo -e "${CHECK}"

echo ""

# ============================================================================
# COMPLETE
# ============================================================================
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  INSTALLATION COMPLETE${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${WHITE}Quick Start:${NC}"
echo -e "  ${CYAN}./start.sh${NC}        Start all services"
echo -e "  ${CYAN}./stop.sh${NC}         Stop all services"
echo -e "  ${CYAN}./status.sh${NC}       Check service status"
echo ""
echo -e "${WHITE}Services:${NC}"
echo -e "  ${DIM}pwnd-llm${NC}   Phi-3 LLM backend    ${DIM}(port 8001)${NC}"
echo -e "  ${DIM}pwnd-api${NC}   FastAPI application  ${DIM}(port 8002)${NC}"
echo -e "  ${DIM}caddy${NC}      Web server           ${DIM}(port 80/443)${NC}"
echo -e "  ${DIM}pwnd-auto${NC}  Auto-improvement     ${DIM}(optional)${NC}"
echo ""
echo -e "${WHITE}Data Import:${NC}"
echo -e "  1. Place documents in ${CYAN}data/inbox/${NC}"
echo -e "  2. Run ${CYAN}python auto_improve.py${NC} to ingest"
echo -e "  3. Or use the web UI: ${CYAN}Ingest Documents${NC} button"
echo ""
echo -e "${WHITE}Access:${NC}"
echo -e "  Local:  ${CYAN}http://localhost${NC}"
echo -e "  Config: Edit ${CYAN}Caddyfile${NC} for your domain"
echo ""
echo -e "${DIM}────────────────────────────────────────────────────${NC}"
echo -e "${DIM}\"Evil must be fought wherever it is found.\"${NC}"
echo -e "${DIM}────────────────────────────────────────────────────${NC}"
echo ""
