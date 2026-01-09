#!/bin/bash
# Monitor the 50-query test progress

echo "Monitoring 50-query test progress..."
echo "Press Ctrl+C to exit (test will continue in background)"
echo ""

while true; do
    clear
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║     50 Query Test - Live Monitoring                           ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""

    # Check if process is running
    if ps aux | grep -q "[p]ython3 test_50_queries.py"; then
        echo "Status: ✅ RUNNING"

        # Get process info
        pid=$(ps aux | grep "[p]ython3 test_50_queries.py" | awk '{print $2}')
        cpu=$(ps aux | grep "[p]ython3 test_50_queries.py" | awk '{print $3}')
        mem=$(ps aux | grep "[p]ython3 test_50_queries.py" | awk '{print $4}')
        runtime=$(ps -p $pid -o etime= 2>/dev/null | tr -d ' ')

        echo "PID: $pid"
        echo "CPU: ${cpu}%"
        echo "Memory: ${mem}%"
        echo "Runtime: $runtime"
    else
        echo "Status: ❌ NOT RUNNING (completed or failed)"
    fi

    echo ""
    echo "─────────────────────────────────────────────────────────────────"
    echo "Latest Output (last 30 lines):"
    echo "─────────────────────────────────────────────────────────────────"

    # Show latest output
    if [ -f /tmp/claude/-opt-rag/tasks/b4bf4fe.output ]; then
        tail -30 /tmp/claude/-opt-rag/tasks/b4bf4fe.output
    else
        echo "No output file yet..."
    fi

    echo ""
    echo "─────────────────────────────────────────────────────────────────"

    # Check for result files
    if [ -f /opt/rag/test_results_50queries.txt ]; then
        echo "✅ Results available: /opt/rag/test_results_50queries.txt"
        echo ""
        echo "Violations detected:"
        grep "Total violations:" /opt/rag/test_results_50queries.txt || echo "  (report not complete yet)"
    else
        echo "⏳ Waiting for results... (test still in progress)"
    fi

    echo ""
    echo "Next update in 10 seconds... (Ctrl+C to exit monitor)"
    sleep 10
done
