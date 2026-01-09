#!/bin/bash
# L Investigation Framework - Final Rebuild Script
# Run: sudo ./scripts/rebuild_final.sh
#
# This script rebuilds the entire system from scratch

set -e
cd /opt/rag

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║       L INVESTIGATION FRAMEWORK - FINAL REBUILD              ║"
echo "║       'Evil must be fought wherever it is found'             ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# 1. Stop services
echo "[1/7] Stopping services..."
systemctl stop l-api 2>/dev/null || true
sleep 1

# 2. Install dependencies
echo "[2/7] Installing Python dependencies..."
source venv/bin/activate
pip install --quiet \
    argon2-cffi \
    python-jose[cryptography] \
    email-validator \
    psycopg2-binary \
    httpx

# 3. Database setup
echo "[3/7] Setting up database tables..."
DB_PASS="${PGPASSWORD:-$(grep -oP 'postgresql://[^:]+:\K[^@]+' /opt/rag/.env 2>/dev/null || echo 'changeme')}"
PGPASSWORD="$DB_PASS" psql -U lframework -d ldb -h localhost << 'SQL'
-- Auth tables
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    email_verified BOOLEAN DEFAULT FALSE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    last_login TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    role VARCHAR(50) DEFAULT 'user'
);

CREATE TABLE IF NOT EXISTS user_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,
    ip_address INET,
    user_agent TEXT
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_sessions_token ON user_sessions(token_hash);

-- Session tables (for conversations)
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    is_auto INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS auto_sessions (
    id SERIAL PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    status TEXT DEFAULT 'running',
    query_count INTEGER DEFAULT 0,
    max_queries INTEGER DEFAULT 20,
    started_at TIMESTAMP DEFAULT NOW(),
    stopped_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_auto_conv ON auto_sessions(conversation_id);
SQL
echo "  Done."

# 4. Generate SECRET_KEY if missing
echo "[4/7] Checking environment..."
if ! grep -q "SECRET_KEY=" .env 2>/dev/null; then
    SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    echo "SECRET_KEY=$SECRET" >> .env
    echo "  Generated SECRET_KEY"
else
    echo "  SECRET_KEY exists"
fi

# 5. Test Python imports
echo "[5/7] Testing Python imports..."
python3 -c "from app.main import app; print('  app.main: OK')"
python3 -c "from app.pipeline import process_query; print('  app.pipeline: OK')"
python3 -c "from app.auth import hash_password; print('  app.auth: OK')"

# 6. Restart services
echo "[6/7] Starting services..."
systemctl start l-api
sleep 2

# 7. Verify
echo "[7/7] Verifying..."
echo ""
echo "Services:"
systemctl is-active l-api && echo "  l-api: RUNNING" || echo "  l-api: FAILED"
systemctl is-active l-llm && echo "  l-llm: RUNNING" || echo "  l-llm: FAILED"
systemctl is-active caddy && echo "  caddy: RUNNING" || echo "  caddy: FAILED"

echo ""
echo "Health check:"
curl -s http://localhost:8002/api/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  Status: {d[\"status\"]}')"

echo ""
echo "Stats:"
curl -s http://localhost:8002/api/stats | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  Documents: {d[\"sources\"]}'); print(f'  Nodes: {d[\"nodes\"]}'); print(f'  Edges: {d[\"edges\"]}')"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                    REBUILD COMPLETE                          ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Frontend: https://pwnd.icu"
echo "API: http://localhost:8002/api/health"
echo ""
echo "Test query:"
echo "  curl 'http://localhost:8002/api/ask?q=test'"
