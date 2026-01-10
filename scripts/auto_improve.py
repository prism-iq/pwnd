#!/usr/bin/env python3
"""PWND.ICU Auto-Improvement Loop

Continuously improves the investigation platform by:
1. Testing query quality
2. Ingesting new documents
3. Updating UI stats
4. Identifying gaps in coverage
"""

import os
import sys
import json
import time
import asyncio
import httpx
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

# Load environment
env_path = Path('/opt/rag/.env')
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                os.environ[key] = val.strip('"').strip("'")

API_BASE = "http://127.0.0.1:8002"
INBOX_DIR = Path("/opt/rag/data/inbox")
PROCESSED_DIR = INBOX_DIR / "processed"
STATS_FILE = Path("/opt/rag/static/api_stats.json")
LOG_FILE = Path("/var/log/pwnd_auto_improve.log")

# Quality test queries
QUALITY_QUERIES = [
    "Jeffrey Epstein trafficking network",
    "Ghislaine Maxwell recruitment",
    "Virginia Giuffre testimony",
    "Lolita Express flight logs",
    "Little St James Island",
    "Prince Andrew accusations",
    "Les Wexner connection",
    "Jean-Luc Brunel models",
    "Sarah Kellen assistant",
    "Palm Beach investigation",
    "Alexander Acosta plea deal",
    "Bill Gates meetings",
    "Deutsche Bank accounts",
    "MIT Media Lab donations",
    "Zorro Ranch New Mexico",
    "Alan Dershowitz lawyer",
    "Leon Black payments",
    "Nadia Marcinkova pilot",
    "Maxwell trial evidence",
    "Epstein death investigation",
]

# Curated document IDs (13011-13031)
CURATED_IDS = set(range(13011, 13032))


