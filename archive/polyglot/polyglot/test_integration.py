#!/usr/bin/env python3
"""
L Investigation - Full Polyglot Integration Test
Tests all organs working together
"""

import time
import json
import ctypes
import httpx
from concurrent.futures import ThreadPoolExecutor, as_completed

# =============================================================================
# Configuration
# =============================================================================

ORGANS = {
    'brain': 'http://127.0.0.1:8085',
    'cells': 'http://127.0.0.1:9001',
    'veins': 'http://127.0.0.1:8002',
}

SYNAPSES_PATH = '/opt/rag/polyglot/cpp-core/lib/liblsearch.so'

# =============================================================================
# Test Functions
# =============================================================================

def test_synapses():
    """Test C++ synapses (FFI bridge)"""
    print("\n[SYNAPSES] Testing C++ FFI bridge...")
    start = time.time()

    try:
        lib = ctypes.CDLL(SYNAPSES_PATH)
        lib.l_synapse_version.restype = ctypes.c_char_p
        lib.l_synapse_hash.restype = ctypes.c_uint64
        lib.l_synapse_hash.argtypes = [ctypes.c_char_p]
        lib.l_synapse_similarity.restype = ctypes.c_float
        lib.l_synapse_similarity.argtypes = [ctypes.c_char_p, ctypes.c_char_p]

        version = lib.l_synapse_version().decode()
        h = lib.l_synapse_hash(b"test")
        sim = lib.l_synapse_similarity(b"hello world", b"hello there")

        elapsed = (time.time() - start) * 1000
        print(f"  Version: {version}")
        print(f"  Hash: {h}")
        print(f"  Similarity: {sim:.2%}")
        print(f"  Time: {elapsed:.2f}ms")
        return True, elapsed
    except Exception as e:
        print(f"  ERROR: {e}")
        return False, 0

def test_brain():
    """Test Go brain (decision making)"""
    print("\n[BRAIN] Testing Go gateway...")
    start = time.time()

    try:
        # Health check
        r = httpx.get(f"{ORGANS['brain']}/health", timeout=5)
        health = r.json()

        # Strategic analysis
        r = httpx.post(
            f"{ORGANS['brain']}/analyze",
            json={"query": "Who committed fraud at Enron?"},
            timeout=5
        )
        analysis = r.json()

        elapsed = (time.time() - start) * 1000
        print(f"  Status: {health['status']}")
        print(f"  Uptime: {health['uptime']:.0f}s")
        print(f"  Strategy: {analysis['priority']} priority")
        print(f"  Terms: {analysis['search_terms'][:3]}...")
        print(f"  Time: {elapsed:.2f}ms")
        return True, elapsed
    except Exception as e:
        print(f"  ERROR: {e}")
        return False, 0

def test_cells():
    """Test Rust cells (extraction)"""
    print("\n[CELLS] Testing Rust extractor...")
    start = time.time()

    try:
        r = httpx.post(
            f"{ORGANS['cells']}/extract",
            json={"text": "John Smith transferred $5,000,000 to Bank of America on 2024-03-15. Contact: john@enron.com"},
            timeout=5
        )
        data = r.json()

        elapsed = (time.time() - start) * 1000
        print(f"  Persons: {len(data.get('persons', []))}")
        print(f"  Dates: {len(data.get('dates', []))}")
        print(f"  Emails: {len(data.get('emails', []))}")
        print(f"  Processing: {data.get('processing_time_ms', 0)}ms (Rust)")
        print(f"  Total time: {elapsed:.2f}ms")
        return True, elapsed
    except Exception as e:
        print(f"  ERROR: {e}")
        return False, 0

def test_full_investigation():
    """Test full investigation flow through brain"""
    print("\n[FULL] Testing complete investigation...")
    start = time.time()

    try:
        r = httpx.post(
            f"{ORGANS['brain']}/investigate",
            json={
                "query": "Find all financial transfers related to fraud",
                "sessionId": "test-session-001"
            },
            timeout=30
        )
        data = r.json()

        elapsed = (time.time() - start) * 1000
        print(f"  Success: {data.get('success', False)}")
        print(f"  Strategy: {data.get('strategy', {}).get('priority', 'unknown')}")

        entities = data.get('entities', {})
        if entities and not entities.get('fallback'):
            print(f"  Entities extracted: Yes")
        else:
            print(f"  Entities: Fallback mode")

        print(f"  Total time: {elapsed:.2f}ms")
        return True, elapsed
    except Exception as e:
        print(f"  ERROR: {e}")
        return False, 0

def test_parallel_load():
    """Test parallel requests to all organs"""
    print("\n[PARALLEL] Testing concurrent organ calls...")
    start = time.time()

    results = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(lambda: httpx.get(f"{ORGANS['brain']}/health", timeout=5)): 'brain',
            executor.submit(lambda: httpx.get(f"{ORGANS['cells']}/health", timeout=5)): 'cells',
            executor.submit(lambda: httpx.post(f"{ORGANS['brain']}/analyze", json={"query": "test"}, timeout=5)): 'analyze',
            executor.submit(lambda: httpx.post(f"{ORGANS['cells']}/extract", json={"text": "John Smith $100"}, timeout=5)): 'extract',
        }

        for future in as_completed(futures):
            name = futures[future]
            try:
                r = future.result()
                results[name] = r.status_code == 200
            except:
                results[name] = False

    elapsed = (time.time() - start) * 1000
    success = sum(results.values())
    total = len(results)

    for name, ok in results.items():
        status = "OK" if ok else "FAIL"
        print(f"  {name}: {status}")

    print(f"  Parallel time: {elapsed:.2f}ms ({success}/{total} success)")
    return success == total, elapsed

# =============================================================================
# Main
# =============================================================================

def main():
    print("=" * 60)
    print("   L INVESTIGATION - POLYGLOT INTEGRATION TEST")
    print("=" * 60)

    results = []

    # Run all tests
    tests = [
        ("Synapses (C++)", test_synapses),
        ("Brain (Go)", test_brain),
        ("Cells (Rust)", test_cells),
        ("Full Investigation", test_full_investigation),
        ("Parallel Load", test_parallel_load),
    ]

    for name, test_fn in tests:
        success, elapsed = test_fn()
        results.append((name, success, elapsed))

    # Summary
    print("\n" + "=" * 60)
    print("   RESULTS SUMMARY")
    print("=" * 60)

    total_time = 0
    passed = 0
    for name, success, elapsed in results:
        status = "PASS" if success else "FAIL"
        icon = "✓" if success else "✗"
        print(f"  {icon} {name}: {status} ({elapsed:.1f}ms)")
        total_time += elapsed
        if success:
            passed += 1

    print(f"\n  Total: {passed}/{len(results)} passed")
    print(f"  Total time: {total_time:.1f}ms")

    if passed == len(results):
        print("\n  [SUCCESS] All organs working together!")
    else:
        print("\n  [WARNING] Some organs offline")

    return passed == len(results)

if __name__ == '__main__':
    exit(0 if main() else 1)
