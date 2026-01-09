# Learnings from Other OSINT Tools (GitHub Research)

**Research Date:** 2026-01-08
**Purpose:** Learn best practices from established OSINT/investigation frameworks

---

## Top Email OSINT Tools Analyzed

### 1. h8mail - Email Breach Hunting
**URL:** https://github.com/khast3x/h8mail
**Stars:** High popularity
**Key Features:**
- Email OSINT & password breach hunting
- Uses premium services + local breaches
- Chases down related emails (connection mapping)

**What We Can Learn:**
- ✓ Breach correlation (link emails to known data breaches)
- ✓ Related email discovery (expand investigation graph)
- ✓ API integration with breach databases (HaveIBeenPwned, etc.)

### 2. comms-analyzer-toolbox - Corpus Analysis
**URL:** https://github.com/bitsofinfo/comms-analyzer-toolbox
**Stars:** Moderate
**Key Features:**
- MBOX file analysis (email corpus)
- Elasticsearch + Kibana integration
- Graph visualization of communications
- CSV text message support

**What We Can Learn:**
- ✓ Elasticsearch for large corpus (better than SQLite FTS)
- ✓ Kibana dashboards (visual investigation)
- ✓ MBOX format support (standard email export)
- ✓ Communication graph visualization

### 3. Paliscope - Evidence Management
**URL:** https://usersearch.org/updates/top-10-rated-osint-tools-from-github
**Key Features:**
- Chain of custody automation
- Timestamps + digital signatures
- Legal admissibility focus
- Proves data hasn't been altered

**What We Can Learn:**
- ✓ Digital signatures (beyond SHA256 hashes)
- ✓ Automated chain of custody logging
- ✓ Legal-grade evidence packaging
- ✓ Tamper-proof verification

### 4. Hunchly - Automated Web Investigation
**URL:** https://usersearch.org/updates/top-10-rated-osint-tools-from-github
**Key Features:**
- Records everything during research
- Automatic capture with timestamps
- Tracks deleted content
- Legal proof of discovery

**What We Can Learn:**
- ✓ Session recording (track investigation path)
- ✓ Deleted content tracking (archive before removal)
- ✓ Investigation timeline visualization
- ✓ Proof of how evidence was found

### 5. SeFACED - Deep Learning Classification
**URL:** https://github.com/Abdul-Rehman-J/SeFACED
**Dataset:** 32,427 emails (normal, fraud, harassment, suspicious)
**Key Features:**
- Semantic email classification
- Pre-trained on labeled dataset
- Categories: normal, fraud, harassment, suspicious

**What We Can Learn:**
- ✓ ML classification (auto-detect fraud/harassment)
- ✓ Pre-trained models for email types
- ✓ Semantic analysis (not just keyword matching)
- ✓ Labeled dataset approach

### 6. EmailAnalyzer - EML Forensics
**URL:** https://github.com/keraattin/EmailAnalyzer
**Key Features:**
- Extract headers, links, hashes from .eml
- Report generation
- Suspicious content detection

**What We Can Learn:**
- ✓ EML file support (standard email format)
- ✓ Automated report generation
- ✓ Link extraction and analysis
- ✓ Hash-based file tracking

### 7. Mailinspector - Outlook Forensics
**URL:** https://github.com/filipposfwt/Mailinspector
**Key Features:**
- PST file analysis (Outlook)
- Offline mode (no live access needed)
- Attachment extraction
- Suspicious content search

**What We Can Learn:**
- ✓ PST file support (corporate investigations)
- ✓ Offline analysis capability
- ✓ Attachment forensics
- ✓ Live vs offline modes

---

## Common Patterns Across Top Tools

### 1. Evidence Integrity
- **Chain of custody tracking** (every tool emphasizes this)
- **Digital signatures** (beyond basic hashes)
- **Timestamps** (when evidence was captured)
- **Legal admissibility** (designed for court use)

### 2. Multiple Data Sources
- **Email formats:** MBOX, PST, EML, MSG
- **Breach databases:** HaveIBeenPwned, local dumps
- **Social media:** Linked accounts
- **Metadata:** Headers, IP addresses, routing

### 3. Visualization
- **Graphs:** Communication networks, entity relationships
- **Timelines:** Chronological event mapping
- **Dashboards:** Kibana, custom web UIs
- **Reports:** Automated, exportable

### 4. Classification
- **ML models:** Fraud, harassment, phishing detection
- **Semantic analysis:** Context-aware categorization
- **Confidence scores:** Probability of classification
- **Pre-trained datasets:** Labeled email corpora

---

## Gaps in Our L Investigation Framework

### Missing Features (Compared to Top Tools)

1. **Elasticsearch Integration**
   - Current: SQLite FTS5
   - Should add: Elasticsearch option for large corpora (100k+ emails)
   - Benefit: Better performance, Kibana dashboards

2. **MBOX/PST Support**
   - Current: Custom email import
   - Should add: Standard format parsers (MBOX, PST, EML)
   - Benefit: Works with Gmail/Outlook exports

3. **ML Classification**
   - Current: Keyword-based detection
   - Should add: Pre-trained fraud/harassment models
   - Benefit: Automated criminal pattern detection

4. **Investigation Timeline**
   - Current: Basic date sorting
   - Should add: Visual timeline with events
   - Benefit: Chronological investigation view

