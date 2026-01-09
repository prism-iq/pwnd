#!/bin/bash
# Build Script - Iteration 2: Cleanup + Git Prep
# Run: ./scripts/build_iteration_2.sh

set -e
cd /opt/rag

echo "=== ITERATION 2: CLEANUP + GIT PREP ==="

# 1. Clean temp files
echo "[1/5] Cleaning temp files..."
rm -f *.tmp *.bak test_*.txt diagnostic_results.txt 2>/dev/null || true
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true
echo "Done."

# 2. Check for secrets
echo "[2/5] Checking for secrets..."
SECRETS=$(grep -rn "sk-ant-api\|password.*=.*['\"][a-zA-Z0-9]" --include="*.py" --include="*.sh" . 2>/dev/null | \
    grep -v ".env" | grep -v ".example" | grep -v "your-" | grep -v "changeme" | grep -v "xxx" | grep -v "archive/" | grep -v "\$" || true)

if [ -n "$SECRETS" ]; then
    echo "WARNING: Potential secrets found:"
    echo "$SECRETS"
    exit 1
else
    echo "No secrets in tracked files."
fi

# 3. Verify .gitignore
echo "[3/5] Verifying .gitignore..."
REQUIRED_IGNORES=(".env" "venv/" "*.db" "*.gguf" "archive/" ".claude/")
for item in "${REQUIRED_IGNORES[@]}"; do
    if grep -q "$item" .gitignore; then
        echo "  [OK] $item"
    else
        echo "  [MISSING] $item"
    fi
done

# 4. Git status
echo "[4/5] Git status..."
git status --short

# 5. Dry run - what would be committed
echo "[5/5] Files to be committed:"
git diff --cached --stat 2>/dev/null || echo "(nothing staged yet)"

echo ""
echo "=== ITERATION 2 COMPLETE ==="
echo ""
echo "Next: Run iteration 3 to commit and push:"
echo "  ./scripts/build_iteration_3.sh"
