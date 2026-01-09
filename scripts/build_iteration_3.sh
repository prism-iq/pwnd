#!/bin/bash
# Build Script - Iteration 3: GitHub Push
# Run: ./scripts/build_iteration_3.sh
#
# Prerequisites:
#   gh auth login  (GitHub CLI authentication)

set -e
cd /opt/rag

echo "=== ITERATION 3: GITHUB PUSH ==="

# 1. Verify services
echo "[1/6] Verifying services..."
systemctl is-active l-api >/dev/null && echo "  l-api: OK" || echo "  l-api: FAILED"
systemctl is-active l-llm >/dev/null && echo "  l-llm: OK" || echo "  l-llm: FAILED"
systemctl is-active caddy >/dev/null && echo "  caddy: OK" || echo "  caddy: FAILED"

# 2. Health check
echo "[2/6] Running health checks..."
curl -s http://localhost:8002/api/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  API Health: {d[\"status\"]}')"
curl -s https://pwnd.icu/api/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  Public Health: {d[\"status\"]}')" 2>/dev/null || echo "  Public: not reachable (OK for local)"

# 3. Test auth
echo "[3/6] Testing auth..."
RESULT=$(curl -s http://localhost:8002/api/auth/verify)
echo "  Auth verify: $RESULT"

# 4. Check GitHub CLI
echo "[4/6] Checking GitHub CLI..."
if gh auth status >/dev/null 2>&1; then
    echo "  gh: authenticated"
    GH_OK=1
else
    echo "  gh: NOT authenticated"
    echo ""
    echo "  Run: gh auth login"
    echo "  Then re-run this script"
    GH_OK=0
fi

# 5. Commit any remaining changes
echo "[5/6] Checking for uncommitted changes..."
if [ -n "$(git status --porcelain)" ]; then
    echo "  Staging and committing remaining changes..."
    git add -A
    git commit -m "docs: Update CLAUDE.md with auth documentation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
else
    echo "  No uncommitted changes"
fi

# 6. GitHub push (if authenticated)
echo "[6/6] GitHub setup..."
if [ "$GH_OK" = "1" ]; then
    # Check if remote exists
    if git remote get-url origin >/dev/null 2>&1; then
        echo "  Remote 'origin' already exists"
        git push origin main
    else
        echo "  Creating GitHub repo..."
        gh repo create l-investigation-framework \
            --public \
            --source=. \
            --remote=origin \
            --push \
            --description "OSINT investigation framework with RAG, PostgreSQL, and Phi-3 LLM"
    fi

    # Create tag
    echo "  Creating v1.0.0 tag..."
    git tag -a v1.0.0 -m "Initial release - L Investigation Framework

Features:
- OSINT RAG chatbot with detective persona
- PostgreSQL backend with full-text search
- Phi-3 LLM (local) + Haiku (API) hybrid
- Secure auth with Argon2id
- TLS 1.3 + security headers

The Code: Evil must be fought wherever it is found."

    git push origin v1.0.0

    echo ""
    echo "=== SUCCESS ==="
    REPO_URL=$(gh repo view --json url -q '.url' 2>/dev/null || echo "https://github.com/YOUR_USERNAME/l-investigation-framework")
    echo "Repository: $REPO_URL"
    echo "Tag: v1.0.0"
else
    echo ""
    echo "=== MANUAL STEPS REQUIRED ==="
    echo "1. gh auth login"
    echo "2. ./scripts/build_iteration_3.sh"
    echo ""
    echo "Or manually:"
    echo "  git remote add origin https://github.com/YOUR_USERNAME/l-investigation-framework.git"
    echo "  git push -u origin main"
    echo "  git tag -a v1.0.0 -m 'Initial release'"
    echo "  git push origin v1.0.0"
fi

echo ""
echo "=== ITERATION 3 COMPLETE ==="
