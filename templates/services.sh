#!/bin/bash
# templates/services.sh - Generates systemd units and Caddy config

set -e

echo "Generating service files..."

# systemd: l-api.service
cat > /etc/systemd/system/l-api.service << 'SERVICEEOF'
[Unit]
Description=L Investigation API
After=network.target

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
SERVICEEOF

# systemd: l-llm.service
cat > /etc/systemd/system/l-llm.service << 'SERVICEEOF'
[Unit]
Description=L Investigation LLM Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/rag/llm
ExecStart=/opt/rag/venv/bin/python backend.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICEEOF

# Caddy config
cat > /etc/caddy/Caddyfile << 'CADDYEOF'
pwnd.icu {
    reverse_proxy /api/* 127.0.0.1:8002
    reverse_proxy 127.0.0.1:8002

    encode gzip

    header {
        X-Content-Type-Options nosniff
        X-Frame-Options DENY
        X-XSS-Protection "1; mode=block"
        Referrer-Policy strict-origin-when-cross-origin
        Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"
    }
}
CADDYEOF

echo "✓ Service files generated"
echo "Note: Run 'systemctl daemon-reload' to reload systemd units"
