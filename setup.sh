#!/bin/bash
set -e

echo "========================================="
echo "  pwnd.icu - OSINT Investigation Setup  "
echo "========================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root (use sudo)${NC}"
    exit 1
fi

echo -e "${GREEN}[1/8]${NC} Installing system dependencies..."
pacman -S --noconfirm python python-pip python-virtualenv nginx certbot certbot-nginx || {
    echo -e "${YELLOW}Note: Using apt-get for Debian/Ubuntu systems${NC}"
    apt-get update
    apt-get install -y python3 python3-pip python3-venv nginx certbot python3-certbot-nginx
}

echo -e "${GREEN}[2/8]${NC} Creating virtual environment..."
cd /opt/rag
python3 -m venv venv

echo -e "${GREEN}[3/8]${NC} Installing Python dependencies..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo -e "${GREEN}[4/8]${NC} Setting up databases..."
# Create database directories if they don't exist
mkdir -p db

# Initialize databases (schemas should already exist)
if [ ! -f "db/sources.db" ]; then
    echo -e "${YELLOW}Warning: db/sources.db not found. You need to import your email data.${NC}"
fi

if [ ! -f "db/graph.db" ]; then
    echo -e "${YELLOW}Warning: db/graph.db not found. You need to build the graph database.${NC}"
fi

# Create sessions.db if it doesn't exist
if [ ! -f "db/sessions.db" ]; then
    echo "Creating sessions.db..."
    sqlite3 db/sessions.db < db/schema_sessions.sql
fi

echo -e "${GREEN}[5/8]${NC} Setting up Mistral LLM backend..."
# Check if backend.py exists
if [ ! -f "backend.py" ]; then
    echo -e "${RED}Error: backend.py not found${NC}"
    exit 1
fi

echo -e "${GREEN}[6/8]${NC} Creating systemd services..."

# Create l-llm service
cat > /etc/systemd/system/l-llm.service << 'EOF'
[Unit]
Description=L Investigation LLM Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/rag
Environment=PATH=/opt/rag/venv/bin:/usr/bin
ExecStart=/opt/rag/venv/bin/python backend.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# Create l-api service
cat > /etc/systemd/system/l-api.service << 'EOF'
[Unit]
Description=L Investigation API
After=network.target l-llm.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/rag
Environment=PATH=/opt/rag/venv/bin:/usr/bin
ExecStart=/opt/rag/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8002
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

echo -e "${GREEN}[7/8]${NC} Enabling and starting services..."
systemctl daemon-reload
systemctl enable l-llm l-api
systemctl start l-llm
sleep 5  # Wait for LLM to start
systemctl start l-api

echo -e "${GREEN}[8/8]${NC} Configuring Nginx..."

# Backup existing nginx config if exists
if [ -f "/etc/nginx/sites-available/pwnd.icu" ]; then
    cp /etc/nginx/sites-available/pwnd.icu /etc/nginx/sites-available/pwnd.icu.bak
fi

cat > /etc/nginx/sites-available/pwnd.icu << 'EOF'
server {
    listen 80;
    server_name pwnd.icu www.pwnd.icu;

    # Static files
    location / {
        root /opt/rag/static;
        try_files $uri $uri/ /index.html;
    }

    # API proxy
    location /api/ {
        proxy_pass http://127.0.0.1:8002;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        # SSE support
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 600s;
    }
}
EOF

# Enable site
ln -sf /etc/nginx/sites-available/pwnd.icu /etc/nginx/sites-enabled/
nginx -t && systemctl restart nginx

echo ""
echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}  Installation Complete!${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""
echo -e "Services status:"
systemctl status l-llm --no-pager | head -3
systemctl status l-api --no-pager | head -3
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Import your email data to db/sources.db"
echo "2. Build the graph database to db/graph.db"
echo "3. Configure your domain DNS to point to this server"
echo "4. Run: certbot --nginx -d pwnd.icu -d www.pwnd.icu"
echo ""
echo -e "${GREEN}Access your instance:${NC}"
echo "  - Local: http://localhost"
echo "  - Public: http://pwnd.icu (after DNS setup)"
echo ""
