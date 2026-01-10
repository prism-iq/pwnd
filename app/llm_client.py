"""LLM client - Local Phi-3 workers + Claude API

Architecture:
- Phi-3 (local, free): Entity extraction, filtering, simple tasks
- Sonnet (API, paid): High-quality synthesis with caching
- Haiku (API, cheap): Fast structured analysis
"""
import logging
import httpx
from typing import Dict, Any, Optional, List
from collections import OrderedDict
from app.config import LLM_MISTRAL_URL, LLM_HAIKU_API_KEY

log = logging.getLogger(__name__)


async def call_local(prompt: str, max_tokens: int = 512, temperature: float = 0.3) -> str:
    """Call local Phi-3 via worker pool"""
    try:
        from app.workers import worker_pool, JobType
        if not worker_pool.workers:
            return ""

        # Use summarize job type for general prompts
        job_id = await worker_pool.submit(
            JobType.SUMMARIZE,
            {"text": prompt, "max_length": max_tokens * 4},
        )
        job = await worker_pool.get_result(job_id, timeout=15)
        if job and job.result:
            return job.result
        return ""
    except Exception as e:
        log.debug(f"Local LLM call failed: {e}")
        return ""


async def extract_entities_local(text: str) -> List[Dict]:
    """Extract entities using local Phi-3"""
    try:
        from app.workers import worker_pool, JobType
        if not worker_pool.workers:
            return []

        job_id = await worker_pool.submit(
            JobType.EXTRACT_ENTITIES,
            {"text": text[:3000]}
        )
        job = await worker_pool.get_result(job_id, timeout=30)
        if job and job.result:
            return job.result
        return []
    except Exception:
        return []


async def extract_relationships_local(text: str, entities: List[Dict]) -> List[Dict]:
    """Extract relationships using local Phi-3"""
    try:
        from app.workers import worker_pool, JobType
        if not worker_pool.workers:
            return []

        job_id = await worker_pool.submit(
            JobType.EXTRACT_RELATIONSHIPS,
            {"text": text[:2500], "entities": entities}
        )
        job = await worker_pool.get_result(job_id, timeout=30)
        if job and job.result:
            return job.result
        return []
    except Exception:
        return []


async def parallel_extract_entities(text: str, query: str = "", entity_types: List[str] = None) -> Dict:
    """
    Parallel Phi-3 extraction with Haiku validation.

    Architecture:
        [Doc batch]
              ↓
    ┌─────────────────────────────────────┐
    │  Phi3-A (dates)    → SQL dates      │
    │  Phi3-B (persons)  → SQL persons    │  parallel
    │  Phi3-C (orgs)     → SQL orgs       │
    │  Phi3-D (amounts)  → SQL amounts    │
    └─────────────────────────────────────┘
              ↓ merge results
    [Haiku] → validate, correct, structure → clean INSERT
    """
    try:
        from app.workers import parallel_extract
        return await parallel_extract(text, query, entity_types)
    except Exception as e:
        return {"error": str(e), "raw_extracted": {}, "validated": {}}


async def parse_query_intent(query: str) -> Dict:
    """Parse user query intent using local Phi-3"""
    try:
        from app.workers import worker_pool, JobType
        if not worker_pool.workers:
            return {"intent": "other", "targets": [], "keywords": []}

        job_id = await worker_pool.submit(
            JobType.PARSE_INTENT,
            {"query": query}
        )
        job = await worker_pool.get_result(job_id, timeout=20)
        if job and job.result:
            return job.result
        return {"intent": "other", "targets": [], "keywords": []}
    except Exception:
        return {"intent": "other", "targets": [], "keywords": []}


async def generate_subqueries(query: str, context: str = "") -> List[str]:
    """Generate follow-up queries (self-questioning) using local Phi-3"""
    try:
        from app.workers import worker_pool, JobType
        if not worker_pool.workers:
            return []

        job_id = await worker_pool.submit(
            JobType.GENERATE_SUBQUERIES,
            {"query": query, "context": context}
        )
        job = await worker_pool.get_result(job_id, timeout=25)
        if job and job.result:
            return job.result
        return []
    except Exception:
        return []