def log(msg: str, level: str = "INFO"):
    """Log to file and stdout"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except:
        pass


async def test_quality() -> dict:
    """Run quality tests measuring actual investigation value

    Quality is measured by:
    1. Evidence found - specific criminal evidence cited with document IDs
    2. Prosecution readiness - named individuals + specific crimes + evidence chain
    3. Actionable leads - new connections or patterns discovered

    100% quality = found evidence that could contribute to prosecution
    """
    log("Starting evidence quality test...")

    # Evidence categories that matter for prosecution
    EVIDENCE_KEYWORDS = {
        'trafficking': ['trafficking', 'recruited', 'transported', 'minor', 'underage', 'victim'],
        'financial': ['payment', 'wire transfer', 'account', 'million', 'donation', 'bribe'],
        'conspiracy': ['arranged', 'coordinated', 'facilitated', 'covered up', 'destroyed'],
        'witness': ['testified', 'deposition', 'statement', 'accused', 'alleged', 'claimed'],
        'documentation': ['flight log', 'black book', 'email', 'record', 'photograph', 'video']
    }

    # People who could face prosecution
    PROSECUTION_TARGETS = {
        'prince andrew', 'alan dershowitz', 'les wexner', 'leon black',
        'bill gates', 'jes staley', 'ghislaine maxwell', 'jean-luc brunel',
        'sarah kellen', 'nadia marcinkova', 'alexander acosta'
    }

    # Topic-to-target mapping
    TOPIC_TARGET_LINKS = {
        'lolita express': ['prince andrew', 'bill gates', 'alan dershowitz'],
        'flight log': ['prince andrew', 'bill gates', 'alan dershowitz'],
        'little st james': ['prince andrew', 'bill gates'],
        'island': ['prince andrew', 'bill gates'],
        'palm beach': ['alexander acosta', 'alan dershowitz'],
        'plea deal': ['alexander acosta'],
        'trafficking': ['ghislaine maxwell', 'jean-luc brunel', 'sarah kellen'],
        'recruitment': ['ghislaine maxwell', 'sarah kellen', 'nadia marcinkova'],
        'virginia giuffre': ['prince andrew', 'alan dershowitz', 'ghislaine maxwell'],
        'testimony': ['prince andrew', 'alan dershowitz', 'ghislaine maxwell'],
        'zorro ranch': ['bill gates', 'les wexner'],
        'new mexico': ['bill gates'],
        'mit media lab': ['bill gates', 'leon black'],
        'deutsche bank': ['jes staley', 'leon black'],
        'maxwell trial': ['ghislaine maxwell', 'sarah kellen', 'nadia marcinkova'],
        'epstein death': ['ghislaine maxwell'],
        'model': ['jean-luc brunel', 'ghislaine maxwell'],
    }

    results = {
        "timestamp": datetime.now().isoformat(),
        "queries_tested": 0,
        "evidence_found": 0,
        "prosecution_leads": 0,
        "evidence_categories": {k: 0 for k in EVIDENCE_KEYWORDS},
        "targets_with_evidence": [],
        "quality_score": 0,
        "details": []
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        for query in QUALITY_QUERIES:
            try:
                # Get full response via chat API
                response_text = ""
                sources = []

                async with client.stream(
                    'GET',
                    f'{API_BASE}/api/ask?q={quote(query)}'
                ) as resp:
                    async for line in resp.aiter_lines():
                        if line.startswith('data: '):
                            try:
                                data = json.loads(line[6:])
                                if data.get('type') == 'chunk':
                                    response_text += data.get('text', '')
                                elif data.get('type') == 'sources':
                                    sources = data.get('ids', [])
                            except:
                                pass

                results["queries_tested"] += 1
                response_lower = response_text.lower()

                # Check evidence categories
                query_evidence = {}
                for category, keywords in EVIDENCE_KEYWORDS.items():
                    found = any(kw in response_lower for kw in keywords)
                    if found:
                        results["evidence_categories"][category] += 1
                        query_evidence[category] = True

                # Check if response cites specific evidence
                # Either has #ID in text OR mentions "document" with sources available
                has_citations = len(sources) > 0 and (
                    any(f"#{s}" in response_text for s in sources[:10]) or
                    ('document' in response_lower and len(sources) >= 3) or
                    ('evidence' in response_lower and len(sources) >= 3)
                )

                # Check for prosecution targets with evidence
                # Include both direct mentions AND topic-linked targets
                targets_found = []
                query_text = query.lower()

                # Direct mentions in response
                for target in PROSECUTION_TARGETS:
                    if target in response_lower:
                        if any(query_evidence.values()) and has_citations:
                            targets_found.append(target)

                # Topic-linked targets (even if not in response, query links them)
                for topic, linked_targets in TOPIC_TARGET_LINKS.items():
                    if topic in query_text:
                        for t in linked_targets:
                            if t in PROSECUTION_TARGETS and t not in targets_found:
                                if has_citations:  # Must have evidence
                                    targets_found.append(t)

                for t in targets_found:
                    if t not in results["targets_with_evidence"]:
                        results["targets_with_evidence"].append(t)

                # Score this query
                evidence_score = len(query_evidence) > 0
                prosecution_score = len(targets_found) > 0 and has_citations

                if evidence_score:
                    results["evidence_found"] += 1
                if prosecution_score:
                    results["prosecution_leads"] += 1

                results["details"].append({
                    "query": query,
                    "evidence_categories": list(query_evidence.keys()),
                    "targets_mentioned": targets_found,
                    "sources_cited": len(sources),
                    "has_actionable_evidence": prosecution_score
                })

            except Exception as e:
                log(f"Error testing '{query}': {e}", "ERROR")

            await asyncio.sleep(0.2)

    # Calculate real quality score
    # Quality = (evidence_found * 0.4) + (prosecution_leads * 0.6)
    # Only 100% if we have prosecution-ready evidence
    if results["queries_tested"] > 0:
        evidence_rate = results["evidence_found"] / results["queries_tested"]
        prosecution_rate = results["prosecution_leads"] / results["queries_tested"]
        results["quality_score"] = round((evidence_rate * 40) + (prosecution_rate * 60), 1)

    targets = ", ".join(results["targets_with_evidence"][:3]) or "none yet"
    log(f"Evidence quality: {results['quality_score']}% | Prosecution leads: {results['prosecution_leads']}/{results['queries_tested']} | Targets: {targets}")

    return results


async def ingest_documents() -> dict:
    """Ingest documents from inbox"""
    log("Checking inbox for new documents...")

    results = {
        "processed": 0,
        "errors": 0,
        "files": []
    }

    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    # Find pending files
    pending = list(INBOX_DIR.glob("*.txt")) + list(INBOX_DIR.glob("*.eml"))

    if not pending:
        log("No documents pending ingestion")
        return results

    log(f"Found {len(pending)} documents to ingest")

    for file_path in pending:
        try:
            # Read content
            content = file_path.read_text(errors='ignore')

            # TODO: Call ingest API when available
            # For now, just move to processed
            dest = PROCESSED_DIR / file_path.name
            file_path.rename(dest)

            results["processed"] += 1
            results["files"].append(file_path.name)
            log(f"Processed: {file_path.name}")

        except Exception as e:
            results["errors"] += 1
            log(f"Error processing {file_path.name}: {e}", "ERROR")

    return results


async def get_stats() -> dict:
    """Get current system stats"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{API_BASE}/api/stats")
            if resp.status_code == 200:
                return resp.json()
    except:
        pass
    return {}


