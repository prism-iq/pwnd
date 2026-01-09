#!/bin/bash
# Wait for test completion and show results

echo "Waiting for 50-query test to complete..."
echo ""

while true; do
    # Check if results file exists
    if [ -f /opt/rag/test_results_50queries.txt ]; then
        echo "✅ Test completed! Showing results..."
        echo ""
        cat /opt/rag/test_results_50queries.txt
        exit 0
    fi

    # Show current progress
    current_query=$(grep -o "Query [0-9]*/50" /opt/rag/test_output_live.txt 2>/dev/null | tail -1)
    if [ -n "$current_query" ]; then
        echo "[$(date +%H:%M:%S)] Progress: $current_query"
    fi

    # Wait 1 minute between checks
    sleep 60
done
