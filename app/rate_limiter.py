"""Rate limiting and cost protection for /api/ask endpoint"""
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, Optional
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class RateLimitState:
    """Global rate limiting state"""
    # Concurrent requests
    semaphore: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(10))

    # IP tracking: {ip: [(timestamp, timestamp, ...), ...]}
    ip_requests: Dict[str, list] = field(default_factory=lambda: defaultdict(list))

    # Daily counters
    total_requests_today: int = 0
    last_reset_date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))

    # Queue
    queue_size: int = 0
    MAX_QUEUE_SIZE: int = 20
    MAX_CONCURRENT: int = 10
    MAX_REQUESTS_PER_HOUR_PER_IP: int = 100
    MAX_REQUESTS_PER_DAY: int = 500


# Global state
_state = RateLimitState()


def reset_if_new_day():
    """Reset daily counters if it's a new day"""
    today = datetime.now().strftime("%Y-%m-%d")
    if today != _state.last_reset_date:
        _state.total_requests_today = 0
        _state.last_reset_date = today

        # Clean up old IP request logs (>24h old)
        cutoff = time.time() - 86400
        for ip in list(_state.ip_requests.keys()):
            _state.ip_requests[ip] = [ts for ts in _state.ip_requests[ip] if ts > cutoff]
            if not _state.ip_requests[ip]:
                del _state.ip_requests[ip]


def check_ip_rate_limit(client_ip: str) -> tuple[bool, Optional[str], int]:
    """Check if IP has exceeded rate limit

    Returns:
        (allowed: bool, reason: Optional[str], remaining: int)
    """
    reset_if_new_day()

    now = time.time()
    hour_ago = now - 3600

    # Get requests in last hour
    if client_ip in _state.ip_requests:
        recent_requests = [ts for ts in _state.ip_requests[client_ip] if ts > hour_ago]
        _state.ip_requests[client_ip] = recent_requests

        if len(recent_requests) >= _state.MAX_REQUESTS_PER_HOUR_PER_IP:
            next_reset = min(recent_requests) + 3600
            seconds_until_reset = int(next_reset - now)
            return False, f"Rate limit: {_state.MAX_REQUESTS_PER_HOUR_PER_IP} requests/hour per IP", seconds_until_reset

        remaining = _state.MAX_REQUESTS_PER_HOUR_PER_IP - len(recent_requests)
    else:
        remaining = _state.MAX_REQUESTS_PER_HOUR_PER_IP

    return True, None, remaining


def check_global_daily_limit() -> tuple[bool, Optional[str]]:
    """Check global daily request limit"""
    reset_if_new_day()

    if _state.total_requests_today >= _state.MAX_REQUESTS_PER_DAY:
        return False, f"Daily limit reached: {_state.MAX_REQUESTS_PER_DAY} requests/day"

    return True, None


async def acquire_slot(client_ip: str, timeout: float = 30.0) -> tuple[bool, Optional[str], Dict[str, int]]:
    """Attempt to acquire a request slot with queueing

    Returns:
        (acquired: bool, error_message: Optional[str], headers: dict)
    """
    # Check IP rate limit
    ip_allowed, ip_reason, ip_remaining = check_ip_rate_limit(client_ip)
    if not ip_allowed:
        return False, ip_reason, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(ip_remaining)}

    # Check global daily limit
    global_allowed, global_reason = check_global_daily_limit()
    if not global_allowed:
        return False, global_reason, {"X-RateLimit-Remaining": "0"}

    # Check queue size
    if _state.semaphore.locked() and _state.queue_size >= _state.MAX_QUEUE_SIZE:
        return False, "Server busy: queue full (max 20 requests)", {}

    # Try to acquire semaphore (with queueing)
    _state.queue_size += 1
    try:
        acquired = await asyncio.wait_for(_state.semaphore.acquire(), timeout=timeout)
        if not acquired:
            return False, "Request timeout: waited too long in queue", {}

        # Successfully acquired - record the request
        _state.ip_requests[client_ip].append(time.time())
        _state.total_requests_today += 1

        # Calculate remaining requests
        remaining_ip = _state.MAX_REQUESTS_PER_HOUR_PER_IP - len([
            ts for ts in _state.ip_requests[client_ip]
            if ts > time.time() - 3600
        ])
        remaining_global = _state.MAX_REQUESTS_PER_DAY - _state.total_requests_today
        remaining = min(remaining_ip, remaining_global)

        headers = {
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Limit-Hourly": str(_state.MAX_REQUESTS_PER_HOUR_PER_IP),
            "X-RateLimit-Limit-Daily": str(_state.MAX_REQUESTS_PER_DAY)
        }

        return True, None, headers

    except asyncio.TimeoutError:
        return False, "Request timeout: server busy (waited 30s)", {}
    finally:
        _state.queue_size -= 1


def release_slot():
    """Release a request slot"""
    _state.semaphore.release()


def get_limits_status() -> Dict:
    """Get current rate limit status"""
    reset_if_new_day()

    return {
        "concurrent_slots_available": _state.MAX_CONCURRENT - (_state.MAX_CONCURRENT - _state.semaphore._value),
        "concurrent_max": _state.MAX_CONCURRENT,
        "queue_size": _state.queue_size,
        "queue_max": _state.MAX_QUEUE_SIZE,
        "requests_today": _state.total_requests_today,
        "daily_limit": _state.MAX_REQUESTS_PER_DAY,
        "hourly_limit_per_ip": _state.MAX_REQUESTS_PER_HOUR_PER_IP,
        "reset_date": _state.last_reset_date
    }
