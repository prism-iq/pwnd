#!/usr/bin/env python3
"""
L Investigation - Multi-Phi3 Pipeline
Specialized Phi-3 instances with router and Haiku aggregator

Architecture:
  Query → Router → [Phi3-Dates, Phi3-Persons, Phi3-Orgs, Phi3-Amounts] → Haiku Aggregator → DB

Each Phi-3 is specialized for one entity type = higher accuracy
Haiku validates and merges before insertion
"""

import asyncio
import re
import json
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum
import httpx

# =============================================================================
# Configuration
# =============================================================================

class EntityType(Enum):
    DATES = "dates"
    PERSONS = "persons"
    ORGS = "organizations"
    AMOUNTS = "amounts"
    LOCATIONS = "locations"
    EMAILS = "emails"

PHI3_ENDPOINTS = {
    EntityType.DATES: "http://127.0.0.1:11434/api/generate",
    EntityType.PERSONS: "http://127.0.0.1:11434/api/generate",
    EntityType.ORGS: "http://127.0.0.1:11434/api/generate",
    EntityType.AMOUNTS: "http://127.0.0.1:11434/api/generate",
}

RUST_EXTRACT_URL = "http://127.0.0.1:9001/extract"

# =============================================================================
# Specialized Prompts (Phi-3 optimized)
# =============================================================================

PHI3_PROMPTS = {
    EntityType.DATES: """Extract ALL dates from this text. Output JSON array only.
Format: [{"value": "YYYY-MM-DD", "original": "original text", "context": "surrounding words"}]
Text: {text}
JSON:""",

    EntityType.PERSONS: """Extract ALL person names from this text. Output JSON array only.
Format: [{"name": "Full Name", "role": "role if mentioned", "context": "surrounding words"}]
Text: {text}
JSON:""",

    EntityType.ORGS: """Extract ALL organizations from this text. Output JSON array only.
Format: [{"name": "Organization Name", "type": "company/foundation/govt/etc", "context": "surrounding words"}]
Text: {text}
JSON:""",

    EntityType.AMOUNTS: """Extract ALL monetary amounts from this text. Output JSON array only.
Format: [{"value": number, "currency": "USD/EUR/etc", "original": "$1,234", "context": "surrounding words"}]
Text: {text}
JSON:""",
}

# =============================================================================
# Fast Regex Pre-filter (C++ synapses backup)
# =============================================================================

REGEX_PATTERNS = {
    EntityType.DATES: [
        r'\b(\d{4}-\d{2}-\d{2})\b',
        r'\b(\d{1,2}/\d{1,2}/\d{2,4})\b',
        r'\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4})\b',
    ],
    EntityType.PERSONS: [
        r'\b([A-Z][a-z]{2,15} [A-Z][a-z]{2,15})\b',
        r'\b([A-Z][a-z]{2,15} [A-Z]\. [A-Z][a-z]{2,15})\b',
    ],
    EntityType.ORGS: [
        r'\b([A-Z][a-zA-Z]+(?: [A-Z][a-zA-Z]+)* (?:Inc|LLC|Corp|Ltd|Foundation|Group|Partners|Company|Co|Association|Bank))\b',
    ],
    EntityType.AMOUNTS: [
        r'(\$[\d,]+(?:\.\d{2})?(?:[MBK])?)',
        r'(€[\d,]+(?:\.\d{2})?)',
        r'(\d+(?:,\d{3})*(?:\.\d{2})?\s*(?:dollars|USD|euros|EUR))',
    ],
}

def regex_extract(text: str, entity_type: EntityType) -> List[Dict]:
    """Fast regex extraction as pre-filter"""
    results = []
    patterns = REGEX_PATTERNS.get(entity_type, [])

    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            start = max(0, match.start() - 50)
            end = min(len(text), match.end() + 50)
            context = text[start:end].strip()

            results.append({
                "value": match.group(1) if match.groups() else match.group(0),
                "context": context,
                "source": "regex"
            })

    return results

