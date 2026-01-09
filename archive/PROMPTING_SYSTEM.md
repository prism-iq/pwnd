# Optimized Prompting System

## Core Identity (1 file, loaded first)
**IDENTITY.md** - 15 lines
- Role: Detective OSINT criminology expert
- Focus: pedocriminality, murders, violence, trafficking
- Tone: Factual, direct, no fluff
- Method: Facts only, sources [#ID], no external knowledge

## Technical Constraints (1 file, critical)
**MASTER_CONTEXT.md** - Top 100 lines only
- Security rules (127.0.0.1, parameterized SQL)
- Server specs (i7-6700, 64GB RAM, Arch Linux)
- File structure
- Python heredoc fix (NL = chr(10))

## Current Build State (auto-generated each iteration)
**BUILD_LATEST.md** - Auto-regenerated
- Last changes applied
- Services status
- API endpoints working/broken
- Cost tracking (30€/mois budget)
- Next iteration goals

## Architecture (1 file, reference only)
**ARCHITECTURE_MAP.md**
- File communication (imports)
- Module responsibilities
- Current issues
- Read ONLY when debugging imports

## Prompting Rules

### ITERATION CYCLE:
1. **Read (3 files max):**
   - IDENTITY.md (15 lines)
   - MASTER_CONTEXT.md (100 lines)
   - BUILD_LATEST.md (auto-gen from last iteration)

2. **Analyze:**
   - Code changes needed
   - DB schema changes
   - New features
   - Bugs to fix

3. **Generate (1 file):**
   - BUILD_ITERATION_XX.md with:
     - Changes applied
     - Bugs fixed
     - Tests run
     - Next goals
   - Overwrite BUILD_LATEST.md

4. **Apply:**
   - Code changes
   - Restart services
   - Test with curl
   - Debug logs if error

5. **Commit:**
   - git add -A
   - git commit (descriptive message)

### ANTI-PATTERNS (STOP DOING):
❌ Reading 20+ .md files every iteration
❌ Generating redundant documentation
❌ Verbose explanations
❌ Asking permission ("would you like me to...")
❌ Reading full files when grep would work

### OPTIMIZED PATTERNS (START DOING):
✅ Read ONLY 3 core files per iteration
✅ Auto-generate BUILD_LATEST.md from changes
✅ grep/head/tail for quick checks
✅ Test immediately after code change
✅ One iteration = one focused improvement

## File Hierarchy (Priority Order)

### P0: Critical (Read First)
1. IDENTITY.md (15 lines - WHO I AM)
2. MASTER_CONTEXT.md (100 lines - CONSTRAINTS)
3. BUILD_LATEST.md (auto-gen - CURRENT STATE)

### P1: Reference (Read When Needed)
- ARCHITECTURE_MAP.md (import debugging)
- ANTI_DDOS_SPEC.md (rate limiting)
- DETECTIVE_METHODOLOGY.md (investigation workflow)

### P2: Historical (Archive Only)
- BUILD_ITERATION_01.md, 02.md, etc.
- OPTIMIZATION_APPLIED.md
- Old debug files

## Auto-Generation Template

### BUILD_LATEST.md Structure:
```markdown
# Build State - [TIMESTAMP]

## Services
- l-api: [ACTIVE/FAILED]
- l-llm: [ACTIVE/FAILED]
- caddy: [ACTIVE/FAILED]

## Last Changes
1. [Change 1]
2. [Change 2]

## Tests Passed
- [x] Health check
- [x] Stats endpoint
- [ ] Query processing

## Current Issues
- [Issue 1]
- [Issue 2]

## Next Iteration
1. [Goal 1]
2. [Goal 2]

## Cost Tracking (30€/mois)
- Queries today: X/200
- Cost today: $X.XX
- Budget remaining: $XX.XX

## Quick Debug
```bash
# Test API
curl http://localhost:8002/api/health

# Check logs if error
journalctl -u l-api -n 20 --no-pager | grep Error
```
```

## Iteration Speed Target
- Read phase: <30s (3 files)
- Analysis: <1min (code + DB check)
- Generate: <1min (BUILD_LATEST.md)
- Apply: <2min (code + test)
- Total: <5min per iteration

## Metrics
- Files read per iteration: 3 max
- Files generated per iteration: 1-2 max
- Lines written per iteration: <300
- Curl tests per iteration: 2-3 min

## Self-Improvement Loop
Each iteration learns from:
- Previous BUILD_ITERATION_XX.md (what worked)
- Error logs (what failed)
- Code patterns (what's clean)
- DB schema (what's efficient)

Append learnings to BUILD_LATEST.md → Next iteration reads it → Improves.