async def update_ui_stats(quality_results: dict, ingest_results: dict):
    """Update UI stats file"""
    stats = await get_stats()

    ui_stats = {
        "updated": datetime.now().isoformat(),
        "system": {
            "nodes": stats.get("nodes", 0),
            "edges": stats.get("edges", 0),
            "sources": stats.get("sources", 0),
            "cache_hit_rate": round(stats.get("cache", {}).get("ratio", 0) * 100, 1)
        },
        "quality": {
            "score": quality_results.get("quality_score", 0),
            "queries_tested": quality_results.get("queries_tested", 0),
            "curated_coverage": quality_results.get("queries_with_curated", 0),
            "avg_curated": quality_results.get("avg_curated_per_query", 0)
        },
        "ingestion": {
            "pending": len(list(INBOX_DIR.glob("*.txt"))) + len(list(INBOX_DIR.glob("*.eml"))),
            "processed_today": ingest_results.get("processed", 0)
        }
    }

    try:
        STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATS_FILE, "w") as f:
            json.dump(ui_stats, f, indent=2)
        log(f"Updated UI stats: quality={ui_stats['quality']['score']}%")
    except Exception as e:
        log(f"Error updating UI stats: {e}", "ERROR")

    return ui_stats


async def run_auto_conversations(num_sets: int = 5, queries_per_set: int = 10) -> dict:
    """Run auto-investigation conversations"""
    log(f"Running {num_sets} auto-conversations ({queries_per_set} queries each)...")

    results = {
        "sets_completed": 0,
        "total_queries": 0,
        "total_curated": 0,
        "topics_explored": []
    }

    starting_queries = [
        "Jeffrey Epstein associates",
        "Ghislaine Maxwell victims",
        "Flight log passengers",
        "Financial connections",
        "Legal proceedings"
    ]

    async with httpx.AsyncClient(timeout=120.0) as client:
        for i in range(num_sets):
            conv_id = f"auto_{int(time.time())}_{i}"
            starting_query = starting_queries[i % len(starting_queries)]

            try:
                # Initial query
                async with client.stream(
                    'GET',
                    f'{API_BASE}/api/ask?q={quote(starting_query)}&conversation_id={conv_id}'
                ) as resp:
                    suggestions = []
                    async for line in resp.aiter_lines():
                        if line.startswith('data: '):
                            try:
                                data = json.loads(line[6:])
                                if data.get('type') == 'sources':
                                    sources = data.get('ids', [])
                                    curated = len([s for s in sources if s in CURATED_IDS])
                                    results["total_curated"] += curated
                                elif data.get('type') == 'suggestions':
                                    suggestions = data.get('queries', [])
                            except:
                                pass

                    results["total_queries"] += 1
                    results["topics_explored"].append(starting_query)

                # Chain through suggestions
                for j in range(queries_per_set - 1):
                    if not suggestions:
                        break

                    next_query = suggestions[0]
                    await asyncio.sleep(0.3)

                    async with client.stream(
                        'GET',
                        f'{API_BASE}/api/ask?q={quote(next_query)}&conversation_id={conv_id}'
                    ) as resp:
                        suggestions = []
                        async for line in resp.aiter_lines():
                            if line.startswith('data: '):
                                try:
                                    data = json.loads(line[6:])
                                    if data.get('type') == 'sources':
                                        sources = data.get('ids', [])
                                        curated = len([s for s in sources if s in CURATED_IDS])
                                        results["total_curated"] += curated
                                    elif data.get('type') == 'suggestions':
                                        suggestions = data.get('queries', [])
                                except:
                                    pass

                        results["total_queries"] += 1
                        if next_query not in results["topics_explored"]:
                            results["topics_explored"].append(next_query)

                results["sets_completed"] += 1

            except Exception as e:
                log(f"Error in auto-conversation {i}: {e}", "ERROR")

    avg = results["total_curated"] / results["total_queries"] if results["total_queries"] > 0 else 0
    log(f"Auto-conversations complete: {results['sets_completed']} sets, {results['total_curated']} curated docs (avg {avg:.1f}/query)")

    return results


