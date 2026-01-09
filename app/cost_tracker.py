"""Cost tracking and protection for Haiku API calls"""
from datetime import datetime
from typing import Dict, Optional
from app.db import execute_query, execute_insert


# Cost limits
HAIKU_DAILY_BUDGET_USD = 5.00  # $5/day hard limit
HAIKU_COST_PER_1M_INPUT_TOKENS = 0.80  # $0.80 per 1M input tokens
HAIKU_COST_PER_1M_OUTPUT_TOKENS = 4.00  # $4.00 per 1M output tokens


def init_cost_tracking_table():
    """Initialize api_costs table in scores.db (PostgreSQL)"""
    from app.db import get_db

    with get_db("scores") as conn:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_costs (
                date TEXT PRIMARY KEY,
                haiku_calls INTEGER DEFAULT 0,
                estimated_cost_usd REAL DEFAULT 0.0,
                last_updated TIMESTAMP DEFAULT NOW()
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_api_costs_date ON api_costs(date)
        """)

        conn.commit()


def get_today_cost() -> Dict[str, any]:
    """Get today's Haiku API cost stats

    Returns:
        {
            "date": "2026-01-07",
            "calls": 42,
            "cost_usd": 0.234,
            "budget_usd": 5.00,
            "remaining_usd": 4.766,
            "budget_exceeded": False
        }
    """
    today = datetime.now().strftime("%Y-%m-%d")

    # Get from scores.db
    result = execute_query(
        "scores",
        "SELECT haiku_calls, estimated_cost_usd FROM api_costs WHERE date = %s",
        (today,)
    )

    if result:
        calls = result[0]["haiku_calls"]
        cost = result[0]["estimated_cost_usd"]
    else:
        calls = 0
        cost = 0.0

    remaining = HAIKU_DAILY_BUDGET_USD - cost
    exceeded = cost >= HAIKU_DAILY_BUDGET_USD

    return {
        "date": today,
        "calls": calls,
        "cost_usd": round(cost, 4),
        "budget_usd": HAIKU_DAILY_BUDGET_USD,
        "remaining_usd": round(max(0, remaining), 4),
        "budget_exceeded": exceeded
    }


def check_budget_available() -> tuple[bool, Optional[str]]:
    """Check if Haiku budget is available

    Returns:
        (allowed: bool, reason: Optional[str])
    """
    stats = get_today_cost()

    if stats["budget_exceeded"]:
        return False, f"Daily Haiku budget exceeded (${stats['budget_usd']}/day limit)"

    return True, None


def record_haiku_call(tokens_in: int, tokens_out: int) -> float:
    """Record a Haiku API call and return cost

    Args:
        tokens_in: Input tokens used
        tokens_out: Output tokens used

    Returns:
        cost_usd: Estimated cost in USD
    """
    # Calculate cost
    cost_usd = (
        (tokens_in * HAIKU_COST_PER_1M_INPUT_TOKENS / 1_000_000) +
        (tokens_out * HAIKU_COST_PER_1M_OUTPUT_TOKENS / 1_000_000)
    )

    today = datetime.now().strftime("%Y-%m-%d")

    # Update api_costs table in scores.db (PostgreSQL)
    from app.db import get_db

    with get_db("scores") as conn:
        cursor = conn.cursor()

        # Insert or update (PostgreSQL syntax)
        cursor.execute("""
            INSERT INTO api_costs (date, haiku_calls, estimated_cost_usd, last_updated)
            VALUES (%s, 1, %s, NOW())
            ON CONFLICT(date) DO UPDATE SET
                haiku_calls = haiku_calls + 1,
                estimated_cost_usd = estimated_cost_usd + %s,
                last_updated = NOW()
        """, (today, cost_usd, cost_usd))

        conn.commit()

    return cost_usd


def get_fallback_response() -> Dict[str, any]:
    """Get fallback response when budget is exceeded"""
    stats = get_today_cost()

    return {
        "findings": [
            f"Service limit reached: ${stats['budget_usd']}/day Haiku budget exceeded",
            f"Used: ${stats['cost_usd']} across {stats['calls']} calls today",
            "Try again tomorrow or contact admin to increase budget"
        ],
        "sources": [],
        "confidence": "low",
        "hypotheses": [],
        "contradictions": [],
        "suggested_queries": []
    }


# Initialize table on import
init_cost_tracking_table()
