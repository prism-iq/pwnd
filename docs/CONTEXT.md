# Project Vision - L Investigation Framework

## What This Is

L Investigation Framework is a production-grade OSINT (Open Source Intelligence) investigation platform designed for analyzing large email corpora and discovering hidden relationships through graph analysis and AI-driven insights.

Think of it as: **"Talking to Claude, but for OSINT"** - natural language queries that automatically chain together to uncover connections, patterns, and evidence.

## The Problem

Traditional OSINT workflows are fragmented:
- **Keyword search**: Find emails containing "Epstein" → 1,207 results → manual review
- **Graph exploration**: Who knows who? → SQL queries → JOIN tables → visualize
- **Timeline analysis**: What happened when? → Filter by date → chronological sort
- **Pattern detection**: Financial transfers? → Regex → aggregate → correlate

Investigators spend 80% of their time on data wrangling, 20% on actual analysis.

## The Solution

**Single Interface:** Natural language query → AI-driven investigation → Automatic follow-up questions

**Example Session:**
```
User: "Who is Jeffrey Epstein?"
→ System finds entities, relationships, emails
→ System suggests: "What financial entities appear in his communications?"
→ Auto-investigates if enabled
→ System suggests: "What connections does he have to Trump?"
→ Chains continue until pattern emerges
```

**Key Innovation:** The system doesn't just answer questions - it **asks the next question for you**.

## Core Features

### 1. Email Corpus Analysis
- **13,009 indexed emails** (2007-2021, 948MB)
- Full-text search with SQLite FTS5
- Metadata extraction: sender, recipients, dates, URLs, IPs
- Thread reconstruction via `in_reply_to` and `thread_id`

### 2. Graph Database
- **14,437 nodes** (persons, orgs, locations, dates, amounts)
- **3,034 edges** (relationships: knows, works_for, owns_property)
- Entity deduplication via aliases table
- Source tracking: every node links back to originating email

### 3. Dual-LLM Pipeline
- **Phi-3-Mini 4K (local)**: Intent parsing (2-3s)
  - Converts "who knows trump" → `{"intent": "connections", "entities": ["trump"]}`
  - No API cost, privacy-preserving
  - **Note**: Function names say `call_mistral()` but actually use Phi-3
- **Claude Haiku (API)**: Deep analysis (3-5s)
  - Synthesizes findings into readable narrative
  - Extracts suggested follow-up queries
  - Confidence scoring and contradiction detection

### 4. Auto-Investigation Loop
- Recursive query chaining based on AI suggestions
- Max 5 queries per session (configurable)
- User can stop/pause at any time
- Progress tracking in banner

### 5. Real-Time Streaming
- Server-Sent Events (SSE) for live updates
- Status messages: "Parsing query...", "Analyzing with Haiku..."
- Incremental response rendering (markdown)
- Graceful error handling

## Use Cases

### Investigative Journalism
- "Find all communications between X and Y in 2015"
- "What financial transactions appear in these emails?"
- "Who introduced X to Y? When did they first meet?"

### Legal Discovery
- "Show all emails where contract Z is mentioned"
- "Timeline of events related to company X"
- "Who had knowledge of event Y before date Z?"

### OSINT Research
- "Map connections between entities A, B, C"
- "Find emails discussing topic X sent from domain Y"
- "Extract all phone numbers and addresses from corpus"

### Threat Intelligence
- "Identify all domains mentioned in suspicious emails"
- "Find communication patterns indicating coordination"
- "Extract IOCs (IPs, URLs, file hashes) from corpus"

## Design Philosophy

### 1. Privacy First
- **Local LLM** for intent parsing (no sensitive data to API)
- **Self-hosted** (full control over data)
- **No telemetry** (no analytics, no tracking)
- **On-premises deployment** (can run fully offline after setup)

### 2. Transparency
- **Show your work**: Every finding cites source emails
- **Confidence scoring**: AI indicates certainty level
- **Contradiction detection**: Flags conflicting information
- **Suggested queries**: User sees reasoning behind follow-ups

### 3. Performance
- **Target: <10s per query** (currently 57s, needs optimization)
- **Streaming responses** (results appear incrementally)
- **Caching** (prepared but not yet implemented)
- **PostgreSQL migration ready** (10-100x faster queries)

### 4. Extensibility
- **Modular architecture**: Easy to swap LLMs, databases
- **Plugin system**: Crypto/stegano modules already present
- **API-first**: All features accessible via REST API
- **Documentation**: Comprehensive docs for customization

## Architecture Decisions

