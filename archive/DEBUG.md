# DEBUG - L Investigation Framework

**Last Updated:** 2026-01-08 04:28
**Status:** PRODUCTION READY ✅

---

## CURRENT STATE

### Services
```bash
systemctl status l-llm l-api caddy
```
- l-llm: ✅ ACTIVE (Phi-3-Mini, 4GB RAM, port 8001)
- l-api: ✅ ACTIVE (FastAPI, port 8002)
- caddy: ✅ ACTIVE (ports 80/443)

### Database Stats
- **Emails:** 13,009 (sources.db - 993MB)
- **Nodes:** 14,422 (graph.db - 3.6MB)
- **Edges:** 3,021
- **Sessions:** Active (sessions.db - 49KB)

### URLs
- **Local:** http://localhost
- **Public:** https://pwnd.icu
- **API:** http://localhost:8002
- **Health:** http://localhost:8002/api/health

---

## QUICK DIAGNOSTICS

### Check Everything
```bash
# Services
systemctl status l-llm l-api caddy --no-pager | grep Active

# API health
curl http://localhost:8002/api/health

# Stats
curl http://localhost:8002/api/stats

# Frontend
curl -I http://localhost/

# Logs (last 20 lines)
journalctl -u l-llm -n 20 --no-pager
journalctl -u l-api -n 20 --no-pager
journalctl -u caddy -n 20 --no-pager
```

### Quick Restart
```bash
systemctl restart l-llm l-api caddy
sleep 5
curl http://localhost:8002/api/health
```

---

## COMMON ISSUES & FIXES

### 1. Frontend not loading
**Symptom:** `curl http://localhost/` returns nothing
**Fix:**
```bash
cat > /etc/caddy/Caddyfile << 'EOF'
:80 {
    root * /opt/rag/static
    file_server
    handle /api/* {
        reverse_proxy localhost:8002
    }
}
EOF
systemctl restart caddy
```

### 2. API not responding
**Symptom:** `curl http://localhost:8002/api/health` fails
**Fix:**
```bash
# Check if port busy
lsof -i :8002

# Restart service
systemctl restart l-api
sleep 3
systemctl status l-api
```

### 3. LLM timeout
**Symptom:** Queries take forever, no response
**Fix:**
```bash
# Check Phi-3 status
systemctl status l-llm

# Check memory
free -h

# Restart LLM
systemctl restart l-llm
# Wait 30s for model to load
sleep 30
```

### 4. Database locked
**Symptom:** "database is locked" errors
**Fix:**
```bash
# Check processes
lsof /opt/rag/db/*.db

# Kill if needed
killall -9 python uvicorn

# Restart services
systemctl restart l-llm l-api
```

### 5. Response shows sources but no text
**Symptom:** Frontend shows "Sources: [123] [456]" but no analysis
**Check:**
```bash
# Test raw API
curl -s "http://localhost:8002/api/ask?q=test" | grep chunk

# Should see: {"type": "chunk", "text": "..."}
```
**Fix:** Check app/pipeline.py line 404 - ensure chunk is emitted

### 6. Rate limit hit
**Symptom:** "Rate limit reached" or 429 errors
**Fix:**
```bash
# Check rate limits
sqlite3 /opt/rag/db/audit.db "SELECT COUNT(*) FROM query_log WHERE date(created_at) = date('now')"

# Reset if needed (CAREFUL!)
sqlite3 /opt/rag/db/audit.db "DELETE FROM query_log WHERE date(created_at) = date('now')"

# Or increase limits in app/rate_limiter.py
```

### 7. Out of budget
**Symptom:** "Cost limit reached" errors
**Fix:**
```bash
# Check Haiku usage
sqlite3 /opt/rag/db/audit.db "SELECT COUNT(*), SUM(cost_usd) FROM haiku_calls WHERE date(created_at) = date('now')"

# Increase limit in app/config.py:
# HAIKU_DAILY_LIMIT = 200 → 500
# HAIKU_COST_LIMIT_USD = 1.0 → 5.0
```

---

## FILE LOCATIONS

### Code
- `/opt/rag/app/` - FastAPI application
- `/opt/rag/llm/` - Phi-3 backend
- `/opt/rag/static/` - Frontend (HTML/JS/CSS)
- `/opt/rag/scripts/` - Utility scripts

### Config
- `/opt/rag/.env` - Environment variables
- `/opt/rag/Caddyfile` - Web server config
- `/etc/caddy/Caddyfile` - System Caddy config
- `/etc/systemd/system/l-*.service` - Service files

