# L Investigation Framework - Diagnostic Report
**Date:** 2026-01-07
**Public URL:** https://pwnd.icu
**Database:** /opt/rag/db/sources.db (948MB, 13,009 emails)

---

## PHASE 1: DIAGNOSTIC RESULTS

### 1.1 Database Statistics

**sources.db:**
- Total emails: 13,009
- Date range: 2007-09-20 to 2021-12-07
- Epstein mentions: 1,207 emails
- Maxwell mentions: 17 emails
- Trump mentions: 2,011 emails

**graph.db:**
- Total nodes: 14,437
  - Persons: 2,560
  - Dates: 1,950
  - Locations: 1,840
  - Amounts: 1,737
  - Objects: 1,453
  - Companies: 1,274
  - Documents: 598
  - Organizations: 591
  - Events: 532
- Total edges: 3,034

**Key Entities Found:**
```sql
Jeffrey Epstein (node_id: 9, 97, 712, 3485, 5363, 7487)
Donald Trump (node_id: 3427, 4320, 4535, 4861, 4946)
Ghislaine Maxwell (not yet extracted as node)
```

### 1.2 API Query Tests

**Query 1: "Who is Jeffrey Epstein?"**
- Response time: 56.9 seconds
- Intent parsed: "connections"
- Sources found: 10 (doc_ids: 6, 9, 10, 13, 14, 24, 29, 62, 63, 70)
- Haiku analysis: "No substantive data retrieved"
- **Issue:** Sources are spam/promotional emails TO Epstein (Amazon, XM Radio), not ABOUT him

**Sample returned sources:**
```
doc_id=6: "Review your recent purchases at Amazon.com" (To: Jeffrey Epstein)
doc_id=9: "Special Offer - iThink Business Bundle"
doc_id=13: "XM Radio Online - Important Registration Information"
doc_id=24: "Your login details" (Username: jeffrey)
```

**Query 2-5:** (Tests interrupted - need manual rerun)

### 1.3 Search Logic Analysis

**Current Pipeline (4-step LLM flow):**

1. **Mistral IN** - Intent parsing (2-3 sec, 100 tokens)
   - Parses query → JSON: `{"intent": "connections|search|timeline", "entities": [...], "filters": {...}}`
   - Location: `/opt/rag/app/pipeline.py:10-54`

2. **Python SQL** - Query execution
   - **"search" intent**: FTS on `emails_fts` + LIKE on `nodes`
   - **"connections" intent**: Find nodes → get edges → get linked emails
   - Location: `/opt/rag/app/pipeline.py:56-205`

3. **Haiku OUT** - Analysis (3-5 sec, 500 tokens)
   - Synthesizes results into narrative
   - Extracts suggested_queries for auto-investigation

4. **Mistral OUT** - Format to friendly tone

**Graph Connections Found:**
```sql
Jeffrey Epstein → jeeproject@yahoo.com (email_owner, has_email, owns_account)
Jeffrey Epstein → Little St. James (owns_property, has_address)
```

**NO direct Epstein ↔ Trump edges found** (they exist in emails but not extracted)

### 1.4 Critical Issues Identified

**A. Search Quality:**
- FTS returns emails TO entity, not ABOUT entity
- Spam/promotional emails dominate results (Amazon, XM Radio, login credentials)
- Biographical queries fail because entities aren't in body_text, only in recipient fields

**B. Entity Extraction:**
- Only 14,437 nodes extracted from 13,009 emails (1.1 entities per email avg)
- Key person "Ghislaine Maxwell" has NO node despite 17 email mentions
- Connections between Epstein-Trump exist in emails but not graphed

**C. Performance:**
- Query time: ~57 seconds (too slow)
- Bottleneck: Mistral 7B intent parsing + Haiku analysis on every query

**D. Missing Features:**
- No `/api/graph/overview` endpoint
- No embedding-based semantic search (only keyword FTS)
- No entity deduplication (Jeffrey Epstein appears as 6+ nodes)

---

## PHASE 2: POSTGRESQL MIGRATION (PREPARED - NOT EXECUTED)

### 2.1 Migration Rationale

**Current:** 4 separate SQLite databases (sources.db, graph.db, sessions.db, scores.db, audit.db)
**Proposed:** Single PostgreSQL instance with schemas

**Benefits:**
- Connection pooling for concurrent requests (Caddy → FastAPI)
- JOIN queries across databases (currently requires 2+ queries)
- Better FTS with ts_vector/ts_query (vs SQLite FTS5)
- JSONB for flexible entity properties
- Row-level security for multi-tenant deployment
- Backup/replication built-in

**Schema Design:**
```sql
-- sources schema
CREATE TABLE sources.emails (...);
CREATE INDEX idx_emails_fts ON sources.emails USING gin(to_tsvector('english', body_text || ' ' || subject));

-- graph schema
CREATE TABLE graph.nodes (...);
CREATE TABLE graph.edges (...);
CREATE INDEX idx_nodes_name_trgm ON graph.nodes USING gin(name gin_trgm_ops);

-- sessions schema
CREATE TABLE sessions.conversations (...);
CREATE TABLE sessions.messages (...);
```

