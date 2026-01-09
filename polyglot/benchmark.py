#!/usr/bin/env python3
"""
L Investigation - Performance Benchmark
Measures throughput and latency of the polyglot system
"""

import time
import ctypes
import httpx
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

ITERATIONS = 50
PARALLEL_WORKERS = 10

# =============================================================================
# Benchmarks
# =============================================================================

def bench_synapses():
    """Benchmark C++ synapses"""
    lib = ctypes.CDLL('/opt/rag/polyglot/cpp-core/lib/liblsearch.so')
    lib.l_synapse_hash.restype = ctypes.c_uint64
    lib.l_synapse_hash.argtypes = [ctypes.c_char_p]
    lib.l_synapse_similarity.restype = ctypes.c_float
    lib.l_synapse_similarity.argtypes = [ctypes.c_char_p, ctypes.c_char_p]

    text = b"Jeffrey Skilling committed massive financial fraud at Enron Corporation"

    times = []
    for _ in range(ITERATIONS):
        start = time.perf_counter()
        lib.l_synapse_hash(text)
        lib.l_synapse_similarity(text, b"Ken Lay also committed fraud")
        times.append((time.perf_counter() - start) * 1000)

    return times

def bench_rust_extraction():
    """Benchmark Rust extraction"""
    text = "John Smith transferred $5,000,000 to Bank of America on 2024-03-15. Contact: john@enron.com"

    times = []
    with httpx.Client(timeout=10) as client:
        for _ in range(ITERATIONS):
            start = time.perf_counter()
            client.post('http://127.0.0.1:9001/extract', json={'text': text})
            times.append((time.perf_counter() - start) * 1000)

    return times

def bench_go_analysis():
    """Benchmark Go strategic analysis"""
    query = "Who committed the fraud at Enron Corporation?"

    times = []
    with httpx.Client(timeout=10) as client:
        for _ in range(ITERATIONS):
            start = time.perf_counter()
            client.post('http://127.0.0.1:8085/analyze', json={'query': query})
            times.append((time.perf_counter() - start) * 1000)

    return times

def bench_parallel_throughput():
    """Benchmark parallel throughput"""
    def single_request(i):
        start = time.perf_counter()
        httpx.post('http://127.0.0.1:9001/extract',
                   json={'text': f'Test {i}: John Smith $1000'},
                   timeout=10)
        return (time.perf_counter() - start) * 1000

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
        futures = [executor.submit(single_request, i) for i in range(ITERATIONS)]
        times = [f.result() for f in as_completed(futures)]
    total_time = time.perf_counter() - start

    throughput = ITERATIONS / total_time
    return times, throughput

# =============================================================================
# Main
# =============================================================================

def print_stats(name, times):
    avg = statistics.mean(times)
    p50 = statistics.median(times)
    p95 = sorted(times)[int(len(times) * 0.95)]
    p99 = sorted(times)[int(len(times) * 0.99)]
    min_t = min(times)
    max_t = max(times)

    print(f"\n  {name}:")
    print(f"    Mean:   {avg:.2f}ms")
    print(f"    P50:    {p50:.2f}ms")
    print(f"    P95:    {p95:.2f}ms")
    print(f"    P99:    {p99:.2f}ms")
    print(f"    Min:    {min_t:.2f}ms")
    print(f"    Max:    {max_t:.2f}ms")

def main():
    print("=" * 60)
    print("   L INVESTIGATION - PERFORMANCE BENCHMARK")
    print(f"   Iterations: {ITERATIONS}, Workers: {PARALLEL_WORKERS}")
    print("=" * 60)

    # C++ Synapses
    print("\n[1/4] Benchmarking C++ Synapses...")
    synapse_times = bench_synapses()
    print_stats("C++ Synapses (hash + similarity)", synapse_times)

    # Rust Extraction
    print("\n[2/4] Benchmarking Rust Extraction...")
    rust_times = bench_rust_extraction()
    print_stats("Rust Extraction (HTTP)", rust_times)

    # Go Analysis
    print("\n[3/4] Benchmarking Go Analysis...")
    go_times = bench_go_analysis()
    print_stats("Go Analysis (HTTP)", go_times)

    # Parallel Throughput
    print("\n[4/4] Benchmarking Parallel Throughput...")
    parallel_times, throughput = bench_parallel_throughput()
    print_stats("Parallel Requests", parallel_times)
    print(f"    Throughput: {throughput:.1f} req/s")

    # Summary
    print("\n" + "=" * 60)
    print("   PERFORMANCE SUMMARY")
    print("=" * 60)
    print(f"""
  Organ Performance (P50):
    • Synapses (C++):  {statistics.median(synapse_times):.2f}ms  - INSTANT
    • Cells (Rust):    {statistics.median(rust_times):.2f}ms  - FAST
    • Brain (Go):      {statistics.median(go_times):.2f}ms  - FAST

  System Throughput: {throughput:.1f} requests/second

  Target vs Actual:
    • Extraction < 5ms:  {'PASS' if statistics.median(rust_times) < 5 else 'FAIL'} ({statistics.median(rust_times):.1f}ms)
    • Analysis < 10ms:   {'PASS' if statistics.median(go_times) < 10 else 'FAIL'} ({statistics.median(go_times):.1f}ms)
    • Throughput > 50/s: {'PASS' if throughput > 50 else 'FAIL'} ({throughput:.0f}/s)
""")

if __name__ == '__main__':
    main()
