#!/bin/bash
# Build Script - Iteration 1: Auth System
# Run: sudo ./scripts/build_iteration_1.sh

set -e
cd /opt/rag

echo "=== ITERATION 1: AUTH SYSTEM ==="

# 1. PostgreSQL Auth Tables
echo "[1/5] Creating auth tables..."
# Load password from environment or use default dev password
DB_PASS="${PGPASSWORD:-$(grep -oP 'postgresql://[^:]+:\K[^@]+' /opt/rag/.env 2>/dev/null || echo 'changeme')}"
PGPASSWORD="$DB_PASS" psql -U lframework -d ldb -h localhost << 'SQL'
CREATE EXTENSION IF NOT EXISTS pgcrypto;

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

CREATE TABLE IF NOT EXISTS password_resets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,
    used BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_sessions_token ON user_sessions(token_hash);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON user_sessions(user_id);
SQL
echo "Done."

# 2. Caddy Security Headers
echo "[2/5] Configuring Caddy security headers..."
cat > /etc/caddy/Caddyfile << 'CADDY'
pwnd.icu {
    reverse_proxy localhost:8002

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        X-XSS-Protection "1; mode=block"
        Referrer-Policy "strict-origin-when-cross-origin"
        Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'"
        Permissions-Policy "geolocation=(), microphone=(), camera=()"
    }
}
CADDY
systemctl reload caddy
echo "Done."

# 3. Install dependencies
echo "[3/5] Installing auth dependencies..."
source venv/bin/activate
pip install argon2-cffi python-jose[cryptography] email-validator --quiet
echo "Done."

# 4. Generate SECRET_KEY if not exists
echo "[4/5] Checking SECRET_KEY..."
if ! grep -q "SECRET_KEY=" .env 2>/dev/null; then
    SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    echo "SECRET_KEY=$SECRET" >> .env
    echo "Generated new SECRET_KEY"
else
    echo "SECRET_KEY already exists"
fi

# 5. Restart services
echo "[5/5] Restarting services..."
systemctl restart l-api
sleep 2

# Verify
echo ""
echo "=== VERIFICATION ==="
curl -s http://localhost:8002/api/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'API: {d[\"status\"]}')"
echo ""

# Test auth
echo "Testing auth endpoints..."
RESULT=$(curl -s -X POST http://localhost:8002/api/auth/register \
    -H "Content-Type: application/json" \
    -d '{"email":"buildtest@test.com","password":"BuildTest123"}' 2>&1)

if echo "$RESULT" | grep -q "access_token"; then
    echo "Auth: OK (registration works)"
elif echo "$RESULT" | grep -q "already registered"; then
    echo "Auth: OK (user exists)"
else
    echo "Auth: FAILED"
    echo "$RESULT"
fi

echo ""
echo "=== ITERATION 1 COMPLETE ==="