### 2.2 Migration Script

**File:** `/opt/rag/scripts/migrate_to_postgres.sh`
- Exports SQLite → CSV
- Creates PostgreSQL schemas
- Imports CSV with COPY
- Creates indexes and constraints
- Validates row counts
- **Manual trigger only** (requires `.env` with POSTGRES_URL)

---

## PHASE 3: ENTITY EXTRACTION (PREPARED - NOT EXECUTED)

### 3.1 Haiku Entity Extraction

**Problem:** Current extraction is incomplete (1.1 entities/email)

**Solution:** Bulk NER pipeline using Claude Haiku API

**File:** `/opt/rag/scripts/extract_entities.sh`

**Features:**
- Batch processing (100 emails per API call)
- Rate limiting (5 req/sec, Tier 1 limit)
- Structured JSON output:
  ```json
  {
    "entities": [
      {"name": "Ghislaine Maxwell", "type": "person", "confidence": 0.95},
      {"name": "Trump SoHo", "type": "location", "confidence": 0.89}
    ],
    "relationships": [
      {"from": "Ghislaine Maxwell", "to": "Jeffrey Epstein", "type": "associated_with"}
    ]
  }
  ```
- Deduplication via fuzzy matching (Levenshtein distance)
- Source tracking (doc_id → node mapping)

**Usage:**
```bash
# Extract from unprocessed emails
./scripts/extract_entities.sh --batch-size 100 --max-docs 1000

# Re-extract all (for improved prompts)
./scripts/extract_entities.sh --force --batch-size 50
```

**Cost Estimate:**
- 13,009 emails / 100 per batch = 131 API calls
- @ $0.25 per 1M input tokens ≈ $3-5 total

### 3.2 Entity Deduplication

**Problem:** "Jeffrey Epstein" exists as 6+ nodes (9, 97, 712, 3485, 5363, 7487)

**Solution:** Post-processing script

**File:** `/opt/rag/scripts/deduplicate_entities.sh`

**Algorithm:**
1. Group nodes by type
2. Calculate Levenshtein distance for all pairs
3. Merge nodes with distance < 3 and same type
4. Update edge references to canonical node_id
5. Create alias entries in `aliases` table

---

## PHASE 4: CPU OPTIMIZATION (PREPARED - NOT EXECUTED)

### 4.1 Current Mistral 7B Settings

**Backend:** llama.cpp server on localhost:8001
**Model:** mistral-7b-instruct-v0.2.Q4_K_M.gguf (4.4GB)
**Current Config:**
```yaml
# From systemd service or backend.py
model_path: /opt/rag/models/mistral-7b-instruct-v0.2.Q4_K_M.gguf
n_ctx: 2048        # Context window
n_threads: 4       # CPU threads (auto-detect)
n_batch: 512       # Batch size
temperature: 0.0   # Deterministic for intent parsing
max_tokens: 100    # Intent parsing only
```

### 4.2 Tuning Recommendations

**File:** `/opt/rag/config/llm_tuning.yaml` (not applied yet)

```yaml
# Optimized for Intel/AMD 8-core CPU
mistral:
  n_threads: 6              # Leave 2 cores for FastAPI/Caddy
  n_batch: 256              # Reduce for lower latency
  n_ctx: 1024               # Intent parsing doesn't need 2048
  use_mlock: true           # Lock model in RAM (prevent swap)
  use_mmap: true            # Memory-map model file

# Alternative: Faster model for intent parsing
mistral_alternative:
  model: "mistral-7b-instruct-v0.2.Q3_K_S.gguf"  # 3-bit quantization
  # 30% faster, slight quality loss acceptable for intent parsing

# Haiku settings (API)
haiku:
  max_tokens: 500
  temperature: 0.3
  cache_ttl: 300            # Cache identical queries for 5 min
```

**Apply with:**
```bash
# Test new config without restarting services
./scripts/test_llm_config.sh config/llm_tuning.yaml

# Apply permanently
./scripts/apply_llm_config.sh config/llm_tuning.yaml
sudo systemctl restart l-llm
```

### 4.3 Performance Targets

**Current:** 57 seconds per query
**Target:** <10 seconds per query

**Breakdown:**
- Mistral intent parsing: 2-3s → 1s (tuning)
- SQL execution: 1-2s → 0.5s (PostgreSQL + indexes)
- Haiku analysis: 3-5s → 3s (caching)
- Formatting: <1s

---

## PHASE 5: PACKAGING & GIT

### 5.1 Current .gitignore Issues

**File:** `/opt/rag/.gitignore`

**Currently excluded:**
```
venv/, __pycache__/, *.pyc
db/*.db                    # ✗ Too broad - excludes schemas
models/*.gguf              # ✓ Correct
.env                       # ✓ Correct
```

