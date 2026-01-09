# Troubleshooting Guide - L Investigation Framework

Quick reference for common issues and their fixes.

---

## Service Issues

### ❌ "Connection refused" when accessing https://pwnd.icu

**Symptoms:**
```bash
curl https://pwnd.icu
curl: (7) Failed to connect to pwnd.icu port 443: Connection refused
```

**Diagnosis:**
```bash
systemctl status caddy
```

**Fix:**
```bash
sudo systemctl restart caddy
sudo journalctl -u caddy -n 50  # Check for errors
```

**Common causes:**
- Caddy service stopped
- Caddyfile syntax error
- Port 80/443 already in use

---

### ❌ "502 Bad Gateway" from Caddy

**Symptoms:**
Browser shows "502 Bad Gateway" error

**Diagnosis:**
```bash
systemctl status l-api
curl http://127.0.0.1:8002/api/health
```

**Fix:**
```bash
sudo systemctl restart l-api
sudo journalctl -u l-api -n 100
```

**Common causes:**
- FastAPI crashed
- Binding to wrong interface (0.0.0.0 instead of 127.0.0.1)
- Python venv not activated

---

### ❌ Phi-3-Mini LLM not responding

**Symptoms:**
Query hangs at "Parsing query..." status

**Diagnosis:**
```bash
systemctl status l-llm
curl http://127.0.0.1:8001/v1/models
```

**Fix:**
```bash
sudo systemctl restart l-llm
# Wait 10-30s for model to load
curl http://127.0.0.1:8001/v1/models  # Should return model info
```

**Common causes:**
- Model file missing/corrupted
- Out of memory (needs 4GB+ RAM for Phi-3-Mini)
- Port 8001 already in use

---

## Query Issues

### ❌ Query returns "No relevant sources found"

**Symptoms:**
Query like "Who is Jeffrey Epstein?" returns no results

**Diagnosis:**
```bash
sqlite3 /opt/rag/db/sources.db "SELECT COUNT(*) FROM emails WHERE body_text LIKE '%epstein%' COLLATE NOCASE;"
```

**Fix 1:** Spam filtering too aggressive
```python
# app/pipeline.py - Remove or relax LENGTH filter
# Before: AND LENGTH(body_text) > 500
# After: AND LENGTH(body_text) > 100
```

**Fix 2:** Entity not in graph
```bash
# Run entity extraction
./scripts/extract_entities.sh --batch-size 100 --max-docs 1000
```

**Common causes:**
- FTS search too strict
- Entity name variations ("Epstein" vs "Jeffrey Epstein")
- Spam emails filtered out
- Entity not yet extracted into graph

---

### ❌ Query returns only spam/promotional emails

**Symptoms:**
Results are Amazon receipts, XM Radio offers, etc.

**Fix:** Add spam filters to SQL
```python
# app/pipeline.py line ~70-90
email_query = """
    SELECT ... FROM emails_fts
    WHERE emails_fts MATCH ?
      AND LENGTH(body_text) > 500
      AND subject NOT LIKE '%Amazon%'
      AND subject NOT LIKE '%review%'
      AND subject NOT LIKE '%offer%'
      AND subject NOT LIKE '%Special%'
    ORDER BY rank
    LIMIT ?
"""
```

---

### ❌ Query times out after 2 minutes

**Symptoms:**
Browser shows timeout error, query never completes

**Diagnosis:**
```bash
# Check if Phi-3 is responding
time curl -X POST http://127.0.0.1:8001/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Test","max_tokens":10}'
```

**Fix 1:** Increase timeout
```python
# app/routes.py
@router.get("/api/ask")
async def ask(...):
    # Add timeout parameter
    return StreamingResponse(..., headers={"X-Accel-Buffering": "no"})
```

**Fix 2:** Optimize Phi-3 settings
```bash
./scripts/apply_llm_config.sh config/llm_tuning.yaml
```

---

## Database Issues

### ❌ "database is locked" error

**Symptoms:**
```
sqlite3.OperationalError: database is locked
```

**Diagnosis:**
```bash
lsof | grep sources.db  # See which processes have lock
```

**Fix:**
```bash
# Close any open sqlite3 sessions
pkill sqlite3

# Or restart API
sudo systemctl restart l-api
```

**Prevention:**
```python
# app/db.py - Use WAL mode
conn = sqlite3.connect("sources.db")
conn.execute("PRAGMA journal_mode=WAL")
```

---

### ❌ Database file corrupted

**Symptoms:**
```
sqlite3.DatabaseError: database disk image is malformed
```