5. **Breach Correlation**
   - Current: Corpus-only analysis
   - Should add: HaveIBeenPwned API integration
   - Benefit: Link emails to known breaches

6. **Session Recording**
   - Current: No investigation tracking
   - Should add: Log all queries + results (Hunchly-style)
   - Benefit: Reproducible investigations, audit trail

7. **Digital Signatures**
   - Current: SHA256 hashes only
   - Should add: GPG/PGP signatures for evidence
   - Benefit: Cryptographic proof of authenticity

---

## Our Competitive Advantages

### What L Investigation Framework Does Better

1. **The Code - Moral Foundation**
   - ✓ Explicit victim protection rules
   - ✓ Criminology focus (not general OSINT)
   - ✓ Ethical investigation framework
   - **NO OTHER TOOL HAS THIS**

2. **Dual-LLM Pipeline**
   - ✓ Local Phi-3 (privacy) + Claude Haiku (analysis)
   - ✓ Cost-optimized ($33/month budget)
   - ✓ Rate limiting + anti-DDoS
   - **Most tools don't use LLMs**

3. **Clone & Run**
   - ✓ boom.sh single entry point
   - ✓ Multi-OS support (Arch, Debian, Ubuntu, Fedora)
   - ✓ Auto-configuration (PostgreSQL, model download)
   - **Most tools require manual setup**

4. **Social Media Integration**
   - ✓ Templates for Twitter, Reddit, YouTube, TikTok, etc.
   - ✓ Evidence packages ready to share
   - ✓ Viral-ready formatting
   - **NO OTHER TOOL DOES THIS**

5. **Graph Database**
   - ✓ Entity relationship mapping
   - ✓ Connection discovery
   - ✓ Network visualization
   - **Some tools have this, but not with LLM integration**

---

## Immediate Improvements to Implement

### Priority 1 (High Impact, Low Effort)

1. **Add MBOX Import**
   ```bash
   ./scripts/import-mbox.sh /path/to/gmail-export.mbox
   ```
   - Python library: `mailbox`
   - Parse Gmail/Thunderbird exports
   - Import to PostgreSQL

2. **Investigation Session Logging**
   - Log every query to `investigation_sessions` table
   - Track: query, results, timestamp, user
   - Export session as evidence package
   - Legal audit trail

3. **Breach API Integration**
   - HaveIBeenPwned API (free tier)
   - Check emails against known breaches
   - Display breach info in results
   - Add to graph as "breach" nodes

### Priority 2 (High Impact, Medium Effort)

4. **Visual Timeline**
   - D3.js timeline in frontend
   - Show emails chronologically
   - Filter by date range
   - Export as PNG/SVG

5. **ML Classification (Fraud Detection)**
   - Use SeFACED approach
   - Pre-train on labeled dataset
   - Classify: normal, fraud, harassment, suspicious
   - Add confidence scores to emails

6. **Digital Signatures**
   - GPG sign evidence packages
   - Include public key in exports
   - Verify with: `gpg --verify evidence.tar.gz.sig`
   - Cryptographic chain of custody

### Priority 3 (Strategic, Long-term)

7. **Elasticsearch Option**
   - Add as alternative to PostgreSQL
   - For large corpora (100k+ emails)
   - Kibana dashboard integration
   - Keep PostgreSQL as default

8. **PST/EML Support**
   - Python libraries: `libpff`, `eml_parser`
   - Import Outlook exports
   - Extract attachments
   - Metadata preservation

9. **Investigation Replay**
   - Record all queries + results
   - Replay investigation step-by-step
   - Show "how we got here"
   - Legal proof of methodology

---

## Sources (Research)

- [awesome-osint](https://github.com/jivoi/awesome-osint) - Curated OSINT tool list
- [h8mail](https://github.com/khast3x/h8mail) - Email breach hunting
- [comms-analyzer-toolbox](https://github.com/bitsofinfo/comms-analyzer-toolbox) - MBOX corpus analysis
- [SeFACED](https://github.com/Abdul-Rehman-J/SeFACED) - ML email classification
- [EmailAnalyzer](https://github.com/keraattin/EmailAnalyzer) - EML forensics
- [Mailinspector](https://github.com/filipposfwt/Mailinspector) - Outlook forensics
- [Top 10 OSINT Tools](https://usersearch.org/updates/top-10-rated-osint-tools-from-github) - Paliscope, Hunchly
- [Email OSINT Tools](https://github.com/topics/email-osint) - GitHub topic
- [OSINT Tools 2025](https://github.com/JambaAcademy/OSINT) - Latest tools guide

---

## Conclusion

**What Makes Us Unique:**
1. The Code (moral foundation)
2. LLM-powered analysis
3. Social media integration
4. Clone & run deployment

**What We Should Add:**
1. MBOX/PST import (standard formats)
2. Investigation session logging (audit trail)
3. Breach API integration (HaveIBeenPwned)
4. Visual timeline (D3.js)
5. ML classification (fraud detection)
6. Digital signatures (GPG)

**Our Mission:**
> *"Evil must be fought wherever it is found."*
> **— The Code**

This research confirms L Investigation Framework has a unique position: **ethical OSINT with LLM analysis, bound by a moral code, ready for viral sharing.**

No other tool combines:
- Victim protection rules
- Corpus-only analysis (no external knowledge)
- Chain of custody + social media templates
- Production-ready deployment (boom.sh)

**Next step:** Implement Priority 1 features (MBOX import, session logging, breach API).
