# Roadmap - L Investigation Framework

**Current Version:** 1.0.0
**Status:** Production-ready with known limitations
**Last Updated:** 2026-01-08

---

## Current State (v1.0.0)

### ✅ What Works

**Core Features:**
- [x] Natural language query interface
- [x] Auto-investigation loop (recursive query chaining)
- [x] Real-time SSE streaming
- [x] Email FTS search (13,009 emails indexed)
- [x] Graph relationship queries (14,437 nodes, 3,034 edges)
- [x] Dual-LLM pipeline (Phi-3-Mini 4K + Claude Haiku)
- [x] Source citation with clickable IDs
- [x] Conversation history
- [x] Dark theme UI
- [x] Mobile responsive

**Infrastructure:**
- [x] Systemd service management
- [x] Caddy reverse proxy with HTTPS
- [x] Local Phi-3-Mini 4K (llama.cpp)
- [x] Claude Haiku API integration
- [x] SQLite with WAL mode

**Documentation:**
- [x] Comprehensive docs (7 files)
- [x] Installation guide
- [x] Troubleshooting guide
- [x] Diagnostic report

### ⚠️ Known Issues

**Performance:**
- Query time: ~57s (target: <10s)
- Phi-3 intent: 2-3s (target: <1s)
- No caching (repeated queries re-execute)

**Data Quality:**
- Spam emails dominate results (Amazon, XM Radio)
- Entity extraction incomplete (1.1 per email, should be 5-10)
- Duplicate nodes (6+ Epstein nodes)
- No Ghislaine Maxwell node (despite 17 email mentions)

**Features:**
- No semantic search (keyword FTS only)
- No entity linking (Wikidata, DBpedia)
- No multi-hop reasoning
- No timeline visualization

### 📦 Ready for Execution

Scripts prepared but not run:
- Entity extraction ($1.63 cost, 30-60 min)
- PostgreSQL migration (1-2 hours)
- Entity deduplication (2 min)
- CPU optimization (1 min)

---

## Short-Term (v1.1 - Next 2 Weeks)

### Priority 1: Fix Critical Issues

**1. Spam Filtering**
- Status: Not started
- Effort: 1 hour
- Impact: High (fixes main user complaint)

**Implementation:**
```python
# app/pipeline.py - Add to email query
WHERE LENGTH(body_text) > 500
  AND subject NOT LIKE '%Amazon%'
  AND subject NOT LIKE '%review%'
  AND subject NOT LIKE '%offer%'
  AND subject NOT LIKE '%Special%'
```

**2. Entity Extraction**
- Status: Script ready, needs execution
- Effort: 30-60 min runtime + $1.63 API cost
- Impact: High (fills graph with missing entities)

**Command:**
```bash
./scripts/extract_entities.sh --batch-size 100 --max-docs 13009
```

**3. Entity Deduplication**
- Status: Script ready
- Effort: 2 min
- Impact: Medium (consolidates duplicate nodes)

**Command:**
```bash
./scripts/deduplicate_entities.sh --auto --merge-threshold 0.9
```

---

### Priority 2: Performance Optimization

**4. Apply CPU Tuning**
- Status: Config ready
- Effort: 1 min
- Impact: Medium (50% faster intent parsing)

**Command:**
```bash
./scripts/apply_llm_config.sh config/llm_tuning.yaml
```

**Expected:** 2-3s → 1s for intent parsing

**5. Implement Query Caching**
- Status: Not started
- Effort: 2 hours
- Impact: High for repeated queries

**Implementation:**
```python
# app/llm_client.py
from functools import lru_cache
from hashlib import sha256

cache = {}

async def call_mistral_cached(prompt: str):
    key = sha256(prompt.encode()).hexdigest()
    if key in cache:
        return cache[key]
    result = await call_mistral(prompt)
    cache[key] = result
    return result
```

---

### Priority 3: User Experience

**6. Add Source Viewer Page**
- Status: Not started
- Effort: 2 hours
- Impact: Medium (better UX)

**Features:**
- `/source/{id}` route
- Full email display with metadata
- Back link to chat
- Copy button for email text

**7. Add Footer to All Pages**
- Status: Not started
- Effort: 30 min
- Impact: Low (branding)

**Content:**
- Left: "© 2025 Flow"
- Center: Links (Sources, Licenses, GitHub)
- Right: Contact email

---

## Medium-Term (v1.2 - Next Month)

### 8. PostgreSQL Migration
- Status: Script ready, needs PostgreSQL setup
- Effort: 1-2 hours migration + 1 day testing
- Impact: Very high (10-100x faster queries)

**Benefits:**
- Connection pooling for concurrent users
- Better FTS (ts_vector)
- JSONB for flexible queries
- Row-level security (if multi-tenant later)

**Risks:**
- Requires VPS upgrade (more RAM)
- Migration downtime
- Need backup strategy

---

### 9. Semantic Search with Embeddings
- Status: Not started
- Effort: 1 week
- Impact: High (better search quality)

**Approach:**
```python
# Use Sentence-BERT or Mistral embeddings
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')

# Index emails
for email in emails:
    embedding = model.encode(email['body_text'])
    store_embedding(email['doc_id'], embedding)

# Search by similarity
query_embedding = model.encode(user_query)
similar_docs = find_similar(query_embedding, top_k=10)
```

**Storage:** Add `embeddings` table or migrate to pgvector

---

### 10. Multi-Hop Reasoning
- Status: Not started
- Effort: 2 weeks
- Impact: High (unlock new use cases)

**Features:**
- "Who introduced X to Y?"
- "When did A and B first meet?"
- Graph traversal with LLM reasoning

**Implementation:**
- Use recursive CTEs in SQL for path finding
- LLM evaluates each hop for relevance
- Present reasoning chain to user

