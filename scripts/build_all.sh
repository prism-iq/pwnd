#!/bin/bash
# Master Build Script - All Iterations
# Run: sudo ./scripts/build_all.sh
#
# This script runs all 3 iterations in sequence:
# 1. Auth system setup (DB, Caddy, dependencies)
# 2. Cleanup and git prep
# 3. GitHub push (requires gh auth login first)

set -e
cd /opt/rag

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║       L INVESTIGATION FRAMEWORK - FULL BUILD                 ║"
echo "║       'Evil must be fought wherever it is found'             ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Check if running as root for iteration 1
if [ "$EUID" -ne 0 ]; then
    echo "WARNING: Some operations require root. Run with sudo for full setup."
    echo ""
fi

# Iteration 1: Auth System
echo "┌──────────────────────────────────────────────────────────────┐"
echo "│ ITERATION 1: Auth System                                     │"
echo "└──────────────────────────────────────────────────────────────┘"
./scripts/build_iteration_1.sh
echo ""

# Iteration 2: Cleanup
echo "┌──────────────────────────────────────────────────────────────┐"
echo "│ ITERATION 2: Cleanup + Git Prep                              │"
echo "└──────────────────────────────────────────────────────────────┘"
./scripts/build_iteration_2.sh
echo ""

# Iteration 3: GitHub
echo "┌──────────────────────────────────────────────────────────────┐"
echo "│ ITERATION 3: GitHub Push                                     │"
echo "└──────────────────────────────────────────────────────────────┘"
./scripts/build_iteration_3.sh
echo ""

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                    BUILD COMPLETE                            ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Services:"
systemctl is-active l-api l-llm caddy 2>/dev/null | paste - - - || true
echo ""
echo "Health: $(curl -s http://localhost:8002/api/health | python3 -c 'import sys,json; print(json.load(sys.stdin).get(\"status\",\"unknown\"))' 2>/dev/null || echo 'unknown')"
echo ""
echo "Auth test:"
curl -s http://localhost:8002/api/auth/verify | python3 -m json.tool 2>/dev/null || echo '{"error":"failed"}'