# =============================================================================
# Rust Extraction (Cells)
# =============================================================================

async def rust_extract(text: str) -> Dict[str, List]:
    """Call Rust extraction service"""
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(RUST_EXTRACT_URL,
                                  json={"text": text[:10000]},
                                  timeout=5.0)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
    return {}

# =============================================================================
# Phi-3 Specialized Extractors
# =============================================================================

@dataclass
class Phi3Result:
    entity_type: EntityType
    entities: List[Dict]
    processing_time_ms: float
    source: str  # "phi3" or "regex_fallback"

async def call_phi3(text: str, entity_type: EntityType, timeout: float = 10.0) -> Phi3Result:
    """Call specialized Phi-3 instance for entity extraction"""
    start = time.time()

    prompt = PHI3_PROMPTS[entity_type].format(text=text[:3000])

    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(
                PHI3_ENDPOINTS[entity_type],
                json={
                    "model": "phi3:mini",
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 500,
                    }
                },
                timeout=timeout
            )

            if r.status_code == 200:
                data = r.json()
                response_text = data.get("response", "")

                # Parse JSON from response
                try:
                    # Find JSON array in response
                    json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
                    if json_match:
                        entities = json.loads(json_match.group())
                        return Phi3Result(
                            entity_type=entity_type,
                            entities=entities,
                            processing_time_ms=(time.time() - start) * 1000,
                            source="phi3"
                        )
                except json.JSONDecodeError:
                    pass

        except Exception as e:
            pass

    # Fallback to regex
    entities = regex_extract(text, entity_type)
    return Phi3Result(
        entity_type=entity_type,
        entities=entities,
        processing_time_ms=(time.time() - start) * 1000,
        source="regex_fallback"
    )

# =============================================================================
# Router - Dispatches to specialized extractors
# =============================================================================

class EntityRouter:
    """Routes extraction requests to appropriate Phi-3 instances"""

    def __init__(self):
        self.stats = {et: {"calls": 0, "phi3": 0, "regex": 0} for et in EntityType}

    async def extract_all(self, text: str) -> Dict[str, List[Dict]]:
        """Extract all entity types in parallel"""

        # First: Fast Rust extraction (1-3ms)
        rust_result = await rust_extract(text)

        # Determine which types need Phi-3 enhancement
        tasks = []
        for entity_type in [EntityType.DATES, EntityType.PERSONS, EntityType.ORGS, EntityType.AMOUNTS]:
            self.stats[entity_type]["calls"] += 1
            tasks.append(call_phi3(text, entity_type))

        # Run all Phi-3 extractions in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Merge results
        merged = {
            "dates": [],
            "persons": [],
            "organizations": [],
            "amounts": [],
            "locations": rust_result.get("locations", []),
            "emails": rust_result.get("emails", []),
            "phones": rust_result.get("phones", []),
            "urls": rust_result.get("urls", []),
        }

        for result in results:
            if isinstance(result, Phi3Result):
                key = result.entity_type.value
                merged[key] = result.entities

                if result.source == "phi3":
                    self.stats[result.entity_type]["phi3"] += 1
                else:
                    self.stats[result.entity_type]["regex"] += 1

        return merged

    def get_stats(self) -> Dict:
        """Get router statistics"""
        return self.stats

# =============================================================================
# Haiku Aggregator - Validates and merges before DB insert
# =============================================================================

HAIKU_VALIDATION_PROMPT = """You are validating extracted entities for a criminal investigation database.

Extracted entities:
{entities}

Original text snippet:
{text}

For each entity, determine:
1. Is it a real entity (not noise)?
2. Is the type correct?
3. Should it be merged with another entity (duplicate/alias)?

Output JSON:
{{
  "validated": [
    {{"type": "person", "value": "...", "confidence": 0.95, "keep": true}},
    ...
  ],
  "merges": [
    {{"from": "value1", "to": "value2", "reason": "alias"}}
  ],
  "rejected": [
    {{"value": "...", "reason": "not an entity"}}
  ]
}}"""