### Data
- `/opt/rag/db/sources.db` - Email corpus (13,009 emails)
- `/opt/rag/db/graph.db` - Entity graph (14,422 nodes)
- `/opt/rag/db/audit.db` - Query logs, costs
- `/opt/rag/db/sessions.db` - User conversations
- `/opt/rag/llm/Phi-3-mini-4k-instruct-q4.gguf` - LLM model (2.3GB)

### Logs
- `journalctl -u l-llm` - LLM logs
- `journalctl -u l-api` - API logs
- `journalctl -u caddy` - Web server logs
- `/var/log/l-investigation/` - App logs (if configured)

### Exports
- `/opt/rag/exports/` - Evidence packages (.tar.gz)

---

## TESTING COMMANDS

### Health Check
```bash
# All services
curl http://localhost:8002/api/health

# Stats
curl http://localhost:8002/api/stats

# Query test
curl -N "http://localhost:8002/api/ask?q=test"
```

### Database Queries
```bash
# Count emails
sqlite3 /opt/rag/db/sources.db "SELECT COUNT(*) FROM emails"

# Count nodes
sqlite3 /opt/rag/db/graph.db "SELECT COUNT(*) FROM nodes"

# Recent queries
sqlite3 /opt/rag/db/audit.db "SELECT * FROM query_log ORDER BY created_at DESC LIMIT 10"

# Haiku costs today
sqlite3 /opt/rag/db/audit.db "SELECT COUNT(*), SUM(cost_usd) FROM haiku_calls WHERE date(created_at) = date('now')"
```

### Performance
```bash
# Memory usage
free -h
ps aux | grep -E "python|uvicorn|caddy" | awk '{print $2, $4, $11}'

# CPU usage
top -bn1 | grep -E "python|uvicorn|caddy"

# Disk usage
df -h /opt/rag
du -sh /opt/rag/db/*.db
```

---

## DEVELOPMENT

### Run in Dev Mode
```bash
cd /opt/rag
source venv/bin/activate

# LLM backend (terminal 1)
python llm/backend.py

# API (terminal 2)
uvicorn app.main:app --reload --host 127.0.0.1 --port 8002

# Frontend served by Caddy (already running)
```

### Test Without Frontend
```bash
# SSE stream
curl -N "http://localhost:8002/api/ask?q=who+is+epstein"

# Single source
curl "http://localhost:8002/api/source/123"

# Stats
curl "http://localhost:8002/api/stats"
```

### Database Inspection
```bash
# SQLite CLI
sqlite3 /opt/rag/db/sources.db

# List tables
.tables

# Schema
.schema emails

# Sample data
SELECT * FROM emails LIMIT 5;

# Exit
.quit
```

---

## FEATURES STATUS

### Core Features ✅
- [x] Email corpus search (13,009 emails)
- [x] Entity graph (14,422 nodes, 3,021 edges)
- [x] Dual-LLM pipeline (Phi-3 + Haiku)
- [x] Real-time SSE streaming
- [x] Auto-investigate mode (max 20 queries)
- [x] Rate limiting (Anti-DDoS)
- [x] Budget protection ($33/month)
- [x] The Code integration (victim protection)

### Advanced Features ✅ (Added 2026-01-08)
- [x] Keyboard shortcuts (13 shortcuts)
- [x] Export MD/JSON (Ctrl+E)
- [x] Copy to clipboard
- [x] Suggested questions (10 pre-defined)
- [x] Search history (50 queries)
- [x] Bookmarks
- [x] Toast notifications
- [x] Share investigation
- [x] Auto-save drafts
- [x] Quick actions menu

### Evidence Export ✅
- [x] SHA256 verification
- [x] Chain of custody
- [x] Social media templates
- [x] Tamper-proof packaging
- [x] Legal-ready format

### Pending Features
- [ ] MBOX import (Gmail exports)
- [ ] PST support (Outlook)
- [ ] Elasticsearch option (100k+ emails)
- [ ] Visual timeline (D3.js)
- [ ] ML fraud detection
- [ ] GPG signatures
- [ ] Investigation replay
- [ ] Breach API (HaveIBeenPwned)

---

## GIT STATUS

```bash
# Current branch
git branch
# Output: * main

# Recent commits
git log --oneline -5

# Uncommitted changes
git status --short

# Last commit
git show --stat HEAD
```

**Latest commit:** fe578b9 - "Research: Learnings from top OSINT tools"

---

## SECURITY CHECKLIST

- [x] Rate limiting active
- [x] SHA256 verification
- [x] Chain of custody
- [x] Victim anonymization (The Code)
- [x] SQL injection prevention
- [x] XSS protection
- [x] Budget caps
- [x] HTTPS (Caddy auto-TLS)
- [x] Input validation
- [x] CORS protection

---

## COST TRACKING

