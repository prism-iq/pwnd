#!/bin/bash
# L Investigation - Polyglot Test Suite
# Languages: Bash, Rust, Go, Python, Node.js

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${BLUE}[BASH]${NC} $1"; }
ok() { echo -e "${GREEN}[OK]${NC} $1"; }
err() { echo -e "${RED}[ERR]${NC} $1"; }

cd /opt/rag

# ==============================================================================
# 1. RUST EXTRACTION TEST
# ==============================================================================
log "Testing Rust extraction..."

RUST_BIN="rust-extract/target/release/l-extract"
if [ -f "$RUST_BIN" ]; then
    TEST_TEXT="John Smith met with Acme Corp in New York on 2024-01-15. Payment of \$50,000 was made."
    RUST_RESULT=$($RUST_BIN --text "$TEST_TEXT" 2>/dev/null || echo '{"error":"failed"}')
    if echo "$RUST_RESULT" | grep -q "persons"; then
        RUST_COUNT=$(echo "$RUST_RESULT" | grep -o '"total_count":[0-9]*' | cut -d: -f2)
        ok "Rust extracted $RUST_COUNT entities"
    else
        err "Rust extraction failed"
    fi
else
    err "Rust binary not found"
fi

# ==============================================================================
# 2. GO GATEWAY TEST
# ==============================================================================
log "Testing Go gateway..."

GO_BIN="go-gateway/l-gateway"
if [ -f "$GO_BIN" ]; then
    # Start gateway briefly
    $GO_BIN --port 8090 &
    GO_PID=$!
    sleep 1

    if curl -s http://localhost:8090/health | grep -q "ok"; then
        ok "Go gateway responding"
    else
        err "Go gateway not responding"
    fi

    kill $GO_PID 2>/dev/null || true
else
    err "Go binary not found"
fi

# ==============================================================================
# 3. PYTHON API TEST
# ==============================================================================
log "Testing Python API..."

source venv/bin/activate
PYTHON_RESULT=$(python3 -c "
from app.pipeline import fast_extract_entities
result = fast_extract_entities('Jeffrey Epstein flew to Virgin Islands with Bill Clinton')
print(f'persons={len(result.get(\"persons\", []))} locations={len(result.get(\"locations\", []))} patterns={len(result.get(\"patterns\", []))}')
")
ok "Python: $PYTHON_RESULT"

# ==============================================================================
# 4. SPEED COMPARISON
# ==============================================================================
log "Speed comparison..."

# Rust speed
if [ -f "$RUST_BIN" ]; then
    RUST_TIME=$( { time $RUST_BIN --text "$(cat <<'EOF'
Jeffrey Epstein was connected to Ghislaine Maxwell. They traveled to Little St. James Island
on private jets. Multiple wire transfers totaling $5,000,000 were made to offshore accounts
in the Cayman Islands. Settlement agreements were signed with victims. The FBI investigation
revealed connections to powerful individuals. Court documents were sealed.
EOF
)" > /dev/null 2>&1; } 2>&1 | grep real | awk '{print $2}')
    ok "Rust extraction: $RUST_TIME"
fi

# Python speed
PYTHON_TIME=$( { time python3 -c "
from app.pipeline import fast_extract_entities
text = '''Jeffrey Epstein was connected to Ghislaine Maxwell. They traveled to Little St. James Island
on private jets. Multiple wire transfers totaling \$5,000,000 were made to offshore accounts
in the Cayman Islands. Settlement agreements were signed with victims. The FBI investigation
revealed connections to powerful individuals. Court documents were sealed.'''
for _ in range(100):
    fast_extract_entities(text)
" > /dev/null 2>&1; } 2>&1 | grep real | awk '{print $2}')
ok "Python 100x extraction: $PYTHON_TIME"

# ==============================================================================
# 5. FULL PIPELINE TEST (20 QUERIES)
# ==============================================================================
log "Running 20-query pipeline test..."

python3 test_20_auto.py 2>&1 | tail -15

# ==============================================================================
# SUMMARY
# ==============================================================================
echo ""
echo "======================================================================"
echo "POLYGLOT TEST COMPLETE"
echo "======================================================================"
echo "Languages used:"
echo "  - Bash: orchestration, scripting"
echo "  - Rust: high-speed extraction (rayon parallelism)"
echo "  - Go: API gateway (goroutines, rate limiting)"
echo "  - Python: main pipeline, LLM integration"
echo "======================================================================"
