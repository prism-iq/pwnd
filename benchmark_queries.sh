#!/bin/bash
# Benchmark 5 test queries with Phi-3-Mini

echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║                                                                  ║"
echo "║  BENCHMARK: 5 TEST QUERIES (Phi-3-Mini)                         ║"
echo "║                                                                  ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""

QUERIES=(
    "epstein"
    "who knows trump"
    "emails from 2004"
    "virgin islands"
    "qui est jeffrey epstein"
)

TOTAL_TIME=0
COUNT=0

for query in "${QUERIES[@]}"; do
    COUNT=$((COUNT + 1))
    echo "════════════════════════════════════════════════════════════════════"
    echo "Query $COUNT/5: $query"
    echo "════════════════════════════════════════════════════════════════════"

    START=$(date +%s.%N)

    # Call API and capture response
    response=$(timeout 30 curl -s "https://pwnd.icu/api/ask?q=$(echo "$query" | jq -sRr @uri)" 2>&1)

    END=$(date +%s.%N)
    DURATION=$(echo "$END - $START" | bc)
    TOTAL_TIME=$(echo "$TOTAL_TIME + $DURATION" | bc)

    echo "Time: ${DURATION}s"

    # Check if response contains results
    if echo "$response" | grep -q '"type": "sources"'; then
        sources=$(echo "$response" | grep '"type": "sources"' | head -1)
        echo "Status: ✓ Results found"
        echo "Sources: $sources"
    elif echo "$response" | grep -q "couldn't find relevant documents"; then
        echo "Status: ✓ No results (expected)"
    else
        echo "Status: ⚠ Check response"
    fi

    echo ""
    sleep 2
done

AVG_TIME=$(echo "scale=2; $TOTAL_TIME / $COUNT" | bc)

echo "════════════════════════════════════════════════════════════════════"
echo "  BENCHMARK RESULTS"
echo "════════════════════════════════════════════════════════════════════"
echo "Total queries: $COUNT"
echo "Total time: ${TOTAL_TIME}s"
echo "Average time: ${AVG_TIME}s"
echo ""

if (( $(echo "$AVG_TIME < 8" | bc -l) )); then
    echo "✅ PASS: Average response time < 8s target"
else
    echo "❌ FAIL: Average response time > 8s target"
fi
