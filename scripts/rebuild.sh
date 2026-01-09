#!/bin/bash
set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=========================================${NC}"
echo -e "${BLUE}  Rebuilding L Investigation Framework  ${NC}"
echo -e "${BLUE}=========================================${NC}"
echo ""

# Check if .env exists
if [ ! -f ".env" ]; then
    echo -e "${RED}Error: .env file not found${NC}"
    echo "Create .env from .env.example and add your API keys"
    exit 1
fi

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${YELLOW}Warning: Not running as root. May need sudo for systemctl commands.${NC}"
fi

# Stop services
echo -e "${GREEN}[1/5]${NC} Stopping services..."
if command -v systemctl &> /dev/null; then
    sudo systemctl stop l-llm l-api caddy 2>/dev/null || true
fi

# Activate virtual environment
echo -e "${GREEN}[2/5]${NC} Activating virtual environment..."
source venv/bin/activate

# Reinstall dependencies
echo -e "${GREEN}[3/5]${NC} Updating Python dependencies..."
pip install --upgrade -r requirements.txt

# Check databases
echo -e "${GREEN}[4/5]${NC} Checking databases..."
if [ ! -f "db/sources.db" ]; then
    echo -e "${YELLOW}  Warning: db/sources.db not found${NC}"
fi

if [ ! -f "db/graph.db" ]; then
    echo -e "${YELLOW}  Warning: db/graph.db not found${NC}"
fi

if [ ! -f "db/sessions.db" ]; then
    echo "  Creating sessions.db..."
    sqlite3 db/sessions.db < db/schema_sessions.sql
fi

# Start services
echo -e "${GREEN}[5/5]${NC} Starting services..."
if command -v systemctl &> /dev/null; then
    sudo systemctl daemon-reload
    sudo systemctl start l-llm
    echo "  Waiting for LLM to initialize (10 seconds)..."
    sleep 10
    sudo systemctl start l-api
    sudo systemctl start caddy

    echo ""
    echo -e "${GREEN}Service status:${NC}"
    sudo systemctl status l-llm --no-pager | head -3
    sudo systemctl status l-api --no-pager | head -3
    sudo systemctl status caddy --no-pager | head -3
fi

echo ""
echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}  Rebuild Complete!${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""
echo -e "${GREEN}Access the application:${NC}"
echo "  • Local:  http://localhost"
echo "  • API:    http://localhost/api/stats"
echo ""
echo -e "${YELLOW}View logs:${NC}"
echo "  sudo journalctl -u l-llm -f"
echo "  sudo journalctl -u l-api -f"
echo ""
