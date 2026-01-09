# Anti-DDoS Specification

## Budget Constraints
- **30€/mois** STRICT
- Haiku: ~$0.01 per query (3000 tokens)
- Max: 3000 queries/mois = 100/jour

## Rate Limits (Per IP)
- **2 queries/minute** (anti-spam)
- **10 queries/hour** (normal usage)
- **30 queries/day** (abuse protection)

## Global Limits
- **60 queries/hour** (server protection)
- **200 Haiku calls/day** (budget cap)
- **33 USD/month** (hard stop)

## Spam Detection
- Identical query repeated → BLOCK (2 min cooldown)
- Short queries (<3 chars) repeated → BLOCK
- Pattern detection: hash IP + query

## Queue System
- FIFO (first in, first out)
- Max 20 in queue
- 30s timeout
- Fair distribution

## Implementation
- File: `app/rate_limiter.py`
- DB: `audit.db/query_log`
- Logs: IP hash (GDPR), query preview, timestamp
- Check: BEFORE query processing
- Return: HTTP 429 if exceeded

## Error Messages
```json
{
  "error": "Rate limit: 2 queries/min exceeded",
  "retry_after": 60
}
```

## Monitoring
- Track: queries/hour, cost/day, budget remaining
- Alert: 80% budget reached
- Auto-stop: 100% budget reached (resume next month)
