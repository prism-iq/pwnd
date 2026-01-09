"""LLM client for Mistral (local) and Haiku (API)"""
import httpx
from typing import Dict, Any, Optional
from app.config import LLM_MISTRAL_URL, LLM_HAIKU_API_KEY

async def call_mistral(prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
    """Call local Mistral LLM"""
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
        return f"Error calling Mistral: {str(e)}"

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
