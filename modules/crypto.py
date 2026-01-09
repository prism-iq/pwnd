"""Cryptographic anomaly detection module"""
import re
import math
from typing import List, Dict, Any
from collections import Counter

def analyze_entropy(data: bytes) -> Dict[str, Any]:
    """
    Calculate Shannon entropy of data.
    High entropy (>7.5) suggests encrypted/compressed data.

    Returns:
        {
            "entropy": float,
            "is_anomalous": bool,
            "threshold": 7.5,
            "interpretation": str
        }
    """
    if not data:
        return {"entropy": 0.0, "is_anomalous": False, "threshold": 7.5, "interpretation": "empty"}

    # Calculate byte frequency
    counter = Counter(data)
    length = len(data)

    # Shannon entropy
    entropy = 0.0
    for count in counter.values():
        probability = count / length
        if probability > 0:
            entropy -= probability * math.log2(probability)

    is_anomalous = entropy > 7.5
    interpretation = "high_entropy" if is_anomalous else "normal"

    return {
        "entropy": round(entropy, 3),
        "is_anomalous": is_anomalous,
        "threshold": 7.5,
        "interpretation": interpretation
    }

def detect_patterns(text: str) -> List[Dict[str, Any]]:
    """
    Detect suspicious patterns in text:
    - Alphanumeric codes (A1B2C3)
    - Base64 strings
    - Hex strings
    - Repeated amounts
    - Date patterns

    Returns:
        [{pattern_type, value, count, positions}]
    """
    patterns = []

    # Base64 pattern (at least 20 chars)
    base64_pattern = r'\b[A-Za-z0-9+/]{20,}={0,2}\b'
    for match in re.finditer(base64_pattern, text):
        patterns.append({
            "pattern_type": "base64",
            "value": match.group()[:50],
            "count": 1,
            "positions": [match.start()]
        })

    # Hex strings (at least 16 chars)
    hex_pattern = r'\b[0-9a-fA-F]{16,}\b'
    for match in re.finditer(hex_pattern, text):
        patterns.append({
            "pattern_type": "hex",
            "value": match.group()[:50],
            "count": 1,
            "positions": [match.start()]
        })

    # Alphanumeric codes (e.g., A1B2C3D4)
    code_pattern = r'\b[A-Z]{1,2}\d{1,2}[A-Z]{1,2}\d{1,2}[A-Z\d]*\b'
    code_matches = re.findall(code_pattern, text)
    if code_matches:
        code_counter = Counter(code_matches)
        for code, count in code_counter.most_common(10):
            if count > 2:
                patterns.append({
                    "pattern_type": "alphanumeric_code",
                    "value": code,
                    "count": count,
                    "positions": []
                })

    # Money amounts
    amount_pattern = r'\$[\d,]+\.?\d*'
    amounts = re.findall(amount_pattern, text)
    if amounts:
        amount_counter = Counter(amounts)
        for amount, count in amount_counter.most_common(10):
            if count > 3:
                patterns.append({
                    "pattern_type": "recurring_amount",
                    "value": amount,
                    "count": count,
                    "positions": []
                })

    return patterns

def analyze_amounts(amounts: List[float]) -> Dict[str, Any]:
    """
    Analyze list of amounts for anomalies:
    - Round amounts (1000, 5000, etc.)
    - Sequences (1000, 2000, 3000)
    - Exact recurrences

    Returns:
        {
            "anomalies": [],
            "recurring": [],
            "round_amounts": [],
            "sequences": []
        }
    """
    if not amounts:
        return {"anomalies": [], "recurring": [], "round_amounts": [], "sequences": []}

    result = {
        "anomalies": [],
        "recurring": [],
        "round_amounts": [],
        "sequences": []
    }

    # Count exact amounts
    counter = Counter(amounts)
    for amount, count in counter.items():
        if count > 2:
            result["recurring"].append({"amount": amount, "count": count})

    # Round amounts (divisible by 100, 500, 1000)
    for amount in set(amounts):
        if amount >= 100:
            if amount % 1000 == 0:
                result["round_amounts"].append({"amount": amount, "divisor": 1000})
            elif amount % 500 == 0:
                result["round_amounts"].append({"amount": amount, "divisor": 500})
            elif amount % 100 == 0:
                result["round_amounts"].append({"amount": amount, "divisor": 100})

    # Detect sequences
    sorted_amounts = sorted(set(amounts))
    if len(sorted_amounts) >= 3:
        for i in range(len(sorted_amounts) - 2):
            diff1 = sorted_amounts[i+1] - sorted_amounts[i]
            diff2 = sorted_amounts[i+2] - sorted_amounts[i+1]
            if abs(diff1 - diff2) < 0.01 and diff1 > 0:
                result["sequences"].append({
                    "start": sorted_amounts[i],
                    "increment": diff1,
                    "length": 3
                })

    return result

def detect_code_words(text: str, known_codes: List[str] = None) -> List[Dict[str, Any]]:
    """
    Detect potential code words:
    - Words out of context
    - Unusual capitalization
    - Suspicious repetitions

    Returns:
        [{word, frequency, contexts, suspicion_score}]
    """
    if known_codes is None:
        known_codes = []

    # Tokenize
    words = re.findall(r'\b[A-Z][A-Za-z]+\b', text)

    if not words:
        return []

    # Count capitalized words
    counter = Counter(words)

    code_words = []
    for word, count in counter.most_common(50):
        suspicion = 0

        # Check if in known codes
        if word.upper() in [k.upper() for k in known_codes]:
            suspicion += 40

        # Unusual frequency
        if count > 5:
            suspicion += min(count * 2, 30)

        # Odd capitalization in middle of sentence
        if re.search(r'\. [a-z]+.*\b' + word + r'\b', text):
            suspicion += 20

        if suspicion > 30:
            code_words.append({
                "word": word,
                "frequency": count,
                "contexts": [],
                "suspicion_score": suspicion
            })

    return code_words[:20]
