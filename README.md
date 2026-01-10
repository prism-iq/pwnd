# PWND.ICU

### Epstein Document Investigation Platform

[![Live Demo](https://img.shields.io/badge/Live-pwnd.icu-blue?style=for-the-badge)](https://pwnd.icu)
[![Documents](https://img.shields.io/badge/Documents-33,598-green?style=for-the-badge)](https://pwnd.icu)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

> *"Protect the weak against the evil strong.*
> *It is not enough to say I will not be evil,*
> *evil must be fought wherever it is found."*
> **— David Gemmell, The Drenai Code**

---

## What is This?

**PWND.ICU** is an AI-powered OSINT platform for investigating the Epstein case documents. Ask questions in natural language, get answers with source citations from **33,598 documents** including:

| Source | Documents | Contents |
|--------|-----------|----------|
| FOIA Releases | 13,000+ | FBI files, DOJ reports, court records |
| Court Depositions | 8,500+ | Sworn testimony, victim statements |
| Maxwell Trial | 5,000+ | Evidence, transcripts, exhibits |
| Flight Logs | 2,000+ | Lolita Express manifests, pilot logs |
| Financial Records | 3,000+ | Wire transfers, accounts, tax records |
| Email Corpus | 2,000+ | Communications, contacts, schedules |

---

## Try It Now

**Live:** [https://pwnd.icu](https://pwnd.icu)

### Chat Mode
Ask questions, get AI-synthesized answers with document citations:

```
You: Who flew on Epstein's plane with Bill Clinton?

AI: According to flight logs [1][2], Bill Clinton flew on
    Epstein's aircraft multiple times between 2001-2003...

    Sources:
    [1] EFTA00010720.txt - Flight manifest March 2002
    [2] Epstein_Depositions_Full.txt - Pilot testimony
```

### Search Mode
Direct full-text search across all documents with relevance scoring.

---

## Self-Host

```bash
git clone https://github.com/prism-iq/pwnd.git
cd pwnd
sudo ./install.sh
```

**That's it.** The installer handles:
- OS detection (Arch, Debian, Ubuntu, Fedora)
- Dependencies (PostgreSQL, Python 3.11+, Caddy)
- Phi-3 LLM download (2.4GB local model)
- Database setup + document import
- Service configuration + health checks

**Access:** http://localhost after install

---

## Features

### RAG-Powered Chat
- Natural language questions about documents
- AI-synthesized answers with source citations
- Conversation history persistence
- Streaming responses (real-time typing)

### Document Search
- Full-text search across 33,598 documents
- Relevance scoring + snippet extraction
- Filter by document type/source
- Entity extraction (names, dates, locations)

### Investigation Tools
- Entity relationship graph
- Timeline reconstruction
- Pattern detection
- Evidence chain tracking

### Export & Verification
- SHA256 document verification
- Chain of custody tracking
- Legal-ready evidence packages
- Social media templates (Twitter, Reddit, YouTube)

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                         Browser                              │
│                    (Chat / Search UI)                        │
└─────────────────────────┬────────────────────────────────────┘
                          │ REST API + SSE Streaming
                          ▼
┌──────────────────────────────────────────────────────────────┐
│                      FastAPI Backend                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ /api/chat   │  │ /api/search │  │ /api/investigate    │  │
│  │ (RAG Chat)  │  │ (Documents) │  │ (Graph Analysis)    │  │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
└─────────┼────────────────┼────────────────────┼──────────────┘
          │                │                    │
    ┌─────▼─────┐    ┌─────▼─────┐        ┌─────▼─────┐
    │  Phi-3    │    │PostgreSQL │        │  Claude   │
    │(Local LLM)│    │(Documents)│        │  Haiku    │
    │  2.4GB    │    │   + FTS   │        │(Optional) │
    └───────────┘    └───────────┘        └───────────┘
```

---

## API Endpoints

### Chat
```bash
# Send message, get AI response with sources
curl -X POST https://pwnd.icu/api/chat/send \
  -H "Content-Type: application/json" \
  -d '{"message": "Who is Ghislaine Maxwell?"}'

# Stream response (SSE)
curl -X POST https://pwnd.icu/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "What did the pilot testify?"}'

# List conversations
curl https://pwnd.icu/api/chat/conversations
```

### Search
```bash
# Full-text search
curl "https://pwnd.icu/api/search?q=flight+logs+clinton"

# Document by ID
curl "https://pwnd.icu/api/document/EFTA00010720"
```

### System
```bash
curl https://pwnd.icu/api/health
curl https://pwnd.icu/api/stats
```

---

## Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Linux (any distro) | Arch, Debian, Ubuntu |
| CPU | 4 cores | 8+ cores |
| RAM | 8GB | 16GB+ |
| Storage | 10GB | 50GB+ SSD |
| Python | 3.11+ | 3.12+ |

---

## Configuration

```bash
# .env file (created by install.sh)

# Database
DATABASE_URL=postgresql://lframework:xxx@localhost:5432/lframework

# Local LLM (auto-downloaded)
LLM_MODEL_PATH=/opt/rag/llm/phi-3-mini-4k-instruct.Q4_K_M.gguf

# Optional: Claude Haiku for advanced analysis
ANTHROPIC_API_KEY=sk-ant-api03-xxx

# Rate limiting
HAIKU_DAILY_LIMIT=200
MAX_REQUESTS_PER_DAY=30
```

---

## The Code

This project is bound by a moral foundation:

**We WILL:**
- Protect victims (anonymize where needed)
- Report only documented facts with citations
- Distinguish confirmed facts from allegations
- Follow evidence wherever it leads
- Maintain chain of custody

**We will NOT:**
- Fabricate or embellish evidence
- Violate victim privacy
- Add knowledge from outside the corpus
- Back away from uncomfortable truth
- Use this for harassment or doxxing

---

## Document Sources

All documents are from public FOIA releases and court records:

| Source | Description |
|--------|-------------|
| EFTA (Epstein Files Transfer Act) | Official FOIA releases |
| SDNY Court Records | Federal court filings |
| Maxwell Trial Exhibits | Trial evidence 2021-2022 |
| DOJ OPR Report | Office of Professional Responsibility |
| Flight Logs | FAA records, pilot testimony |
| Deposition Transcripts | Sworn testimony under oath |

---

## Development

```bash
# Clone
git clone https://github.com/prism-iq/pwnd.git
cd pwnd

# Setup virtualenv
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run dev server
uvicorn app.main:app --reload --port 8002
```

**Structure:**
```
pwnd/
├── app/                  # FastAPI application
│   ├── main.py          # Entry point
│   ├── routes.py        # Search endpoints
│   ├── routes_chat.py   # Chat endpoints (RAG)
│   ├── db.py            # Database layer
│   └── llm_client.py    # LLM integration
├── static/              # Frontend
│   ├── index.html       # Search interface
│   └── chat.html        # Chat interface
├── llm/                 # Local LLM models
├── scripts/             # Setup utilities
└── install.sh           # One-command setup
```

---

## License

MIT License with moral foundation.

Use for investigation, journalism, research, and justice.
Do NOT use for harassment, stalking, or revenge.

See [LICENSE](LICENSE) for full terms.

---

## Links

- **Live Demo:** [https://pwnd.icu](https://pwnd.icu)
- **Issues:** [GitHub Issues](https://github.com/prism-iq/pwnd/issues)
- **Source:** [github.com/prism-iq/pwnd](https://github.com/prism-iq/pwnd)

---

*"Evil must be fought wherever it is found."*
