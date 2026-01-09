# Quick Start Guide

Get L Investigation Framework up and running in 5 minutes.

## 1. Download & Extract

```bash
wget https://github.com/yourusername/l-investigation-framework/releases/latest/download/l-investigation-framework-1.0.0.tar.gz
tar -xzf l-investigation-framework-1.0.0.tar.gz
cd l-investigation-framework
```

## 2. Run Installation

```bash
sudo ./install.sh
```

**What this does:**
- Detects OS (Arch/Ubuntu/Debian)
- Installs system dependencies (Python, SQLite, Caddy)
- Creates virtual environment
- Installs Python packages
- Creates systemd services
- Sets up Caddy web server

## 3. Download Mistral Model

```bash
wget https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf
mv mistral-7b-instruct-v0.2.Q4_K_M.gguf models/
```

## 4. Configure Environment

```bash
cp .env.example .env
nano .env  # Add your Anthropic API key
```

**Required:**
- `HAIKU_API_KEY` - Get from https://console.anthropic.com/

## 5. Import Your Data

### Option A: You have email data
```bash
# Import to db/sources.db
# (Use your own import script)
```

### Option B: Testing only
```bash
# Use sample data (if provided)
# Or skip - app will work but have no emails
```

## 6. Start Services

```bash
./scripts/rebuild.sh
```

**This starts:**
- `l-llm` - Mistral 7B backend (port 8001)
- `l-api` - FastAPI server (port 8002)
- `caddy` - Web server (port 80)

## 7. Access

Open browser: **http://localhost**

## Troubleshooting

### Services won't start
```bash
sudo journalctl -u l-llm -n 50
sudo journalctl -u l-api -n 50
```

### Out of memory
- Mistral requires ~8GB RAM
- Reduce Caddy workers or use smaller model

### Database errors
```bash
sqlite3 db/sessions.db "SELECT * FROM settings;"
```

## Next Steps

- Import email data → `db/sources.db`
- Build graph → `db/graph.db`
- Configure domain → Edit `Caddyfile`
- Enable HTTPS → `caddy fmt Caddyfile`

## Documentation

Full docs: See `README.md`

## Support

Issues: https://github.com/yourusername/l-investigation-framework/issues