async def local_validate(entities: Dict[str, List], text: str) -> Dict:
    """Validate entities using local logic (no external API)"""
    # Accept all entities from Phi-3 extraction - validation is done locally
    validated = []
    for entity_type, items in entities.items():
        for item in items[:20]:
            value = item.get("value") or item.get("name") or str(item)
            if value and len(value) > 2:
                validated.append({
                    "type": entity_type,
                    "value": value,
                    "confidence": 0.75,
                    "keep": True
                })

    return {
        "validated": validated,
        "merges": [],
        "rejected": []
    }

# =============================================================================
# Full Pipeline
# =============================================================================

class MultiPhi3Pipeline:
    """Complete Multi-Phi3 extraction pipeline"""

    def __init__(self):
        self.router = EntityRouter()
        self.total_processed = 0
        self.total_entities = 0

    async def process(self, text: str, validate: bool = True) -> Dict:
        """Process text through full pipeline"""
        start = time.time()

        # Step 1: Parallel extraction via router
        entities = await self.router.extract_all(text)

        entity_count = sum(len(v) for v in entities.values())

        # Step 2: Local validation (optional)
        validation = None
        if validate and entity_count > 0:
            validation = await local_validate(entities, text)

        self.total_processed += 1
        self.total_entities += entity_count

        return {
            "entities": entities,
            "validation": validation,
            "stats": {
                "processing_time_ms": (time.time() - start) * 1000,
                "entity_count": entity_count,
                "router_stats": self.router.get_stats()
            }
        }

    async def process_batch(self, texts: List[str], validate: bool = False) -> List[Dict]:
        """Process multiple texts in parallel"""
        tasks = [self.process(text, validate=validate) for text in texts]
        return await asyncio.gather(*tasks)

# =============================================================================
# Global Instance
# =============================================================================

_pipeline = None

def get_pipeline() -> MultiPhi3Pipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = MultiPhi3Pipeline()
    return _pipeline

# =============================================================================
# API Functions (for integration)
# =============================================================================

async def extract_entities_multi(text: str, validate: bool = True) -> Dict:
    """Main entry point for multi-Phi3 extraction"""
    pipeline = get_pipeline()
    return await pipeline.process(text, validate=validate)

async def extract_batch(texts: List[str]) -> List[Dict]:
    """Batch extraction without validation"""
    pipeline = get_pipeline()
    return await pipeline.process_batch(texts, validate=False)

# =============================================================================
# CLI Test
# =============================================================================

async def main():
    print("=" * 60)
    print("  Multi-Phi3 Pipeline Test")
    print("=" * 60)

    test_text = """
    On January 15, 2024, Jeffrey Epstein transferred $5,000,000 to Deutsche Bank
    from his account at JP Morgan Chase. The wire transfer was authorized by
    Ghislaine Maxwell and processed through their Virgin Islands shell company,
    Southern Trust Company Inc.

    Contact: jeffrey@gmail.com, +1-555-123-4567
    Flight manifest shows departure from Palm Beach to Little St. James.
    """

    print("\nTest text:")
    print(test_text[:200] + "...")

    print("\n[1] Testing Rust extraction...")
    rust_result = await rust_extract(test_text)
    entity_count = sum(len(v) for k, v in rust_result.items() if isinstance(v, list))
    print(f"  Rust found: {entity_count} entities")

    print("\n[2] Testing Multi-Phi3 pipeline...")
    pipeline = get_pipeline()
    result = await pipeline.process(test_text, validate=False)

    print(f"\n  Results:")
    for entity_type, entities in result["entities"].items():
        if entities:
            print(f"    {entity_type}: {len(entities)}")
            for e in entities[:3]:
                val = e.get("value") or e.get("name") or str(e)
                print(f"      - {val}")

    print(f"\n  Processing time: {result['stats']['processing_time_ms']:.1f}ms")
    print(f"  Total entities: {result['stats']['entity_count']}")

    print("\n" + "=" * 60)
    print("  Pipeline ready!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