### Current Budget
- **Monthly:** $33 USD (30€)
- **Daily limit:** 200 Haiku calls
- **Cost/call:** ~$0.01
- **Today:** Check with `curl http://localhost:8002/api/stats`

### Query Costs
```bash
# Today's Haiku usage
sqlite3 /opt/rag/db/audit.db "
SELECT
    COUNT(*) as calls,
    SUM(cost_usd) as total_cost,
    AVG(cost_usd) as avg_cost
FROM haiku_calls
WHERE date(created_at) = date('now')
"
```

---

## EMERGENCY PROCEDURES

### Total System Reset
```bash
# Stop everything
systemctl stop l-llm l-api caddy

# Clear audit logs (reset rate limits)
rm /opt/rag/db/audit.db
sqlite3 /opt/rag/db/audit.db < /opt/rag/app/db.py  # Recreate tables

# Restart
systemctl start l-llm
sleep 30  # Wait for model load
systemctl start l-api caddy

# Test
curl http://localhost:8002/api/health
```

### Database Backup
```bash
# Backup all databases
tar -czf backup_$(date +%Y%m%d).tar.gz /opt/rag/db/*.db

# Restore
tar -xzf backup_YYYYMMDD.tar.gz -C /
```

### Rollback Git
```bash
# See commits
git log --oneline -10

# Rollback to specific commit
git reset --hard COMMIT_HASH

# Restart services
systemctl restart l-llm l-api caddy
```

---

## MONITORING

### Real-time Logs
```bash
# Follow all logs
journalctl -u l-llm -u l-api -u caddy -f

# Just API
journalctl -u l-api -f

# Just LLM
journalctl -u l-llm -f
```

### System Resources
```bash
# Watch memory
watch -n 2 free -h

# Watch processes
watch -n 2 'ps aux | grep -E "python|uvicorn|caddy"'

# Network connections
watch -n 2 'netstat -tunlp | grep -E "8001|8002|80|443"'
```

---

## PRODUCTION DEPLOYMENT

### Pre-flight Checklist
- [ ] Services running
- [ ] Health check passes
- [ ] Stats endpoint works
- [ ] Test query succeeds
- [ ] Frontend loads
- [ ] Database accessible
- [ ] Model loaded
- [ ] Caddy serving HTTPS
- [ ] Rate limiter active
- [ ] Budget tracking works

### Post-deploy Verification
```bash
# Run this after any change
./scripts/verify-deployment.sh  # TODO: create this script

# Or manually:
curl http://localhost:8002/api/health
curl http://localhost:8002/api/stats
curl -N "http://localhost:8002/api/ask?q=test" | head -20
curl -I http://localhost/
```

---

## NEXT ITERATION TODO

### Priority 1
- [ ] Fix .gitignore (static/ ignored, can't commit frontend changes)
- [ ] Create verify-deployment.sh script
- [ ] Add MBOX import script
- [ ] Investigation session logging

### Priority 2
- [ ] Visual timeline (D3.js)
- [ ] Breach API integration (HaveIBeenPwned)
- [ ] GPG signing for evidence packages

### Priority 3
- [ ] Elasticsearch option for large corpora
- [ ] PST import for Outlook
- [ ] ML fraud detection model

---

## LEARNING NOTES

### What Works Well
- Dual-LLM approach (Phi-3 fast, Haiku smart)
- Rate limiting prevents abuse
- SHA256 verification for integrity
- The Code as moral foundation
- Keyboard shortcuts = fast UX
- Evidence export = legal-ready

### What Needs Improvement
- Frontend changes can't be committed (.gitignore issue)
- No MBOX/PST import yet
- No visual timeline
- No ML classification
- Manual evidence review (need automation)

### Recent Learnings (from OSINT research)
- h8mail: breach correlation is powerful
- comms-analyzer-toolbox: Elasticsearch scales better
- Paliscope: digital signatures > SHA256 alone
- SeFACED: ML can auto-detect fraud patterns
- Our advantage: The Code + social media integration

---

## REMEMBER EVERY TIME

1. **Read this file first** before making changes
2. **Update this file** after fixes/features
3. **Check git status** before commits
4. **Test health endpoint** after restarts
5. **Follow The Code** in all features
6. **Document everything** for next iteration
7. **Learn from errors** - add to "Common Issues"

---

*"Evil must be fought wherever it is found."*
**— The Code**

**Debug updated:** 2026-01-08 04:28

## RECENT FIXES

### 2026-01-08 04:35 - Response text not showing
**Symptom:** Frontend shows "Sources: [123]" but no analysis text
**Cause:** updateCurrentMessage() not properly rendering content
**Fix:** 
- Added early return after message creation
- Clear innerHTML before update
- Proper markdown rendering
**File:** static/app.js line 403-435
**Test:** Refresh page, query "test" - should show full response
