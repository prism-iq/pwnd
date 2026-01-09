# LLM Knowledge Leakage Fixes - Applied 2026-01-08

## Summary

Fixed critical issue where LLM was mixing corpus data with external world knowledge (NYT, BBC, Netflix, Wikipedia references).

## Changes Applied

### 1. System Prompt Updates

#### Haiku Analysis Prompt (templates/backend.sh lines 751-772)
```
You are a document analysis engine. You have NO knowledge of the world.

STRICT RULES:
- ONLY use information from the Data provided below
- If Data doesn't contain the answer, say so in findings
- NEVER reference external sources (NYT, BBC, Netflix, Wikipedia, documentaries, news articles, etc.)
- NEVER use general knowledge or say "it's well known" or "historically"
- You are analyzing a private corpus, not the internet

Your job: Extract facts ONLY from the Data provided, nothing else.
```

#### Mistral Formatting Prompt (templates/backend.sh lines 800-830)
```
You are a document analysis assistant. Format this analysis as a natural response.

STRICT RULES:
- ONLY use information from the Analysis JSON below
- NEVER add external knowledge (NYT, BBC, Netflix, Wikipedia, documentaries, news)
- NEVER say "it's well known", "historically", "based on what I know"
- You are analyzing a PRIVATE corpus, not the internet
- If analysis has no findings, say "No relevant data found in corpus"

DO NOT include:
- "User asked: X" prefix
- "Confidence level:" lines
- External references like "(NYT, 2019)" or "BBC News"
- [References] sections
```

#### Fallback Message Improvement
**Before:** "No relevant sources found."
**After:** "I couldn't find relevant documents for this query. Try specific names, dates, or keywords from the corpus."

### 2. Database Cleanup

**File:** graph.db
**Backup:** /opt/rag/db/graph.db.bak

#### Cleanup Statistics
- **Before:** 14,437 nodes
- **After:** 14,422 nodes
- **Removed:** 15 polluted nodes

#### Removed Entities
- NYTimes email addresses (nytimes@email.newyorktimes.com, etc.)
- NYT Now references
- Netflix references (Netflix Gift Card, Netflix Feedback, etc.)

#### Cleanup Steps
1. ✅ Deleted nodes with NYT/BBC/Netflix/Wikipedia references
2. ✅ Deleted orphaned edges (edges pointing to deleted nodes)
3. ✅ Deleted orphaned properties
4. ✅ Vacuumed database to reclaim space

### 3. Git Configuration

**Updated:** .gitignore

Added exclusions:
```gitignore
# Generated files (from templates/)
app/
static/
```

This ensures generated files from templates/ are not committed to git.

### 4. Git Commit

**Commit:** 3a0a3ef
**Message:** "Fix LLM knowledge leakage: Strict corpus-only prompts + DB cleanup"

**Files changed:**
- templates/backend.sh (system prompts updated)
- .gitignore (added app/, static/ exclusions)
- app/pipeline.py (regenerated from template)
- FINAL_SUMMARY.txt (added to repo)

## Testing Requirements

### Required Test Queries

1. **Test: General knowledge query**
   - Query: "Who is Jeffrey Epstein"
   - Expected: Corpus data only, NO NYT/BBC/Netflix references
   - Expected: Sources from email corpus only

2. **Test: No data query**
   - Query: "What is the capital of France"
   - Expected: "I couldn't find relevant documents for this query. Try specific names, dates, or keywords from the corpus."

3. **Test: French language**
   - Query: "Qui parle de transactions"
   - Expected: French response
   - Expected: Corpus data only

### Verification Checklist
- [ ] No external source mentions (NYT, BBC, Netflix, Wikipedia)
- [ ] No general knowledge phrases ("it's well known", "historically")
- [ ] No "User asked: X" prefix in responses
- [ ] Sources listed as "Sources: [7837] [7896]" format only
- [ ] Responses in user's language (French for French queries)

