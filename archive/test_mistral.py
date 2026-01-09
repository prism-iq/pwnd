#!/usr/bin/env python3
"""Test Mistral parsing"""
import sys
import asyncio
sys.path.insert(0, '/opt/rag')

from app.pipeline import parse_intent_mistral

async def test():
    print("Testing parse_intent_mistral...")
    query = "trump"
    print(f"Query: {query}")

    try:
        result = await parse_intent_mistral(query)
        print(f"Result: {result}")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

asyncio.run(test())