**Should exclude:**
```
# Data (not schema)
db/*.db
db/*.db-journal
db/*.db-wal
!db/schema*.sql            # INCLUDE schemas

# Models
models/*.gguf
models/*.bin
!models/README.md          # INCLUDE download instructions

# Secrets
.env
*.key
*.pem

# Build
venv/
__pycache__/
*.pyc
```

### 5.2 Git Repository Initialization

**Status:** Not a git repo currently

**Files to commit:**
```
/opt/rag/
├── app/                   # FastAPI application
├── static/                # Frontend (HTML/CSS/JS)
├── scripts/               # Installation, rebuild, migration
├── modules/               # Custom Python modules
├── templates/             # Jinja2 templates (if any)
├── db/
│   ├── schema_sessions.sql
│   ├── schema_graph.sql   # TO BE CREATED
│   └── schema_sources.sql # TO BE CREATED
├── models/
│   └── README.md          # Download instructions
├── install.sh             # OS detection + dependency install
├── requirements.txt       # Python packages
├── README.md              # Comprehensive documentation
├── QUICKSTART.md          # 5-minute setup guide
├── DIAGNOSTIC_REPORT.md   # This file
├── LICENSE                # MIT License
├── .gitignore
└── .env.example           # Configuration template
```

**Commands:**
```bash
# Create proper .gitignore
cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
venv/

# Databases (data, not schemas)
db/*.db
db/*.db-journal
!db/schema*.sql

# Models (too large)
models/*.gguf
models/*.bin
!models/README.md

# Secrets
.env
*.key
*.pem

# Logs
*.log
logs/
EOF

# Initialize git
git init
git add .
git commit -m "Initial commit: L Investigation Framework

- FastAPI backend with SSE streaming
- Graph database (14k nodes, 3k edges)
- Email corpus (13k emails, 948MB)
- Auto-investigation loop
- Mistral 7B + Claude Haiku LLM pipeline"

# Create GitHub repo (manual)
# Then: git remote add origin https://github.com/USERNAME/l-investigation.git
# Then: git push -u origin main
```

---

## RECOMMENDED NEXT ACTIONS

### Immediate (Do Now):

1. **Run full entity extraction** to populate graph.db properly
   ```bash
   ./scripts/extract_entities.sh --batch-size 100 --max-docs 13009
   ```

2. **Deduplicate Epstein nodes** (6+ duplicates)
   ```bash
   ./scripts/deduplicate_entities.sh --entity "Jeffrey Epstein" --merge-threshold 0.9
   ```

3. **Apply CPU tuning** for faster intent parsing
   ```bash
   ./scripts/apply_llm_config.sh config/llm_tuning.yaml
   sudo systemctl restart l-llm
   ```

### Short-term (This Week):

4. **Migrate to PostgreSQL** for better performance
   ```bash
   # After setting POSTGRES_URL in .env
   ./scripts/migrate_to_postgres.sh --validate
   ```

5. **Implement caching** for repeated queries (Redis or in-memory)

6. **Add /api/graph/overview** endpoint for stats/visualization

### Long-term (Next Sprint):

7. **Semantic search** with embeddings (Mistral 7B or Sentence-BERT)

8. **Entity linking** to external knowledge bases (Wikidata, DBpedia)

9. **Multi-hop reasoning** (Who introduced X to Y? When did they first meet?)

---

## FILES CREATED (READY FOR REVIEW)

**Scripts:**
- `/opt/rag/scripts/migrate_to_postgres.sh` (PREPARED)
- `/opt/rag/scripts/extract_entities.sh` (PREPARED)
- `/opt/rag/scripts/deduplicate_entities.sh` (PREPARED)
- `/opt/rag/scripts/apply_llm_config.sh` (PREPARED)

**Configs:**
- `/opt/rag/config/llm_tuning.yaml` (PREPARED)
- `/opt/rag/.gitignore` (NEEDS UPDATE)

**Documentation:**
- `/opt/rag/DIAGNOSTIC_REPORT.md` (THIS FILE)
- `/opt/rag/README.md` (NEEDS UPDATE)

**DO NOT EXECUTE** migration/extraction scripts until reviewed.

---

## APPENDIX: SQL Queries for Manual Investigation

```sql
-- Find all Epstein-related emails with substance
SELECT doc_id, subject, sender_email, date_sent, LENGTH(body_text)
FROM emails
WHERE (body_text LIKE '%epstein%' OR subject LIKE '%epstein%')
  AND LENGTH(body_text) > 500  -- Filter spam
  AND subject NOT LIKE '%Amazon%'
  AND subject NOT LIKE '%review%'
ORDER BY date_sent DESC
LIMIT 20;

-- Find all person-to-person edges
SELECT e.id, n1.name as from_person, n2.name as to_person, e.type, e.excerpt
FROM edges e
JOIN nodes n1 ON e.from_node_id = n1.id
JOIN nodes n2 ON e.to_node_id = n2.id
WHERE n1.type = 'person' AND n2.type = 'person'
LIMIT 100;

-- Deduplicate Jeffrey Epstein nodes
SELECT id, name, type, source_db, source_id
FROM nodes
WHERE name LIKE '%epstein%'
ORDER BY name;
```
