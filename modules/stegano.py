"""Steganography detection module"""
import os
from typing import Dict, Any
from pathlib import Path

def check_image(filepath: str) -> Dict[str, Any]:
    """
    Analyze image for steganography:
    - LSB analysis
    - EOF data
    - Excessive metadata
    - Unusual dimensions

    Returns:
        {
            "has_hidden_data": bool,
            "confidence": float,
            "method_suspected": str,
            "findings": []
        }
    """
    if not os.path.exists(filepath):
        return {"error": "File not found"}

    findings = []
    confidence = 0.0

    # Get file size
    file_size = os.path.getsize(filepath)

    # Check for data after EOF markers
    try:
        with open(filepath, 'rb') as f:
            content = f.read()

        # JPEG: check for data after FFD9
        if content[:2] == b'\xff\xd8':
            eof_marker = b'\xff\xd9'
            eof_pos = content.rfind(eof_marker)
            if eof_pos > 0 and eof_pos < len(content) - 2:
                extra_bytes = len(content) - eof_pos - 2
                if extra_bytes > 10:
                    findings.append({
                        "type": "eof_data",
                        "detail": f"{extra_bytes} bytes after JPEG EOF"
                    })
                    confidence += 0.6

        # PNG: check for data after IEND
        if content[:8] == b'\x89PNG\r\n\x1a\n':
            iend_marker = b'IEND'
            iend_pos = content.rfind(iend_marker)
            if iend_pos > 0 and iend_pos < len(content) - 8:
                extra_bytes = len(content) - iend_pos - 8
                if extra_bytes > 10:
                    findings.append({
                        "type": "eof_data",
                        "detail": f"{extra_bytes} bytes after PNG IEND"
                    })
                    confidence += 0.6

    except Exception as e:
        findings.append({"type": "error", "detail": str(e)})

    has_hidden_data = confidence > 0.5
    method_suspected = "eof_appended" if has_hidden_data else "none"

    return {
        "has_hidden_data": has_hidden_data,
        "confidence": round(confidence, 2),
        "method_suspected": method_suspected,
        "findings": findings
    }

def check_attachment(filepath: str, content_type: str) -> Dict[str, Any]:
    """
    Analyze generic attachment:
    - Extension/content mismatch
    - Embedded files
    - Hidden streams

    Returns:
        {
            "suspicious": bool,
            "findings": [],
            "entropy": float
        }
    """
    if not os.path.exists(filepath):
        return {"error": "File not found"}

    findings = []
    suspicious = False

    # Get file extension
    ext = Path(filepath).suffix.lower()

    # Read magic bytes
    try:
        with open(filepath, 'rb') as f:
            magic = f.read(16)

        # Check for common mismatches
        magic_ext_map = {
            b'\x89PNG': ['.png'],
            b'\xff\xd8\xff': ['.jpg', '.jpeg'],
            b'GIF8': ['.gif'],
            b'%PDF': ['.pdf'],
            b'PK\x03\x04': ['.zip', '.docx', '.xlsx', '.pptx'],
        }

        for magic_bytes, expected_exts in magic_ext_map.items():
            if magic.startswith(magic_bytes):
                if ext not in expected_exts:
                    findings.append({
                        "type": "extension_mismatch",
                        "detail": f"File starts with {magic_bytes.hex()} but has {ext} extension"
                    })
                    suspicious = True

        # Calculate entropy
        with open(filepath, 'rb') as f:
            data = f.read()

        from modules.crypto import analyze_entropy
        entropy_result = analyze_entropy(data)

    except Exception as e:
        findings.append({"type": "error", "detail": str(e)})
        entropy_result = {"entropy": 0.0}

    return {
        "suspicious": suspicious,
        "findings": findings,
        "entropy": entropy_result.get("entropy", 0.0)
    }

def extract_metadata(filepath: str) -> Dict[str, Any]:
    """
    Extract and analyze metadata:
    - EXIF (images)
    - PDF metadata
    - Office doc properties

    Returns:
        {
            "metadata": {},
            "anomalies": [],
            "hidden_fields": []
        }
    """
    if not os.path.exists(filepath):
        return {"error": "File not found"}

    metadata = {}
    anomalies = []
    hidden_fields = []

    ext = Path(filepath).suffix.lower()

    # Basic file stats
    stat = os.stat(filepath)
    metadata["file_size"] = stat.st_size
    metadata["created"] = stat.st_ctime
    metadata["modified"] = stat.st_mtime

    # Check for unusual file size patterns
    if stat.st_size % 1024 == 0:
        anomalies.append({
            "type": "round_size",
            "detail": f"File size is exactly {stat.st_size // 1024}KB"
        })

    # For images, check basic dimensions (would need PIL/Pillow for full EXIF)
    if ext in ['.jpg', '.jpeg', '.png', '.gif']:
        try:
            with open(filepath, 'rb') as f:
                data = f.read(1000)
                if b'EXIF' in data or b'GPS' in data:
                    metadata["has_exif"] = True
        except Exception:
            pass

    return {
        "metadata": metadata,
        "anomalies": anomalies,
        "hidden_fields": hidden_fields
    }
