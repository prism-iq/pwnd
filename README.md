# L Investigation Framework

**OSINT investigation platform bound by The Code**

> *"Protect the weak against the evil strong.*
> *It is not enough to say I will not be evil,*
> *evil must be fought wherever it is found."*
> **— David Gemmell, The Drenai Code**

---

## Quick Start

```bash
git clone https://github.com/YOUR_USERNAME/l-investigation-framework.git
cd l-investigation-framework
sudo ./boom.sh
```

That's it. The `boom.sh` script handles everything:
- ✓ Detects your OS (Arch, Debian, Ubuntu, Fedora)
- ✓ Installs dependencies (PostgreSQL, Python, Caddy)
- ✓ Downloads Phi-3-Mini LLM model
- ✓ Creates database and schema
- ✓ Starts all services
- ✓ Runs health checks

**Access:** http://localhost

---

## What is This?

L Investigation Framework is a production-ready OSINT tool for:
- **Email corpus analysis** (13,000+ documents)
- **Entity relationship mapping** (graph database)
- **Criminal pattern detection** (AI-powered)
- **Evidence export** (SHA256-verified packages)
- **Chain of custody** (legal-ready)

**Bound by The Code:**
- Protect victims (anonymization, dignity preserved)
- Report truth (corpus-only, source citations)
- Never lie (facts vs hypotheses clearly marked)
- Fight evil (follow evidence wherever it leads)

---

## Architecture

```
┌─────────────┐
│   Browser   │
│  (Frontend) │
└──────┬──────┘
       │ SSE Streaming
       ▼
┌─────────────┐      ┌──────────────┐
│  FastAPI    │◄────►│   Phi-3      │
│   (API)     │      │ (Local LLM)  │
└──────┬──────┘      └──────────────┘
       │
       ├──────────────┬──────────────┐
       ▼              ▼              ▼
┌─────────────┐  ┌──────────┐  ┌──────────┐
│ PostgreSQL  │  │  Claude  │  │  Caddy   │
│  (Database) │  │  Haiku   │  │  (Web)   │
│             │  │(Optional)│  │          │
└─────────────┘  └──────────┘  └──────────┘
```

**Stack:**
- **Backend:** FastAPI + Python 3.11+
- **Database:** PostgreSQL (production) or SQLite (dev)
- **Local LLM:** Phi-3-Mini-4K (GGUF, 2.4GB)
- **API LLM:** Claude Haiku (optional, for advanced analysis)
- **Web Server:** Caddy (auto-HTTPS)
- **Search:** Full-text search (FTS) + vector embeddings

---

## Requirements

**Minimum:**
- **OS:** Linux (Arch, Debian, Ubuntu, Fedora)
- **CPU:** 4 cores
- **RAM:** 8GB
- **Storage:** 10GB

**Recommended:**
- **CPU:** 8+ cores
- **RAM:** 16GB+
- **Storage:** 50GB+ SSD

---

## Configuration

After running `boom.sh`, edit `.env` for your setup:

```bash
# Database (PostgreSQL auto-configured by setup-db.sh)
DATABASE_URL=postgresql://lframework:xxx@localhost:5432/lframework

# LLM Model (auto-downloaded by download-model.sh)
LLM_MODEL_PATH=/opt/rag/llm/phi-3-mini-4k-instruct.Q4_K_M.gguf

# Optional: Claude Haiku for advanced analysis
ANTHROPIC_API_KEY=sk-ant-api03-xxx

# Rate limiting (Anti-DDoS)
HAIKU_DAILY_LIMIT=200
MAX_REQUESTS_PER_DAY=30
```

Full configuration: see `.env.example`

---

## Usage

### Web Interface

1. **Ask a question:**
   "Who is Jeffrey Epstein?"

2. **View sources:**
   Click `[#ID]` citations to see original documents

3. **Auto-investigate:**
   Enable toggle for automatic follow-up queries (max 20)

### API

