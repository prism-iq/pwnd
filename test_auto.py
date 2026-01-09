#!/usr/bin/env python3
"""Test auto-investigation with 20 questions"""
import httpx
import time
import json
import sys

QUERIES = [
    "epstein",
    "maxwell",
    "virgin islands",
    "flight records",
    "bank transfers",
    "giuffre",
    "palm beach",
    "foundation payments",
    "legal documents",
    "private jet",
    "settlement",
    "witness",
    "property records",
    "known associates",
    "travel dates",
    "deposition",
    "court filing",
    "acosta",
    "model agency",
    "recruitment"
]

def test_query(q: str, conv_id: str) -> dict:
    """Test single query, return timing and quality metrics"""
    start = time.time()
    chunks = []
    sources = []
    suggestions = []

    try:
        with httpx.stream("GET", f"http://localhost:8002/api/ask?q={q}&conversation_id={conv_id}", timeout=60) as r:
            for line in r.iter_lines():
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        if data.get("type") == "chunk":
                            chunks.append(data.get("text", ""))
                        elif data.get("type") == "sources":
                            sources = data.get("ids", [])
                        elif data.get("type") == "suggestions":
                            suggestions = data.get("queries", [])
                    except:
                        pass
    except Exception as e:
        return {"error": str(e), "time": time.time() - start}

    elapsed = time.time() - start
    response = "".join(chunks)

    return {
        "query": q,
        "time": round(elapsed, 2),
        "response_len": len(response),
        "sources_count": len(sources),
        "suggestions_count": len(suggestions),
        "has_analysis": "ANALYSIS" in response or "findings" in response.lower(),
        "has_next_step": "next" in response.lower() or "suggest" in response.lower(),
    }

def main():
    print("=" * 60)
    print("L Investigation - 20 Question Auto Test")
    print("=" * 60)

    conv_id = f"test_{int(time.time())}"
    results = []
    total_start = time.time()

    for i, q in enumerate(QUERIES):
        print(f"\n[{i+1}/20] Testing: {q}")
        result = test_query(q, conv_id)
        results.append(result)

        if "error" in result:
            print(f"  ERROR: {result['error']}")
        else:
            print(f"  Time: {result['time']}s | Sources: {result['sources_count']} | Suggestions: {result['suggestions_count']}")
            quality = "GOOD" if result['has_analysis'] and result['has_next_step'] else "OK" if result['response_len'] > 100 else "POOR"
            print(f"  Quality: {quality} ({result['response_len']} chars)")

    total_time = time.time() - total_start

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    times = [r['time'] for r in results if 'error' not in r]
    good = sum(1 for r in results if r.get('has_analysis') and r.get('has_next_step'))
    ok = sum(1 for r in results if r.get('response_len', 0) > 100)

    print(f"Total time: {total_time:.1f}s")
    print(f"Avg per query: {sum(times)/len(times):.1f}s")
    print(f"Min/Max: {min(times):.1f}s / {max(times):.1f}s")
    print(f"Quality: {good}/20 GOOD, {ok}/20 OK")
    print(f"Errors: {sum(1 for r in results if 'error' in r)}")

    # Target: <10s avg, 18+ good quality
    if sum(times)/len(times) < 10 and good >= 18:
        print("\n*** TARGET MET ***")
        return 0
    else:
        print("\n*** NEEDS IMPROVEMENT ***")
        return 1

if __name__ == "__main__":
    sys.exit(main())
