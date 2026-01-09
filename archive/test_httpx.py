#!/usr/bin/env python3
"""Test httpx async client"""
import asyncio
import httpx

async def test():
    print("Testing httpx.AsyncClient...")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            print("Sending request...")
            response = await client.post(
                "http://127.0.0.1:8001/generate",
                json={
                    "prompt": "test",
                    "max_tokens": 10,
                    "temperature": 0.0
                }
            )
            print(f"Got response: {response.status_code}")
            print(f"Body: {response.text[:100]}")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

asyncio.run(test())
