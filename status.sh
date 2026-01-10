#!/bin/bash
echo "PWND.ICU Service Status"
echo "━━━━━━━━━━━━━━━━━━━━━━━"
for svc in pwnd-llm pwnd-api caddy pwnd-auto; do
    status=$(systemctl is-active $svc 2>/dev/null || echo "not installed")
    if [ "$status" = "active" ]; then
        echo -e "  ✓ $svc: \033[0;32m$status\033[0m"
    else
        echo -e "  ✗ $svc: \033[0;31m$status\033[0m"
    fi
done
echo ""
echo "API Health:"
curl -s http://localhost:8002/api/health 2>/dev/null || echo "  API not responding"
