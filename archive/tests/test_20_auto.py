#!/usr/bin/env python3
"""Test 20 auto-investigation queries with quality analysis"""
import httpx
import time
import json
import sys

def analyze_quality(response: str, sources: int, suggestions: int) -> dict:
    """Analyze response quality"""
    issues = []
    score = 100

    # Check structure
    has_analysis = "ANALYSIS" in response or "analysis" in response.lower()
    has_findings = "FINDING" in response or "finding" in response.lower()
    has_next = "NEXT" in response or "next step" in response.lower()

    if not has_analysis:
        issues.append("missing_analysis")
        score -= 20
    if not has_findings:
        issues.append("missing_findings")
        score -= 15
    if not has_next:
        issues.append("missing_next_step")
        score -= 15

    # Check content
    if len(response) < 200:
        issues.append("too_short")
        score -= 20
    if len(response) > 2000:
        issues.append("too_long")
        score -= 10

    # Check citations
    has_citations = "#" in response and any(c.isdigit() for c in response)
    if not has_citations and sources > 0:
        issues.append("no_citations")
        score -= 15

    # Check sources
    if sources == 0:
        score -= 10  # OK for no-result queries

    # Check suggestions
    if suggestions == 0 and sources > 0:
        issues.append("no_suggestions")
        score -= 10

    quality = "GOOD" if score >= 80 else "OK" if score >= 60 else "POOR"

    return {
        "score": max(0, score),
        "quality": quality,
        "issues": issues,
        "has_analysis": has_analysis,
        "has_findings": has_findings,
        "has_next": has_next,
        "has_citations": has_citations
    }

def run_query(query: str, conv_id: str) -> dict:
    """Run single query and collect metrics"""
    start = time.time()
    response_text = ""
    sources = []
    suggestions = []
    patterns = []
    evidence = None

    try:
        with httpx.stream("GET",
            f"http://localhost:8002/api/ask?q={query}&conversation_id={conv_id}",
            timeout=60) as r:
            for line in r.iter_lines():
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        if data.get("type") == "chunk":
                            response_text += data.get("text", "")
                        elif data.get("type") == "sources":
                            sources = data.get("ids", [])
                        elif data.get("type") == "suggestions":
                            suggestions = data.get("queries", [])
                        elif data.get("type") == "thinking" and "PATTERNS" in data.get("text", ""):
                            patterns.append(data.get("text", "").strip())
                        elif data.get("type") == "done":
                            evidence = data.get("evidence", {})
                    except:
                        pass
    except Exception as e:
        return {"error": str(e), "time": time.time() - start}

    elapsed = time.time() - start
    quality = analyze_quality(response_text, len(sources), len(suggestions))

    return {
        "query": query,
        "time": round(elapsed, 2),
        "response": response_text,
        "response_len": len(response_text),
        "sources": len(sources),
        "suggestions": suggestions,
        "patterns": patterns,
        "evidence_hash": evidence.get("hash", "") if evidence else "",
        "quality": quality
    }

QUERIES = [
    "epstein flight logs",
    "maxwell recruitment",
    "virgin islands property",
    "bank transfers offshore",
    "private jet passengers",
    "foundation donations",
    "settlement agreements",
    "witness testimony",
    "court documents sealed",
    "acosta plea deal",
    "model agency connections",
    "palm beach mansion",
    "new york townhouse",
    "little st james island",
    "bill clinton visits",
    "prince andrew allegations",
    "victims compensation fund",
    "fbi investigation",
    "media coverage suppression",
    "legal defense team"
]

def main():
    print("=" * 70)
    print("L Investigation - 20 Query Auto Test with Quality Analysis")
    print("=" * 70)

    conv_id = f"auto20_{int(time.time())}"
    results = []
    poor_queries = []

    for i, query in enumerate(QUERIES):
        print(f"\n[{i+1}/20] {query}")
        result = run_query(query, conv_id)
        results.append(result)

        if "error" in result:
            print(f"  ERROR: {result['error']}")
            continue

        q = result["quality"]
        print(f"  Time: {result['time']}s | Sources: {result['sources']} | Score: {q['score']}")
        print(f"  Quality: {q['quality']} | Response: {result['response_len']} chars")

        if result["patterns"]:
            print(f"  Patterns: {result['patterns']}")

        if q["issues"]:
            print(f"  Issues: {', '.join(q['issues'])}")

        if q["quality"] == "POOR":
            poor_queries.append({"query": query, "issues": q["issues"], "response": result["response"][:200]})

        # Show snippet of response
        snippet = result["response"][:150].replace("\n", " ")
        print(f"  Preview: {snippet}...")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    times = [r["time"] for r in results if "error" not in r]
    scores = [r["quality"]["score"] for r in results if "error" not in r]
    qualities = [r["quality"]["quality"] for r in results if "error" not in r]

    good = qualities.count("GOOD")
    ok = qualities.count("OK")
    poor = qualities.count("POOR")

    print(f"Total queries: {len(results)}")
    print(f"Avg time: {sum(times)/len(times):.1f}s")
    print(f"Avg score: {sum(scores)/len(scores):.0f}/100")
    print(f"Quality: {good} GOOD, {ok} OK, {poor} POOR")

    if poor_queries:
        print(f"\nPOOR QUERIES TO FIX:")
        for pq in poor_queries:
            print(f"  - {pq['query']}: {pq['issues']}")
            print(f"    Response: {pq['response']}...")

    # Return exit code based on quality
    if good >= 18:
        print("\n*** TARGET MET: 18+ GOOD ***")
        return 0
    else:
        print(f"\n*** NEEDS IMPROVEMENT: {good}/18 GOOD ***")
        return 1

if __name__ == "__main__":
    sys.exit(main())