**Query:**
```bash
curl "http://localhost/api/ask?q=trump+connections"
```

**Health check:**
```bash
curl "http://localhost/api/health"
```

**Stats:**
```bash
curl "http://localhost/api/stats"
```

### CLI Tools

**Import emails:**
```bash
./scripts/import.sh /path/to/emails
```

**Build graph:**
```bash
./scripts/build-graph.sh
```

**Check services:**
```bash
sudo systemctl status l-llm l-api caddy
```

---

## The Code - Moral Foundation

This system exists to **fight evil wherever it is found.**

**We will:**
- ✓ Protect victims (anonymize, prioritize safety)
- ✓ Report facts (cite sources, no speculation)
- ✓ Distinguish truth from hypothesis
- ✓ Follow evidence (no matter who is implicated)
- ✓ Preserve chain of custody (SHA256, timestamps)

**We will NOT:**
- ✗ Fabricate evidence
- ✗ Violate victim privacy
- ✗ Add external knowledge (corpus-only)
- ✗ Back away from uncomfortable truth

**Email phrasing:**
- ✓ "According to LinkedIn invitation email [#7837], ..."
- ✗ "Based on his LinkedIn profile" (external knowledge)

---

## Evidence Export

Generate tamper-proof evidence packages:

```bash
./scripts/export-evidence.sh investigation_001
```

**Includes:**
- SHA256 verification
- Chain of custody
- Social media templates (Twitter, Reddit, YouTube)
- Legal-ready format
- The Code moral statement

**Example:** `evidence_001.tar.gz` (ready to share)

---

## Social Media Integration

Exported evidence packages include platform-optimized templates:

| Platform | Format | File |
|----------|--------|------|
| Twitter | Thread (280 chars) | `twitter_thread.txt` |
| Reddit | Markdown post | `reddit_post.md` |
| YouTube | Video description | `youtube_description.txt` |
| TikTok | 60s script | `tiktok_script.txt` |
| LinkedIn | Professional post | `linkedin_post.txt` |
| Instagram | Carousel captions | `instagram_captions.txt` |

All templates include:
- Evidence citations
- SHA256 verification
- The Code statement
- Call-to-action

---

## Troubleshooting

**Services not starting:**
```bash
sudo journalctl -u l-llm -n 50
sudo journalctl -u l-api -n 50
```

**Database errors:**
```bash
psql -U lframework -d lframework -h localhost
```

**Model not found:**
```bash
./scripts/download-model.sh
```

**Port conflicts:**
Edit `.env` and change `PORT=8002` to another port

---

## Development

**Structure:**
```
pwnd/
├── app/              # FastAPI application
├── llm/              # Local LLM backend (Phi-3)
├── static/           # Frontend (HTML/JS/CSS)
├── scripts/          # Setup & utility scripts
├── templates/        # Service templates
├── docs/             # Documentation
├── boom.sh           # Single entry point
├── .env.example      # Environment template
└── LICENSE           # MIT + The Code
```

**Run in dev mode:**
```bash
source venv/bin/activate
uvicorn app.main:app --reload --port 8002
```

---

## License

MIT License with moral foundation.

**This software is bound by The Code:**
- Use for investigation, justice, protection
- Do NOT use for harassment, doxxing, revenge
- Chain of custody and evidence integrity required
- Victim protection is non-negotiable

See [LICENSE](LICENSE) for full terms.

---

## Credits

- **Moral Foundation:** David Gemmell's Drenai Code
- **LLM:** Phi-3-Mini (Microsoft), Claude Haiku (Anthropic)
- **Stack:** FastAPI, PostgreSQL, Caddy
- **Purpose:** Fighting evil wherever it is found

---

## Support

- **Issues:** [GitHub Issues](https://github.com/prism-iq/pwnd/issues)
- **Docs:** [docs/](docs/)
- **The Code:** [docs/CODE.md](docs/CODE.md)

---

*"Evil must be fought wherever it is found."*
**— The Code**