## Deployment Status

### Services
- ✅ l-api.service: Restarted successfully
- ✅ l-llm.service: Running
- ✅ caddy.service: Running

### Files Generated
- ✅ app/pipeline.py: Regenerated with new prompts
- ✅ Backend files: All regenerated from templates/

### Database Status
- ✅ graph.db: Cleaned (15 nodes removed)
- ✅ sources.db: Unchanged (13,009 emails)
- ✅ Backups: graph.db.bak, l.db.bak

## GitHub Repository Setup

### Prerequisites
- [x] Git initialized
- [x] GitHub CLI installed (gh v2.83.2)
- [ ] GitHub authentication required

### Setup Commands

```bash
# 1. Authenticate with GitHub (interactive)
gh auth login
# Choose: GitHub.com → HTTPS → Yes (git credential) → Login with browser

# 2. Create repository
gh repo create l-investigation-framework \
  --public \
  --description "OSINT RAG chatbot for document corpus analysis - Privacy-first, corpus-only LLM investigation framework" \
  --source=. \
  --remote=origin

# 3. Push to GitHub
git push -u origin main

# 4. Verify
gh repo view --web
```

### Alternative (Manual Setup)

If gh CLI doesn't work:

```bash
# 1. Create repo manually on GitHub.com:
#    Name: l-investigation-framework
#    Description: OSINT RAG chatbot for document corpus analysis
#    Public: Yes

# 2. Add remote
git remote add origin https://github.com/YOUR_USERNAME/l-investigation-framework.git

# 3. Push
git push -u origin main
```

## Next Steps

1. **Immediate:**
   - Authenticate gh CLI: `gh auth login`
   - Create GitHub repo and push
   - Test the 3 required queries

2. **Short-term (This Week):**
   - Implement rate limiting (Caddy + SlowAPI)
   - Add HSTS header to Caddyfile
   - Update minor dependencies (anyio, urllib3)

3. **Medium-term (Next Month):**
   - Run entity extraction ($1.63 cost)
   - Apply CPU tuning for faster queries
   - Setup automated backups

## Files Modified

```
/opt/rag/
├── .gitignore                (updated: added app/, static/)
├── templates/backend.sh      (updated: system prompts)
├── app/pipeline.py           (regenerated from template)
├── db/graph.db              (cleaned: 15 nodes removed)
├── db/graph.db.bak          (backup created)
├── FIXES_APPLIED.md         (this file)
└── FINAL_SUMMARY.txt        (added to repo)
```

## Verification

### Database Counts
```bash
# Sources (unchanged)
sqlite3 /opt/rag/db/sources.db "SELECT COUNT(*) FROM emails"
# Result: 13009

# Graph nodes (cleaned)
sqlite3 /opt/rag/db/graph.db "SELECT COUNT(*) FROM nodes"
# Result: 14422 (was 14437, removed 15)

# Verify no pollution
sqlite3 /opt/rag/db/graph.db "SELECT COUNT(*) FROM nodes WHERE name LIKE '%NYT%' OR name LIKE '%BBC%' OR name LIKE '%Netflix%'"
# Result: 0
```

### Git Status
```bash
git log --oneline -5
# 3a0a3ef Fix LLM knowledge leakage: Strict corpus-only prompts + DB cleanup
# 7cc714c Finalize v1.0: Documentation, frontend polish, security audit
# 82a3e2a Major update: Production-ready framework with diagnostic tools
# 3c9cf1e Add guardrails: meta protection + full freedom to accuse
# 05349f7 Add doctrine: epistemological core beliefs for LLM
```

## Contact

**Author:** Flow
**Email:** contact@flowai.com
**License:** MIT
**Public URL:** https://pwnd.icu

---

**Status:** ✅ FIXES APPLIED - READY FOR GITHUB PUSH
**Date:** 2026-01-08
**Commit:** 3a0a3ef