**Diagnosis:**
```bash
sqlite3 /opt/rag/db/sources.db "PRAGMA integrity_check;"
```

**Fix:**
```bash
# Dump and restore
sqlite3 /opt/rag/db/sources.db ".dump" > sources.sql
mv /opt/rag/db/sources.db /opt/rag/db/sources.db.bak
sqlite3 /opt/rag/db/sources.db < sources.sql
```

---

## Frontend Issues

### ❌ EventSource connection fails

**Symptoms:**
Browser console: `EventSource failed: Connection closed`

**Diagnosis:**
```javascript
// Browser DevTools → Network tab
// Check /api/ask request status
```

**Fix:**
```javascript
// static/app.js
eventSource.onerror = (error) => {
    console.error('EventSource error:', error);
    enableInput();  // Re-enable input on error
};
```

---

### ❌ Input stuck disabled after query

**Symptoms:**
Send button remains disabled, can't submit new queries

**Fix:**
Already fixed in app.js:305, 359, 399
- Ensure `enableInput()` called in all error handlers

**Verify:**
```javascript
// Browser console
document.getElementById('sendBtn').disabled = false;
```

---

### ❌ Multiple EventSource connections stacking

**Symptoms:**
Duplicate messages appearing, memory leak

**Fix:**
Already fixed in app.js:310-314
```javascript
// Close previous EventSource before creating new one
if (eventSource) {
    eventSource.close();
    eventSource = null;
}
```

---

## Security Issues

### ❌ API exposed to internet (port 8002)

**Symptoms:**
```bash
curl http://88.99.151.62:8002/api/health  # Returns 200
```

**Fix:**
```bash
# Edit systemd service
sudo nano /etc/systemd/system/l-api.service

# Change:
ExecStart=uvicorn app.main:app --host 0.0.0.0 --port 8002
# To:
ExecStart=uvicorn app.main:app --host 127.0.0.1 --port 8002

sudo systemctl daemon-reload
sudo systemctl restart l-api
```

**Verify:**
```bash
curl http://88.99.151.62:8002/api/health  # Should timeout
curl http://localhost:8002/api/health      # Should work
```

---

### ❌ .env file world-readable

**Symptoms:**
```bash
ls -l /opt/rag/.env
-rw-r--r-- 1 root root 123 Jan 8 .env  # Bad: 644
```

**Fix:**
```bash
chmod 600 /opt/rag/.env
ls -l /opt/rag/.env
-rw------- 1 root root 123 Jan 8 .env  # Good: 600
```

---

### ❌ Database files world-readable

**Fix:**
```bash
chmod 600 /opt/rag/db/*.db
ls -l /opt/rag/db/*.db  # Should show -rw-------
```

---

## Performance Issues

### ❌ Query takes >60 seconds

**Diagnosis:**
```bash
# Enable timing in app.js
console.time('mistral');
const intent = await parse_intent(query);
console.timeEnd('mistral');  # Should be <3s
```

**Fix 1:** Apply CPU tuning
```bash
./scripts/apply_llm_config.sh config/llm_tuning.yaml
```

**Fix 2:** Migrate to PostgreSQL
```bash
# After setting POSTGRES_URL in .env
./scripts/migrate_to_postgres.sh
```

**Fix 3:** Add caching
```python
# app/llm_client.py
from functools import lru_cache

@lru_cache(maxsize=100)
def cached_mistral_call(prompt):
    return call_mistral(prompt)
```

---

### ❌ Out of memory errors

**Symptoms:**
```bash
journalctl -u l-llm | grep "OOM"
```

**Fix:**
```bash
# Reduce Phi-3 context window
# config/llm_tuning.yaml
n_ctx: 1024  # Down from 2048
```

**Or use even smaller quantization:**
```bash
# Download Q3 quantization (faster, less RAM)
# Note: Phi-3-Mini is already small (2.4GB), Q3 would be ~1.8GB
wget https://huggingface.co/microsoft/Phi-3-mini-4k-instruct-gguf/resolve/main/Phi-3-mini-4k-instruct-q3_k_m.gguf
mv Phi-3-mini-4k-instruct-q3_k_m.gguf /opt/rag/llm/
./scripts/apply_llm_config.sh  # Point to new model
```

---

## Installation Issues

### ❌ install.sh fails on OS detection

**Symptoms:**
```
Error: Unsupported OS
```

**Fix:**
```bash
# Manual install
# Arch:
sudo pacman -S python python-pip sqlite caddy

# Ubuntu/Debian:
sudo apt install python3 python3-pip python3-venv sqlite3 caddy
```