def insert_extracted_entities(validated: Dict, source_email_id: int = None) -> Dict[str, int]:
    """
    Insert validated entities into the graph database.

    Args:
        validated: Dict with dates, persons, orgs, amounts, locations
        source_email_id: Optional email ID to create edges from

    Returns:
        Dict with counts of inserted entities by type
    """
    from app.db import execute_insert, execute_query

    counts = {"persons": 0, "orgs": 0, "locations": 0, "edges": 0}

    # Insert persons
    for person in validated.get("persons", []):
        name = person.get("name", "")
        if not name:
            continue
        try:
            execute_insert(
                "graph",
                """INSERT INTO nodes (type, name, name_normalized, metadata)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (type, name_normalized) DO UPDATE SET
                   metadata = nodes.metadata || EXCLUDED.metadata""",
                ("person", name, name.lower(), person)
            )
            counts["persons"] += 1
        except Exception:
            pass

    # Insert organizations
    for org in validated.get("orgs", []):
        name = org.get("name", "")
        if not name:
            continue
        try:
            execute_insert(
                "graph",
                """INSERT INTO nodes (type, name, name_normalized, metadata)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (type, name_normalized) DO UPDATE SET
                   metadata = nodes.metadata || EXCLUDED.metadata""",
                ("organization", name, name.lower(), org)
            )
            counts["orgs"] += 1
        except Exception:
            pass

    # Insert locations
    for loc in validated.get("locations", []):
        name = loc.get("name", "")
        if not name:
            continue
        try:
            execute_insert(
                "graph",
                """INSERT INTO nodes (type, name, name_normalized, metadata)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (type, name_normalized) DO UPDATE SET
                   metadata = nodes.metadata || EXCLUDED.metadata""",
                ("location", name, name.lower(), loc)
            )
            counts["locations"] += 1
        except Exception:
            pass

    # If we have a source email, create edges
    if source_email_id:
        # Get email node ID
        email_node = execute_query(
            "graph",
            "SELECT id FROM nodes WHERE type = 'email' AND metadata->>'email_id' = %s",
            (str(source_email_id),)
        )
        if email_node:
            email_node_id = email_node[0]["id"]
            # Create edges to extracted entities
            for person in validated.get("persons", []):
                try:
                    person_node = execute_query(
                        "graph",
                        "SELECT id FROM nodes WHERE type = 'person' AND name_normalized = %s",
                        (person.get("name", "").lower(),)
                    )
                    if person_node:
                        execute_insert(
                            "graph",
                            """INSERT INTO edges (from_node_id, to_node_id, type)
                               VALUES (%s, %s, 'mentions')
                               ON CONFLICT DO NOTHING""",
                            (email_node_id, person_node[0]["id"])
                        )
                        counts["edges"] += 1
                except Exception:
                    pass

    return counts


async def call_mistral(prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
    """Call local LLM via HTTP (legacy)"""
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                LLM_MISTRAL_URL,
                json={
                    "prompt": prompt,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "stop": ["</s>", "\n\nUser:", "\n\nHuman:"]
                }
            )
            response.raise_for_status()
            data = response.json()
            return data.get("text", "").strip()
    except Exception as e:
        return f"Error calling local LLM: {str(e)}"

def check_haiku_rate_limit() -> Dict[str, Any]:
    """Check if Haiku rate limit is reached for today"""
    from app.db import execute_query
    from app.config import HAIKU_DAILY_LIMIT, HAIKU_COST_LIMIT_USD
    from datetime import datetime

    # Count calls today
    today = datetime.now().date()
    result = execute_query(
        "audit",
        """SELECT COUNT(*) as call_count, COALESCE(SUM(cost_usd), 0) as total_cost
           FROM haiku_calls
           WHERE created_at::date = %s""",
        (today,)
    )

    if not result:
        return {"allowed": True, "calls_today": 0, "cost_today": 0.0}

    call_count = result[0]["call_count"]
    total_cost = result[0]["total_cost"]

    if call_count >= HAIKU_DAILY_LIMIT:
        return {"allowed": False, "reason": f"Daily limit reached ({HAIKU_DAILY_LIMIT} calls)", "calls_today": call_count}

    if total_cost >= HAIKU_COST_LIMIT_USD:
        return {"allowed": False, "reason": f"Cost limit reached (${HAIKU_COST_LIMIT_USD})", "cost_today": total_cost}

    return {"allowed": True, "calls_today": call_count, "cost_today": total_cost}

async def call_haiku(prompt: str, system: Optional[str] = None, max_tokens: int = 2048) -> Dict[str, Any]:
    """Call Claude Haiku API for structured analysis with rate limiting"""
    if not LLM_HAIKU_API_KEY:
        return {"error": "ANTHROPIC_API_KEY not set"}

    # Check rate limit
    limit_check = check_haiku_rate_limit()
    if not limit_check["allowed"]:
        return {"error": f"Rate limit: {limit_check['reason']}", "fallback_to_mistral": True}

    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            messages = [{"role": "user", "content": prompt}]

            payload = {
                "model": "claude-3-5-haiku-20241022",
                "max_tokens": max_tokens,
                "messages": messages
            }

            if system:
                payload["system"] = system

            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": LLM_HAIKU_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json=payload
            )
            response.raise_for_status()
            data = response.json()

            # Extract text and usage
            content = data.get("content", [])
            usage = data.get("usage", {})

            if content and isinstance(content, list):
                text = content[0].get("text", "")

                # Log the call to audit.db
                from app.db import execute_insert
                tokens_in = usage.get("input_tokens", 0)
                tokens_out = usage.get("output_tokens", 0)
                cost_usd = (tokens_in * 0.80 / 1_000_000) + (tokens_out * 4.00 / 1_000_000)

                execute_insert(
                    "audit",
                    """INSERT INTO haiku_calls (tokens_in, tokens_out, cost_usd, query_preview)
                       VALUES (%s, %s, %s, %s)""",
                    (tokens_in, tokens_out, cost_usd, prompt[:200])
                )

                return {"text": text, "usage": usage, "cost_usd": cost_usd}

            return {"error": "Invalid response format"}

    except Exception as e:
        return {"error": f"Error calling Haiku: {str(e)}"}


