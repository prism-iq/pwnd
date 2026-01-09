# L Investigation Framework - Deployment Checklist

## ✅ Pre-Commit Verification (COMPLETED)

### Services Status
- ✓ l-api: active & enabled
- ✓ l-llm: active & enabled  
- ✓ caddy: active & enabled

### Health Checks
- ✓ API stats: https://pwnd.icu/api/stats → 200 OK
- ✓ LLM health: http://127.0.0.1:8001/health → OK
- ✓ PostgreSQL: 13,009 emails indexed

### Security Scan
- ✓ No hardcoded secrets in code
- ✓ API keys removed from config.py
- ✓ All secrets via environment variables
- ✓ .env.example has safe placeholders

### Cleanup
- ✓ Temp files moved to archive/
- ✓ Migration scripts archived
- ✓ Test files removed
- ✓ Root MD files cleaned (only README & CLAUDE)

### Documentation
- ✓ README.md updated
- ✓ CLAUDE.md present
- ✓ LICENSE present (MIT)
- ✓ docs/CODE.md (Drenai ethics)
- ✓ docs/PRINCIPLES.md
- ✓ docs/SCHEMA.md
- ✓ docs/TROUBLESHOOTING.md
- ✓ docs/ROADMAP.md
- ✓ .env.example complete

### Git Status
- ✓ All changes committed
- ✓ .gitignore covers sensitive files
- ✓ Clean working directory

---

## 🚀 GitHub Deployment Steps

### 1. Authenticate with GitHub

```bash
gh auth login
```

Follow prompts:
- Choose: GitHub.com
- Protocol: HTTPS
- Authenticate: via web browser

### 2. Create Repository

```bash
cd /opt/rag
gh repo create l-investigation-framework \
  --public \
  --source=. \
  --remote=origin \
  --push \
  --description "OSINT investigation platform with PostgreSQL, Phi-3, and detective AI persona"
```

### 3. Verify Push

```bash
gh repo view --web
```

### 4. Add Topics

```bash
gh repo edit --add-topic osint
gh repo edit --add-topic rag
gh repo edit --add-topic investigation
gh repo edit --add-topic python
gh repo edit --add-topic postgresql
gh repo edit --add-topic llm
gh repo edit --add-topic detective
gh repo edit --add-topic forensics
```

### 5. Create Release Tag

```bash
git tag -a v1.0.0 -m "Initial release - PostgreSQL production ready"
git push origin v1.0.0
gh release create v1.0.0 \
  --title "v1.0.0 - L Investigation Framework" \
  --notes "Production-ready OSINT investigation platform

## Features
- PostgreSQL backend (13K+ emails indexed)
- Phi-3-Mini local LLM
- Detective narrative AI persona
- Full-text search with trigram matching
- Entity relationship mapping
- Auto-investigation mode
- Evidence export with SHA256 verification

## Stack
- FastAPI + Python 3.11+
- PostgreSQL with FTS
- Phi-3-Mini-4K (GGUF, 2.4GB)
- Claude Haiku (optional)
- Caddy web server

## Quick Start
\`\`\`bash
git clone https://github.com/YOUR_USERNAME/l-investigation-framework.git
cd l-investigation-framework
sudo ./boom.sh
\`\`\`

Access: http://localhost

Bound by The Drenai Code - protecting the weak, reporting truth, fighting evil."
```

---

## 📊 Post-Push Verification

### Check Repository

```bash
# View repo in browser
gh repo view --web

# Check README renders correctly
gh browse

# Verify topics
gh repo view
```

### Update README URL

After repo is created, update README.md:

```bash
# Replace YOUR_USERNAME with actual username
sed -i 's|YOUR_USERNAME|youractualusername|g' README.md
git add README.md
git commit -m "Update README with actual repo URL"
git push
```

---

## 🎯 Final Outputs

Once complete, you'll have:

✅ Public GitHub repository
✅ Clean documentation
✅ Tagged v1.0.0 release
✅ Topics for discoverability
✅ README with clone instructions
✅ LICENSE (MIT + ethics disclaimer)
✅ Complete .env.example

**Repository URL:** https://github.com/YOUR_USERNAME/l-investigation-framework

---

## 🔧 Troubleshooting

### If push fails with secrets warning

GitHub may block push if it detects API keys. Check:

```bash
grep -r "sk-ant-" /opt/rag --include="*.py" --include="*.sh" | grep -v ".env" | grep -v "venv/"
```

Should return empty. If not, clean up and retry.

### If repo creation fails

Create manually:
1. Go to https://github.com/new
2. Name: `l-investigation-framework`
3. Public repo
4. No README (we have one)
5. No .gitignore (we have one)
6. Create repository

Then push:

```bash
git remote add origin https://github.com/YOUR_USERNAME/l-investigation-framework.git
git push -u origin main
```

---

**Ready for production deployment.**

**The Code:**
> "Protect the weak against the evil strong.
> It is not enough to say I will not be evil,
> evil must be fought wherever it is found."
> — David Gemmell, The Drenai Code
