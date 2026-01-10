#!/bin/bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

cd /opt/rag

echo -e "${GREEN}[1/7]${NC} Stopping all services..."
systemctl stop l-api l-go-search l-llm caddy 2>/dev/null || true
sleep 2

echo -e "${GREEN}[2/7]${NC} Loading environment..."
source .env
export DATABASE_URL

echo -e "${GREEN}[3/7]${NC} Activating venv and checking deps..."
source venv/bin/activate
pip install -q httpx psycopg2-binary fastapi uvicorn llama-cpp-python 2>/dev/null

echo -e "${GREEN}[4/7]${NC} Verifying PostgreSQL..."
sudo -u postgres psql ldb -c "SELECT COUNT(*) FROM emails;" || {
    echo -e "${RED}PostgreSQL error${NC}"
    exit 1
}

echo -e "${GREEN}[5/7]${NC} Building Go service..."
cd /opt/rag/go-search
go build -o search-service . 2>/dev/null || echo "Go build skipped"
cd /opt/rag

echo -e "${GREEN}[6/7]${NC} Starting services..."
systemctl daemon-reload

# Start in order
systemctl start l-llm
echo "  Waiting for LLM (8s)..."
sleep 8

systemctl start l-go-search
sleep 1

systemctl start l-api
echo "  Waiting for API (6s)..."
sleep 6

systemctl start caddy

echo -e "${GREEN}[7/7]${NC} Health checks..."
echo -n "  Go search: "
curl -s http://127.0.0.1:8003/health | grep -q ok && echo -e "${GREEN}OK${NC}" || echo -e "${RED}FAIL${NC}"

echo -n "  API: "
curl -s http://127.0.0.1:8002/api/health | grep -q ok && echo -e "${GREEN}OK${NC}" || echo -e "${RED}FAIL${NC}"

echo -n "  Caddy: "
curl -s http://127.0.0.1:80 > /dev/null && echo -e "${GREEN}OK${NC}" || echo -e "${RED}FAIL${NC}"

echo ""
echo -e "${GREEN}=== REBUILD COMPLETE ===${NC}"
echo "Test: https://pwnd.icu"
