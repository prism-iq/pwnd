#!/bin/bash
set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=========================================${NC}"
echo -e "${BLUE}  L Investigation Framework - Install   ${NC}"
echo -e "${BLUE}=========================================${NC}"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: Please run as root (use sudo)${NC}"
    exit 1
fi

# Detect OS
echo -e "${GREEN}[1/7]${NC} Detecting operating system..."
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
    echo -e "  Detected: ${YELLOW}$PRETTY_NAME${NC}"
else
    echo -e "${RED}Error: Cannot detect OS${NC}"
    exit 1
fi

# Install system dependencies
echo -e "${GREEN}[2/7]${NC} Installing system dependencies..."
case $OS in
    arch|manjaro)
        pacman -Syu --noconfirm
        pacman -S --noconfirm python python-pip sqlite caddy
        ;;
    ubuntu|debian)
        apt-get update
        apt-get install -y python3 python3-pip python3-venv sqlite3 caddy
        # Create python symlink if needed
        if ! command -v python &> /dev/null; then
            ln -s /usr/bin/python3 /usr/bin/python
        fi
        ;;
    *)
        echo -e "${RED}Error: Unsupported OS: $OS${NC}"
        echo "Supported: Arch, Ubuntu, Debian"
        exit 1
        ;;
esac

# Get installation directory
INSTALL_DIR=$(pwd)
echo -e "  Install directory: ${YELLOW}$INSTALL_DIR${NC}"

# Create virtual environment
echo -e "${GREEN}[3/7]${NC} Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo -e "${GREEN}[4/7]${NC} Installing Python packages..."
pip install --upgrade pip
pip install -r requirements.txt

# Setup database directories
echo -e "${GREEN}[5/7]${NC} Setting up databases..."
mkdir -p db

# Create sessions database with schema
if [ -f "db/schema_sessions.sql" ]; then
    echo "  Creating sessions.db..."
    sqlite3 db/sessions.db < db/schema_sessions.sql
else
    echo -e "${YELLOW}  Warning: db/schema_sessions.sql not found${NC}"
fi

# Check for other database schemas
if [ ! -f "db/sources.db" ]; then
    echo -e "${YELLOW}  Note: db/sources.db will need to be created${NC}"
    echo -e "        Import your email data later"
fi

if [ ! -f "db/graph.db" ]; then
    echo -e "${YELLOW}  Note: db/graph.db will need to be created${NC}"
    echo -e "        Build graph from email data later"
fi

# Setup systemd services
echo -e "${GREEN}[6/7]${NC} Creating systemd services..."

cat > /etc/systemd/system/l-llm.service << EOF
[Unit]
Description=L Investigation LLM Server (Mistral 7B)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
Environment=PATH=$INSTALL_DIR/venv/bin:/usr/bin
ExecStart=$INSTALL_DIR/venv/bin/python backend.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/l-api.service << EOF
[Unit]
Description=L Investigation API (FastAPI)
After=network.target l-llm.service

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

# Reload systemd
systemctl daemon-reload

# Configure Caddy
echo -e "${GREEN}[7/7]${NC} Configuring Caddy web server..."

# Create Caddyfile if doesn't exist
if [ ! -f "Caddyfile" ]; then
    cat > Caddyfile << 'EOF'
# Development (localhost)
:80 {
    root * static
    file_server

    # API reverse proxy
    handle /api/* {
        reverse_proxy 127.0.0.1:8002
    }
}

# Production (uncomment and configure your domain)
# pwnd.icu {
#     root * static
#     file_server
#
#     handle /api/* {
#         reverse_proxy 127.0.0.1:8002
#     }
# }
EOF
fi

# Enable Caddy service
systemctl enable caddy

echo ""
echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}  Installation Complete!${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo ""
echo -e "1. Create ${BLUE}.env${NC} file with your configuration:"
echo "   cp .env.example .env"
echo "   nano .env  # Add your API keys"
echo ""
echo -e "2. Download Mistral 7B model (if not present):"
echo "   wget https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf"
echo "   mv mistral-7b-instruct-v0.2.Q4_K_M.gguf models/"
echo ""
echo -e "3. Import your email data to ${BLUE}db/sources.db${NC}"
echo ""
echo -e "4. Build graph database to ${BLUE}db/graph.db${NC}"
echo ""
echo -e "5. Run the rebuild script:"
echo "   ./scripts/rebuild.sh"
echo ""
echo -e "${GREEN}Services installed (not started yet):${NC}"
echo "  • l-llm.service  - Mistral LLM backend"
echo "  • l-api.service  - FastAPI application"
echo "  • caddy.service  - Web server"
echo ""
echo -e "${YELLOW}Start services with:${NC}"
echo "  sudo systemctl start l-llm l-api caddy"
echo ""