---

### 11. Timeline Visualization
- Status: Not started
- Effort: 1 week
- Impact: Medium (better pattern detection)

**Features:**
- Interactive timeline view
- Filter by entity, date range
- Zoom in/out
- Export as image/PDF

**Tech Stack:**
- D3.js or Chart.js
- FastAPI endpoint: `/api/timeline?entity=...`

---

## Long-Term (v2.0 - Next Quarter)

### 12. Entity Linking to External Knowledge Bases
- Status: Not started
- Effort: 1 month
- Impact: High (enrichment)

**Sources:**
- Wikidata (structured data)
- DBpedia (Wikipedia extracts)
- OpenCorporates (company data)

**Features:**
- Auto-link "Donald Trump" → Wikidata ID Q22686
- Fetch external info (DOB, occupation, net worth)
- Display in entity modal

---

### 13. Export Formats
- Status: Not started
- Effort: 1 week
- Impact: Medium (professional use)

**Formats:**
- PDF report (markdown → PDF)
- JSON dump (all conversation data)
- CSV (email list, entity list)
- DOCX (investigation summary)

---

### 14. Real-Time Ingestion
- Status: Not started
- Effort: 1 month
- Impact: High (live monitoring)

**Features:**
- Monitor email source (IMAP, mbox file)
- Auto-import new emails
- Re-run entity extraction
- Notify on new findings

**Tech Stack:**
- Celery for background tasks
- Redis for job queue
- Watchdog for file monitoring

---

### 15. Multi-Tenant Support
- Status: Not started
- Effort: 2 months
- Impact: Very high (SaaS potential)

**Features:**
- User authentication (OAuth, JWT)
- Isolated investigations per user
- Shared vs private corpora
- Usage quotas and billing

**Tech Stack:**
- PostgreSQL with row-level security
- Auth0 or custom JWT
- Stripe for billing

---

## Future Ideas (v3.0+)

### 16. Collaborative Investigations
- Multiple users on same investigation
- Comments on findings
- Task assignment
- Activity feed

### 17. Plugin System
- Custom data sources (Slack, Discord, Twitter)
- Custom LLMs (OpenAI, local Llama 3)
- Custom visualizations
- Custom export formats

### 18. Advanced Analytics
- Network centrality (who's most connected?)
- Community detection (clustering)
- Anomaly detection (unusual patterns)
- Predictive modeling (what happens next?)

### 19. Voice Interface
- Voice query input
- TTS for results
- Hands-free investigation

### 20. Mobile App
- Native iOS/Android app
- Offline mode
- Push notifications for findings

---

## Performance Targets

| Metric | Current | v1.1 | v1.2 | v2.0 |
|--------|---------|------|------|------|
| Query time | 57s | 30s | <10s | <5s |
| Entities/email | 1.1 | 5-10 | 5-10 | 10-20 |
| Duplicate rate | 6+ | <2 | <1% | <0.1% |
| Concurrent users | 1 | 1 | 10 | 100+ |
| Email corpus | 13k | 13k | 100k | 1M+ |

---

## Success Metrics (v2.0)

### Technical
- [ ] Query time: <5s (95th percentile)
- [ ] API availability: 99.9%
- [ ] Zero critical security issues
- [ ] 100% test coverage on core features

### User Experience
- [ ] Mobile responsive (WCAG AA)
- [ ] Accessibility score >90 (Lighthouse)
- [ ] Zero console errors
- [ ] <2s time to first byte (TTFB)

### Data Quality
- [ ] Entity extraction: >90% recall
- [ ] Duplicate rate: <0.1%
- [ ] FTS relevance: User feedback >4/5

---

## Decision Points

### PostgreSQL Migration
**When to migrate:**
- ✅ Now: If expecting >10 concurrent users
- ✅ Now: If corpus will exceed 100k emails
- ⏸️ Later: If single user, <50k emails (SQLite fine)

**Cost:** $20-50/month for VPS upgrade (more RAM)

---

### Semantic Search
**When to add:**
- ✅ Now: If keyword FTS has poor results
- ✅ Now: If users want "find similar emails"
- ⏸️ Later: If keyword FTS works well enough

**Cost:** ~4GB storage for embeddings (13k emails)

---

### Multi-Tenant
**When to add:**
- ✅ Now: If planning SaaS/commercial use
- ⏸️ Later: If personal/research project only

**Cost:** 2-3 months development time

---

## Release Schedule

### v1.1 (2 weeks)
- Spam filtering
- Entity extraction
- Deduplication
- CPU tuning
- Query caching
- Source viewer page

### v1.2 (1 month)
- PostgreSQL migration
- Semantic search
- Multi-hop reasoning
- Timeline visualization

### v2.0 (3 months)
- Entity linking
- Export formats
- Real-time ingestion
- Multi-tenant

### v3.0 (6 months)
- Collaborative features
- Plugin system
- Advanced analytics
- Mobile app

---

## Contributing

**Areas needing help:**
1. Frontend: React/Vue migration (if desired)
2. Entity extraction: Improve prompt engineering
3. Performance: Optimize SQL queries
4. Documentation: Video tutorials
5. Testing: Unit tests, integration tests

**Contact:** See `/opt/rag/LICENSE` for author info

---

**TL;DR:**

v1.0 is production-ready but slow (57s queries). v1.1 (2 weeks): fix spam, extract entities, add caching. v1.2 (1 month): PostgreSQL migration, semantic search. v2.0 (3 months): entity linking, exports, multi-tenant. Target: <5s queries, 100+ concurrent users, 1M+ emails.

**Read previous:** `/opt/rag/docs/SCHEMA.md` for database structure.
