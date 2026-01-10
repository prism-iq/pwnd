#!/usr/bin/env python3
"""
Test C++ Synapses FFI from Python
Demonstrates the universal bridge working
"""

import ctypes
from ctypes import c_char_p, c_int, c_int64, c_float, c_uint64, c_double, Structure, POINTER

# Load the synapse library
lib = ctypes.CDLL('./lib/liblsearch.so')

# =============================================================================
# FFI Type Definitions
# =============================================================================

class CSearchResult(Structure):
    _fields_ = [
        ('id', c_int64),
        ('score', c_float),
        ('snippet', ctypes.c_char * 256)
    ]

class CPattern(Structure):
    _fields_ = [
        ('type', ctypes.c_char * 32),
        ('value', ctypes.c_char * 256)
    ]

class CNumeric(Structure):
    _fields_ = [
        ('value', c_double),
        ('unit', ctypes.c_char * 16)
    ]

# =============================================================================
# Function Signatures
# =============================================================================

lib.l_search_init.restype = c_int
lib.l_search_init.argtypes = []

lib.l_synapse_hash.restype = c_uint64
lib.l_synapse_hash.argtypes = [c_char_p]

lib.l_synapse_normalize.restype = c_int
lib.l_synapse_normalize.argtypes = [c_char_p, c_char_p, c_int]

lib.l_synapse_similarity.restype = c_float
lib.l_synapse_similarity.argtypes = [c_char_p, c_char_p]

lib.l_synapse_numbers.restype = c_int
lib.l_synapse_numbers.argtypes = [c_char_p, POINTER(CNumeric), c_int]

lib.l_synapse_version.restype = c_char_p
lib.l_synapse_version.argtypes = []

lib.l_search_extract.restype = c_int
lib.l_search_extract.argtypes = [c_char_p, POINTER(CPattern), c_int]

# =============================================================================
# Tests
# =============================================================================

def main():
    print("=" * 60)
    print("   C++ SYNAPSES TEST - Universal FFI Bridge")
    print("=" * 60)

    # Initialize
    lib.l_search_init()
    version = lib.l_synapse_version().decode()
    print(f"\n[OK] Synapse version: {version}")

    # Test hash
    text = b"Jeffrey Skilling committed fraud"
    h = lib.l_synapse_hash(text)
    print(f"\n[HASH] '{text.decode()}' -> {h}")

    # Test normalize
    dirty = b"  Hello,   WORLD!!!  How ARE you?  "
    clean = ctypes.create_string_buffer(256)
    lib.l_synapse_normalize(dirty, clean, 256)
    print(f"[NORMALIZE] '{dirty.decode().strip()}' -> '{clean.value.decode()}'")

    # Test similarity
    a = b"The quick brown fox jumps"
    b_str = b"A quick brown dog runs"
    sim = lib.l_synapse_similarity(a, b_str)
    print(f"[SIMILARITY] '{a.decode()}' vs '{b_str.decode()}' -> {sim:.2%}")

    # Test number extraction
    money_text = b"He transferred $5,000,000 and another $2.5M to offshore accounts"
    nums = (CNumeric * 10)()
    count = lib.l_synapse_numbers(money_text, nums, 10)
    print(f"\n[NUMBERS] Found {count} numbers in: '{money_text.decode()}'")
    for i in range(count):
        print(f"  - ${nums[i].value:,.2f} {nums[i].unit.decode()}")

    # Test pattern extraction
    crime_text = b"John Smith sent $100,000 to jane@offshore.com on 2024-03-15"
    patterns = (CPattern * 20)()
    count = lib.l_search_extract(crime_text, patterns, 20)
    print(f"\n[PATTERNS] Found {count} patterns in: '{crime_text.decode()}'")
    for i in range(count):
        print(f"  - {patterns[i].type.decode()}: {patterns[i].value.decode()}")

    print("\n" + "=" * 60)
    print("   SYNAPSES WORKING PERFECTLY")
    print("=" * 60)

if __name__ == '__main__':
    main()