def check_opus_rate_limit() -> Dict[str, Any]:
    """Check if Opus rate limit is reached for today"""
    from app.db import execute_query
    from app.config import OPUS_DAILY_LIMIT, OPUS_COST_LIMIT_USD
    from datetime import datetime

    today = datetime.now().date()
    result = execute_query(
        "audit",
        """SELECT COUNT(*) as call_count, COALESCE(SUM(cost_usd), 0) as total_cost
           FROM opus_calls
           WHERE created_at::date = %s""",
        (today,)
    )

    if not result:
        return {"allowed": True, "calls_today": 0, "cost_today": 0.0}

    call_count = result[0]["call_count"]
    total_cost = float(result[0]["total_cost"])

    if call_count >= OPUS_DAILY_LIMIT:
        return {"allowed": False, "reason": f"Daily limit reached ({OPUS_DAILY_LIMIT} calls)", "calls_today": call_count}

    if total_cost >= OPUS_COST_LIMIT_USD:
        return {"allowed": False, "reason": f"Cost limit reached (${OPUS_COST_LIMIT_USD})", "cost_today": total_cost}

    return {"allowed": True, "calls_today": call_count, "cost_today": total_cost}


_opus_cache = OrderedDict()
_OPUS_CACHE_SIZE = 50
_MOCK_MODE = False  # Set True for testing without real API calls

async def call_opus(prompt: str, system: Optional[str] = None, max_tokens: int = 512) -> Dict[str, Any]:
    """Call Claude Opus API for synthesis with caching and rate limiting.
    Uses Opus 4 ($15/$75 per M tokens) - highest quality synthesis.
    """
    import os
    from app.config import LLM_OPUS_API_KEY

    # Mock mode for testing
    if _MOCK_MODE or os.getenv("LLM_MOCK_MODE"):
        log.info("Mock mode: returning test response")
        return {
            "text": f"[MOCK] Analysis of query. Found relevant documents. Key persons mentioned include various individuals connected to the investigation. See sources for details. [#13015] [#13031]",
            "usage": {"input_tokens": 100, "output_tokens": 50},
            "cost_usd": 0.0,
            "mock": True
        }

    if not LLM_OPUS_API_KEY:
        return {"error": "ANTHROPIC_API_KEY not set", "fallback": True}

    # Check cache first (save API costs)
    import hashlib
    cache_key = hashlib.md5((prompt[:500] + str(system)[:100]).encode()).hexdigest()
    if cache_key in _opus_cache:
        log.debug("Opus cache hit")
        return _opus_cache[cache_key]

    # Check rate limit
    limit_check = check_opus_rate_limit()
    if not limit_check["allowed"]:
        log.info(f"Opus rate limit: {limit_check.get('reason')}")
        return {"error": f"Rate limit: {limit_check['reason']}", "fallback": True}

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            messages = [{"role": "user", "content": prompt}]

            payload = {
                "model": "claude-sonnet-4-20250514",  # Sonnet 4 - best quality/cost balance
                "max_tokens": max_tokens,
                "messages": messages
            }

            if system:
                payload["system"] = system

            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": LLM_OPUS_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json=payload
            )
            response.raise_for_status()
            data = response.json()

            # Extract text and usage
            content = data.get("content", [])
            usage = data.get("usage", {})

            if content and isinstance(content, list):
                text = content[0].get("text", "")

                # Log the call to audit db
                from app.db import execute_insert
                tokens_in = usage.get("input_tokens", 0)
                tokens_out = usage.get("output_tokens", 0)
                # Sonnet 4 pricing: $3/M input, $15/M output
                cost_usd = (tokens_in * 3.0 / 1_000_000) + (tokens_out * 15.0 / 1_000_000)

                try:
                    execute_insert(
                        "audit",
                        """INSERT INTO opus_calls (tokens_in, tokens_out, cost_usd, query_preview)
                           VALUES (%s, %s, %s, %s)""",
                        (tokens_in, tokens_out, cost_usd, prompt[:200])
                    )
                except Exception:
                    pass  # Table might not exist yet

                result = {"text": text, "usage": usage, "cost_usd": cost_usd}

                # Cache the result
                _opus_cache[cache_key] = result
                if len(_opus_cache) > _OPUS_CACHE_SIZE:
                    _opus_cache.popitem(last=False)

                return result

            return {"error": "Invalid response format", "fallback": True}

    except httpx.HTTPStatusError as e:
        if "credit balance" in str(e.response.text).lower():
            log.warning("Anthropic API: No credits available")
            return {"error": "API credits depleted", "fallback": True}
        log.error(f"Claude API HTTP error: {e}")
        return {"error": f"API error: {str(e)}", "fallback": True}
    except Exception as e:
        log.error(f"Claude API error: {e}")
        return {"error": f"Error calling Claude: {str(e)}", "fallback": True}
