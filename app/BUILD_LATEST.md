# Build State - 2026-01-08 03:47

## Services Status
- ✅ l-api: ACTIVE (127.0.0.1:8002)
- ✅ l-llm: ACTIVE (127.0.0.1:8001)
- ✅ caddy: ACTIVE (80/443)

## Last Changes (Iteration 01)
1. Detective system prompt: 3000 tokens (criminal focus)
2. Rate limiter: 30€/mois budget protection
3. Anti-DDoS: 2/min, 10/hour, 30/day per IP
4. Fixed import mismatch: routes.py ↔ rate_limiter.py

## Tests Passed
- [x] Health check (http://localhost:8002/api/health)
- [x] Stats endpoint (13009 emails, 14422 nodes)
- [ ] Query processing (not tested yet)
- [ ] Rate limiter under load

## Current Issues
- None (service running)

## Next Iteration Goals
1. Test query with Epstein corpus
2. Verify rate limiter works (spam 3x queries fast)
3. Check Haiku cost (should be ~$0.01/query)
4. Optimize if needed (reduce tokens without losing quality)

## Cost Tracking (30€/mois = $33)
- Haiku calls today: 67
- Cost today: $0.128
- Budget remaining: ~$32.87
- Queries/day limit: 200

## Quick Commands
```bash
# Health
curl -s http://localhost:8002/api/health | python3 -m json.tool

# Test query
curl -N "http://localhost:8002/api/ask?q=who+is+epstein" | head -30

# Check logs if error
journalctl -u l-api -n 30 --no-pager | grep -E "Error|Traceback|ImportError"

# DB stats
sqlite3 db/sources.db "SELECT COUNT(*) FROM emails;"
sqlite3 db/audit.db "SELECT COUNT(*) FROM query_log;"
```

## Architecture Notes
- app/pipeline.py: Detective prompt at line 237-281
- app/rate_limiter.py: acquire_slot() + release_slot()
- app/routes.py: Uses rate limiter before query processing
- DB audit.db: query_log table for rate tracking