---

### ❌ Missing Python dependencies

**Symptoms:**
```
ModuleNotFoundError: No module named 'fastapi'
```

**Fix:**
```bash
cd /opt/rag
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

### ❌ Caddy not starting

**Symptoms:**
```bash
systemctl status caddy
# Failed to bind to port 80: permission denied
```

**Fix:**
```bash
# Allow Caddy to bind to privileged ports
sudo setcap cap_net_bind_service=+ep $(which caddy)

# Or run as root (less secure)
sudo systemctl edit caddy
# Add:
[Service]
User=root
```

---

## Git Issues

### ❌ Accidentally committed *.db files

**Fix:**
```bash
# Remove from git but keep on disk
git rm --cached db/*.db
echo "db/*.db" >> .gitignore
git add .gitignore
git commit -m "Fix: Remove database files from git"
```

---

### ❌ Accidentally committed .env file

**Fix:**
```bash
# Remove from git and history
git rm --cached .env
echo ".env" >> .gitignore
git add .gitignore
git commit -m "Fix: Remove .env from git"

# Remove from history (if already pushed)
git filter-branch --force --index-filter \
  'git rm --cached --ignore-unmatch .env' \
  --prune-empty --tag-name-filter cat -- --all
```

---

## Script Issues

### ❌ extract_entities.sh fails with API error

**Symptoms:**
```
APIError: invalid API key
```

**Fix:**
```bash
# Check .env
grep HAIKU_API_KEY /opt/rag/.env

# Should be: HAIKU_API_KEY=sk-ant-...
# Not: HAIKU_API_KEY="sk-ant-..."  # No quotes

# Re-export
export HAIKU_API_KEY=sk-ant-your-key-here
```

---

### ❌ migrate_to_postgres.sh fails with connection error

**Symptoms:**
```
psql: could not connect to server
```

**Fix:**
```bash
# Test PostgreSQL connection
psql "postgresql://user:pass@host:5432/dbname" -c "SELECT version();"

# Check POSTGRES_URL format
# Correct: postgresql://user:pass@host:5432/dbname
# Wrong: postgres://...  (missing 'ql')
```

---

## Diagnostic Commands

### Check All Services
```bash
systemctl status l-api l-llm caddy
```

### Check Ports
```bash
ss -tlnp | grep -E "800[12]|80|443"
# Should see:
# 127.0.0.1:8001 (l-llm)
# 127.0.0.1:8002 (l-api)
# 0.0.0.0:80 (caddy)
# 0.0.0.0:443 (caddy)
```

### Check Disk Space
```bash
df -h /opt/rag
du -sh /opt/rag/db/*.db
```

### Check Memory
```bash
free -h
ps aux | grep -E "uvicorn|llama"
```

### Test Query Pipeline
```bash
# 1. Test Phi-3
curl -X POST http://127.0.0.1:8001/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Test","max_tokens":10}'

# 2. Test API health
curl http://127.0.0.1:8002/api/health

# 3. Test query
curl -N "http://127.0.0.1:8002/api/ask?q=test"

# 4. Test public URL
curl -s "https://pwnd.icu/api/health"
```

---

## Getting Help

### Log Locations
```bash
# API logs
journalctl -u l-api -n 100 -f

# LLM logs
journalctl -u l-llm -n 100 -f

# Caddy logs
journalctl -u caddy -n 100 -f

# System logs
dmesg | tail -100
```

### Debug Mode
```python
# app/main.py
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Create Issue Report
```bash
# Collect diagnostics
cat > /tmp/issue_report.txt <<EOF
# L Investigation Framework - Issue Report

## System Info
$(uname -a)
$(python3 --version)
$(sqlite3 --version)

## Services
$(systemctl status l-api l-llm caddy)

## Disk
$(df -h /opt/rag)

## Database Sizes
$(ls -lh /opt/rag/db/*.db)

## Recent Errors
$(journalctl -u l-api -n 50)
EOF

cat /tmp/issue_report.txt
```

---

**Quick Reference:**

| Symptom | Fix |
|---------|-----|
| 502 Bad Gateway | `systemctl restart l-api` |
| Query hangs | `systemctl restart l-llm` |
| No results | Run `extract_entities.sh` |
| Spam results | Add filters to SQL |
| API exposed | Change to 127.0.0.1 in systemd |
| Database locked | `pkill sqlite3` |
| Input stuck | Already fixed in app.js |

**Read next:** `/opt/rag/docs/SCHEMA.md` for database structure.
