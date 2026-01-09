#!/usr/bin/env python3
"""Test query execution"""
import sys
sys.path.insert(0, '/opt/rag')

from app.pipeline import execute_sql_by_intent

intent = {
    "intent": "search",
    "entities": ["trump"],
    "filters": {}
}

print("Testing execute_sql_by_intent...")
print(f"Intent: {intent}")

try:
    results = execute_sql_by_intent(intent, limit=10)
    print(f"\nGot {len(results)} results:")
    for i, result in enumerate(results[:3]):
        print(f"{i+1}. {result.get('type', 'N/A')}: {result.get('name', 'N/A')[:50]}")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