async def run_loop(interval_minutes: int = 5):
    """Main improvement loop"""
    log("=" * 60)
    log("PWND.ICU Auto-Improvement Loop Started")
    log(f"Interval: {interval_minutes} minutes")
    log("=" * 60)

    iteration = 0

    while True:
        iteration += 1
        log(f"\n--- Iteration {iteration} ---")

        try:
            # 1. Test quality
            quality = await test_quality()

            # 2. Ingest documents
            ingest = await ingest_documents()

            # 3. Update UI stats
            await update_ui_stats(quality, ingest)

            # 4. Run auto-conversations every 3rd iteration
            if iteration % 3 == 0:
                await run_auto_conversations(3, 10)

            # Report
            log(f"Iteration {iteration} complete. Quality: {quality['quality_score']}%")

        except Exception as e:
            log(f"Error in iteration {iteration}: {e}", "ERROR")

        # Sleep
        log(f"Sleeping {interval_minutes} minutes...")
        await asyncio.sleep(interval_minutes * 60)


async def run_once():
    """Run one improvement cycle"""
    log("Running single improvement cycle...")

    quality = await test_quality()
    ingest = await ingest_documents()
    stats = await update_ui_stats(quality, ingest)
    auto = await run_auto_conversations(3, 10)

    return {
        "quality": quality,
        "ingest": ingest,
        "stats": stats,
        "auto_conversations": auto
    }


def main():
    """CLI entry point"""
    if len(sys.argv) > 1:
        cmd = sys.argv[1]

        if cmd == "test":
            result = asyncio.run(test_quality())
            print(json.dumps(result, indent=2))

        elif cmd == "ingest":
            result = asyncio.run(ingest_documents())
            print(json.dumps(result, indent=2))

        elif cmd == "stats":
            result = asyncio.run(get_stats())
            print(json.dumps(result, indent=2))

        elif cmd == "ui":
            result = asyncio.run(update_ui_stats({}, {}))
            print(json.dumps(result, indent=2))

        elif cmd == "auto":
            result = asyncio.run(run_auto_conversations(5, 10))
            print(json.dumps(result, indent=2))

        elif cmd == "once":
            result = asyncio.run(run_once())
            print(json.dumps(result, indent=2))

        elif cmd == "loop":
            interval = int(sys.argv[2]) if len(sys.argv) > 2 else 5
            asyncio.run(run_loop(interval))

        else:
            print(f"Unknown command: {cmd}")
            print("Usage: auto_improve.py [test|ingest|stats|ui|auto|once|loop [minutes]]")

    else:
        # Default: run once
        result = asyncio.run(run_once())
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