### Why SQLite (for now)?
- **Zero configuration**: No DB server to manage
- **Excellent FTS**: FTS5 is production-grade
- **Single file**: Easy backup and portability
- **Migration path**: PostgreSQL script ready when needed

### Why Local LLM (Phi-3-Mini)?
- **Privacy**: Intent parsing never leaves the server
- **Cost**: No API charges for 95% of queries
- **Speed**: 2-3s on CPU (acceptable for intent parsing)
- **Offline**: Works without internet (after initial setup)
- **Small**: 2.4GB model fits in RAM easily

### Why Claude Haiku (API)?
- **Quality**: Better analysis than local 7B models
- **Cost-effective**: $0.25 per 1M tokens (analysis only)
- **Speed**: 3-5s for complex synthesis
- **Future-proof**: Easy to swap to Opus/Sonnet for higher quality

### Why SSE (not WebSockets)?
- **Simplicity**: One-way server→client stream (perfect fit)
- **Reliability**: Auto-reconnect in browsers
- **HTTP/2 compatible**: Works through proxies
- **Standard**: EventSource API built into browsers

## Technical Stack

```
Frontend:
- Vanilla JS (no framework bloat)
- Markdown rendering (Marked.js)
- Dark theme (custom CSS, no Tailwind)

Backend:
- FastAPI (Python async framework)
- uvicorn (ASGI server)
- httpx (async HTTP client)
- pydantic (data validation)

Database:
- SQLite 3.x (sources, graph, sessions)
- FTS5 (full-text search)
- JSON columns (flexible metadata)

LLMs:
- Phi-3-Mini 4K Instruct (Q4 quantization, 2.4GB)
- llama.cpp server (CPU inference)
- Claude Haiku 4 (via Anthropic API)

Infrastructure:
- Caddy (web server, TLS termination)
- systemd (service management)
- Linux (Arch/Ubuntu/Debian)
```

## Current State (v1.0.0)

### What Works
- ✅ Natural language query interface
- ✅ Auto-investigation loop
- ✅ Real-time SSE streaming
- ✅ Email FTS search
- ✅ Graph relationship queries
- ✅ Dual-LLM pipeline
- ✅ Source citation with clickable IDs
- ✅ Conversation history
- ✅ Dark theme UI
- ✅ Mobile responsive

### Known Issues
- ⚠️ Spam emails dominate results (needs filtering)
- ⚠️ Entity extraction incomplete (1.1 per email, should be 5-10)
- ⚠️ Duplicate nodes (6+ Epstein nodes)
- ⚠️ Query too slow (57s, target <10s)
- ⚠️ No caching (repeated queries re-execute)

### Ready for Execution
- 📦 PostgreSQL migration script
- 📦 Haiku entity extraction ($1.63 cost)
- 📦 Entity deduplication script
- 📦 CPU optimization config

## Future Vision

### Short-term (Next Sprint)
1. **Spam filtering**: Exclude promotional emails from results
2. **Entity extraction**: Run Haiku NER on full corpus
3. **Deduplication**: Merge duplicate person nodes
4. **CPU tuning**: Apply optimized Mistral config

### Medium-term (Next Quarter)
1. **PostgreSQL migration**: Better concurrency and performance
2. **Semantic search**: Embedding-based similarity (beyond keywords)
3. **Redis caching**: Cache repeated queries for 5 minutes
4. **Multi-hop reasoning**: "Who introduced X to Y?"

### Long-term (Next Year)
1. **Entity linking**: Connect to Wikidata, DBpedia
2. **Timeline visualization**: Interactive graph view
3. **Export formats**: PDF reports, JSON dumps, CSV
4. **Multi-tenant**: Support multiple isolated investigations
5. **Real-time ingestion**: Monitor email sources for new data

## Success Metrics

### Performance
- Query time: <10s (from 57s current)
- API availability: 99.9%
- Database size: Handles 100k+ emails

### Quality
- Entity extraction: 5-10 per email (from 1.1 current)
- Duplicate rate: <1% (from 6+ per entity current)
- Result relevance: User feedback system

### User Experience
- Mobile responsive: Works on 375px viewport
- Accessibility: WCAG AA contrast ratios
- Error recovery: Graceful handling, no crashes

## License

MIT License - See `/opt/rag/LICENSE`

Author: Flow

---

**TL;DR:**

OSINT platform for investigating email corpora using AI. Natural language queries → Auto-investigation loop → Entity graph discovery. Local LLM (Phi-3-Mini) + API LLM (Haiku) for privacy and quality. Currently handles 13k emails, 14k entities. Target: <10s queries, 100k+ emails, production-grade performance.

**Read next:** `/opt/rag/docs/PRINCIPLES.md` for architectural decisions.
