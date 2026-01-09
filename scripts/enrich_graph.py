#!/usr/bin/env python3
"""
Graph Enrichment Script - Extract entities, relationships and forensic signals from emails

Now with parallel processing! Uses asyncio.Semaphore to run multiple Haiku API calls concurrently.

Usage:
    python scripts/enrich_graph.py --limit 10 --dry-run          # Test with 10 emails
    python scripts/enrich_graph.py --limit 100 --concurrency 10  # Process 100 emails with 10 parallel calls
    python scripts/enrich_graph.py --concurrency 20              # Process all unprocessed (default: 20 parallel)
    python scripts/enrich_graph.py --no-resume                   # Reprocess everything

Performance:
    - Sequential (old): ~3h35 for 13K emails (1 batch/sec with rate limit)
    - Parallel (new):   ~10-15 min for 13K emails (20 concurrent batches)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import asyncio
import json
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Tuple

import httpx

# Configuration
BATCH_SIZE = 5  # emails per Haiku call
RATE_LIMIT = 1.0  # seconds between calls (only for sequential fallback)
MAX_RETRIES = 3
DEFAULT_CONCURRENCY = 20  # parallel batches
HAIKU_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")


class RateLimitError(Exception):
    """Raised when API returns 429 rate limit error"""
    pass

# Database paths
DB_SOURCES = Path("/opt/rag/db/sources.db")
DB_GRAPH = Path("/opt/rag/db/graph.db")
DB_SCORES = Path("/opt/rag/db/scores.db")
DB_AUDIT = Path("/opt/rag/db/audit.db")

# Haiku extraction prompt
HAIKU_EXTRACTION_PROMPT = '''You are a forensic data extraction system for OSINT investigation. Extract ALL entities, relationships, and signals from these emails.

=== ENTITY TYPES (everything is a node) ===

CORE:
- person (name, normalize: "John Smith" not "JOHN SMITH" not "john")
- email_address
- phone_number
- company / organization
- location (address, city, country, property name)
- amount (keep currency: "$5,000", "€10,000")
- date (ISO format: 2003-04-12)
- time (24h format when possible)

OBJECTS:
- vehicle (plane, car, boat - with registration if available)
- aircraft (tail number critical: N908JE)
- property (real estate, with address)
- document (contract, invoice, file, report)
- account (bank account, crypto wallet, social media handle)
- object (gift, item, product)

EVENTS:
- meeting (scheduled or mentioned)
- flight (origin, destination, date)
- trip (travel mentioned)
- party / gathering
- call (phone call mentioned)
- transaction (payment, transfer)

STATEMENTS (CRITICAL - capture exact meaning):
- claim (allegation, accusation, statement about someone: "X did Y")
- quote (exact words attributed to someone)
- instruction (request, order, task: "please do X", "make sure to Y")
- plan (future intent: "we will", "planning to")
- denial (someone denying something)
- threat (implicit or explicit)
- secret (something marked confidential, "don't tell", "between us")

SIGNALS (forensic flags):
- code_word (word that seems out of context, repeated unusually)
- vague_reference ("the thing", "you know who", "what we discussed")
- missing_context (refers to conversation not in email)
- urgency (unusual rush, "ASAP", "immediately", deadline pressure)
- deletion_request ("delete this", "destroy", "get rid of")
- cash_mention (references to physical cash)
- offshore_mention (tax haven, offshore account, shell company)

=== OUTPUT FORMAT ===

Return ONLY valid JSON. Use the exact Email ID numbers from the input (e.g., 1, 2, 3, not "email_1"):

{{
  "extractions": [
    {{
      "source_id": 1,
      "nodes": [
        {{"name": "Jeffrey Epstein", "type": "person"}},
        {{"name": "jeffrey@epstein.com", "type": "email_address"}},
        {{"name": "$50,000", "type": "amount"}},
        {{"name": "N908JE", "type": "aircraft"}},
        {{"name": "2003-04-12T03:24:00", "type": "datetime"}},
        {{"name": "massage", "type": "code_word", "context": "appears 3x without clear meaning"}},
        {{"name": "Trump had raped her", "type": "claim", "speaker": "witness"}},
        {{"name": "delete this email after reading", "type": "deletion_request"}},
        {{"name": "the thing we discussed", "type": "vague_reference"}}
      ],
      "edges": [
        {{"from": "Jeffrey Epstein", "to": "jeffrey@epstein.com", "type": "has_email"}},
        {{"from": "Jeffrey Epstein", "to": "$50,000", "type": "paid"}},
        {{"from": "Jeffrey Epstein", "to": "N908JE", "type": "owns"}},
        {{"from": "Trump had raped her", "to": "Trump", "type": "accuses"}},
        {{"from": "delete this email", "to": "Jeffrey Epstein", "type": "instructed_by"}}
      ],
      "properties": [
        {{"node": "Jeffrey Epstein", "key": "aliases", "value": "JE, Jeff"}},
        {{"node": "N908JE", "key": "aircraft_type", "value": "Boeing 727"}}
      ],
      "signals": [
        {{"type": "timing_anomaly", "detail": "sent at 03:24 local time"}},
        {{"type": "urgency", "detail": "multiple ASAP references"}},
        {{"type": "language_switch", "detail": "switches to Spanish mid-paragraph"}}
      ]
    }}
  ]
}}

=== RULES ===

1. Extract EVERYTHING - mundane details often matter later
2. Preserve exact wording for claims/quotes/instructions
3. Normalize person names: "John Smith" (not JOHN SMITH, john smith, John SMITH)
4. Keep amounts with currency symbol
5. Dates in ISO format when parseable
6. NO JUDGMENT - no scores, no opinions, no analysis
7. When entity type unclear, use best guess or "unknown"
8. For claims: capture WHO said WHAT about WHOM
9. Flag anything that seems deliberately vague or coded
10. Return one extraction object per email in the batch

=== EMAILS TO PROCESS ===

{emails_formatted}
'''


def get_db_connection(db_path):
    """Get SQLite connection"""
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def get_unprocessed_emails(limit=None, resume=True):
    """Get emails not yet extracted"""
    conn = get_db_connection(DB_SOURCES)
    cursor = conn.cursor()

    if resume:
        # Get emails not in audit log
        audit_conn = get_db_connection(DB_AUDIT)
        audit_cursor = audit_conn.cursor()

        # Get processed email IDs
        audit_cursor.execute("""
            SELECT DISTINCT target_id
            FROM evidence_chain
            WHERE target_type = 'email'
            AND action = 'batch_extracted'
        """)
        processed_ids = {row[0] for row in audit_cursor.fetchall()}
        audit_conn.close()

        # Get all emails
        cursor.execute("""
            SELECT doc_id, subject, date_sent, sender_email, sender_name,
                   recipients_to, recipients_cc, body_text
            FROM emails
            ORDER BY doc_id
        """)
        all_emails = cursor.fetchall()

        # Filter out processed
        emails = [e for e in all_emails if e['doc_id'] not in processed_ids]
    else:
        # Get all emails
        cursor.execute("""
            SELECT doc_id, subject, date_sent, sender_email, sender_name,
                   recipients_to, recipients_cc, body_text
            FROM emails
            ORDER BY doc_id
        """)
        emails = cursor.fetchall()

    conn.close()

    if limit:
        emails = emails[:limit]

    return [dict(e) for e in emails]


def format_email_for_prompt(email: Dict[str, Any]) -> str:
    """Format single email for Haiku prompt"""
    recipients = []

    if email.get('recipients_to'):
        try:
            to_list = json.loads(email['recipients_to']) if isinstance(email['recipients_to'], str) else email['recipients_to']
            for r in to_list:
                if isinstance(r, dict):
                    recipients.append(r.get('email', str(r)))
                else:
                    recipients.append(str(r))
        except:
            recipients.append(str(email['recipients_to']))

    if email.get('recipients_cc'):
        try:
            cc_list = json.loads(email['recipients_cc']) if isinstance(email['recipients_cc'], str) else email['recipients_cc']
            for r in cc_list:
                if isinstance(r, dict):
                    recipients.append(f"{r.get('email', str(r))} (cc)")
                else:
                    recipients.append(f"{r} (cc)")
        except:
            pass

    recipients_str = ", ".join(recipients) if recipients else "N/A"

    body_preview = email.get('body_text', '')[:2000]  # Limit to 2000 chars

    return f"""
---
Email ID: {email['doc_id']}
Date: {email.get('date_sent', 'N/A')}
From: {email.get('sender_email', 'N/A')} ({email.get('sender_name', 'N/A')})
To: {recipients_str}
Subject: {email.get('subject', '(no subject)')}

Body:
{body_preview}
---
"""


async def call_haiku_extract(emails_batch: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Call Haiku API with extraction prompt"""
    if not HAIKU_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set")

    # Format emails for prompt
    emails_formatted = "\n".join([format_email_for_prompt(e) for e in emails_batch])

    prompt = HAIKU_EXTRACTION_PROMPT.format(emails_formatted=emails_formatted)

    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": HAIKU_API_KEY,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json={
                        "model": "claude-3-5-haiku-20241022",
                        "max_tokens": 4096,
                        "messages": [{"role": "user", "content": prompt}]
                    }
                )

                # Check for rate limiting
                if response.status_code == 429:
                    raise RateLimitError("API rate limit exceeded (429)")

                response.raise_for_status()
                data = response.json()

                content = data.get("content", [])
                usage = data.get("usage", {})

                if content and isinstance(content, list):
                    text = content[0].get("text", "")

                    tokens_in = usage.get("input_tokens", 0)
                    tokens_out = usage.get("output_tokens", 0)
                    cost_usd = (tokens_in * 0.80 / 1_000_000) + (tokens_out * 4.00 / 1_000_000)

                    return {
                        "text": text,
                        "usage": usage,
                        "cost_usd": cost_usd
                    }

                return {"error": "Invalid response format"}

        except RateLimitError:
            # Reraise rate limit errors immediately
            raise
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                print(f"  ⚠ Retry {attempt + 1}/{MAX_RETRIES} after error: {e}")
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
            else:
                return {"error": f"Failed after {MAX_RETRIES} attempts: {e}"}

    return {"error": "Unknown error"}


def safe_db_value(value: Any) -> str:
    """Convert any value to a safe database string"""
    if value is None:
        return ''
    if isinstance(value, str):
        return value
    if isinstance(value, (list, dict)):
        # Convert complex types to JSON string
        return json.dumps(value)
    return str(value)


def parse_extraction_result(result: Dict[str, Any], source_ids: List[int]) -> Tuple[Dict[str, Any], str]:
    """Parse Haiku JSON response, handle errors"""
    if "error" in result:
        return None, result["error"]

    try:
        text = result.get("text", "").strip()

        # Remove markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join([l for l in lines if not l.startswith("```")])

        # Try to find JSON in response
        json_start = text.find("{")
        json_end = text.rfind("}") + 1

        if json_start >= 0 and json_end > json_start:
            json_text = text[json_start:json_end]
            data = json.loads(json_text)
            return data, None
        else:
            return None, "No JSON found in response"

    except json.JSONDecodeError as e:
        return None, f"JSON parse error: {e}"
    except Exception as e:
        return None, f"Parse error: {e}"


def insert_nodes(nodes: List[Dict[str, Any]], source_id: int, dry_run: bool = False) -> Dict[str, int]:
    """Insert nodes into graph.db with dedup, return name -> node_id map"""
    if dry_run:
        print(f"    [DRY-RUN] Would insert {len(nodes)} nodes")
        # Return fake IDs for dry run
        return {safe_db_value(node.get('name', '')): i for i, node in enumerate(nodes, 1)}

    conn = get_db_connection(DB_GRAPH)
    cursor = conn.cursor()

    node_id_map = {}

    for node in nodes:
        name = safe_db_value(node.get('name'))
        node_type = safe_db_value(node.get('type', 'unknown'))
        context = safe_db_value(node.get('context', ''))
        speaker = safe_db_value(node.get('speaker', ''))

        if not name:
            continue

        # Normalize name
        name_normalized = name.lower().strip()

        # Check if node exists
        cursor.execute("""
            SELECT id FROM nodes
            WHERE name = ? AND type = ?
        """, (name, node_type))

        existing = cursor.fetchone()

        if existing:
            node_id = existing['id']
        else:
            # Insert new node
            cursor.execute("""
                INSERT INTO nodes (type, name, name_normalized, source_db, source_id, created_by)
                VALUES (?, ?, ?, 'sources', ?, 'haiku_extract')
            """, (node_type, name, name_normalized, source_id))
            node_id = cursor.lastrowid

        node_id_map[name] = node_id

        # Add context/speaker as properties if present
        if context:
            cursor.execute("""
                INSERT INTO properties (node_id, key, value, source_node_id, created_by)
                VALUES (?, 'context', ?, ?, 'haiku_extract')
            """, (node_id, context, source_id))

        if speaker:
            cursor.execute("""
                INSERT INTO properties (node_id, key, value, source_node_id, created_by)
                VALUES (?, 'speaker', ?, ?, 'haiku_extract')
            """, (node_id, speaker, source_id))

    conn.commit()
    conn.close()

    return node_id_map


def insert_edges(edges: List[Dict[str, Any]], node_id_map: Dict[str, int], source_id: int, dry_run: bool = False) -> int:
    """Insert edges, lookup node IDs"""
    if dry_run:
        print(f"    [DRY-RUN] Would insert {len(edges)} edges")
        return len(edges)

    conn = get_db_connection(DB_GRAPH)
    cursor = conn.cursor()

    inserted = 0

    for edge in edges:
        from_name = safe_db_value(edge.get('from'))
        to_name = safe_db_value(edge.get('to'))
        edge_type = safe_db_value(edge.get('type', 'related_to'))
        excerpt = safe_db_value(edge.get('excerpt', ''))

        if not from_name or not to_name:
            continue

        from_id = node_id_map.get(from_name)
        to_id = node_id_map.get(to_name)

        if not from_id or not to_id:
            # Create missing nodes
            if not from_id:
                from_name_norm = from_name.lower().strip() if isinstance(from_name, str) else str(from_name).lower().strip()
                cursor.execute("""
                    INSERT INTO nodes (type, name, name_normalized, source_db, source_id, created_by)
                    VALUES ('unknown', ?, ?, 'sources', ?, 'haiku_extract')
                """, (from_name, from_name_norm, source_id))
                from_id = cursor.lastrowid
                node_id_map[from_name] = from_id

            if not to_id:
                to_name_norm = to_name.lower().strip() if isinstance(to_name, str) else str(to_name).lower().strip()
                cursor.execute("""
                    INSERT INTO nodes (type, name, name_normalized, source_db, source_id, created_by)
                    VALUES ('unknown', ?, ?, 'sources', ?, 'haiku_extract')
                """, (to_name, to_name_norm, source_id))
                to_id = cursor.lastrowid
                node_id_map[to_name] = to_id

        # Insert edge (skip if duplicate)
        cursor.execute("""
            INSERT OR IGNORE INTO edges (from_node_id, to_node_id, type, directed, source_node_id, excerpt, created_by)
            VALUES (?, ?, ?, 1, ?, ?, 'haiku_extract')
        """, (from_id, to_id, edge_type, source_id, excerpt))

        if cursor.rowcount > 0:
            inserted += 1

    conn.commit()
    conn.close()

    return inserted


def insert_properties(properties: List[Dict[str, Any]], node_id_map: Dict[str, int], source_id: int, dry_run: bool = False) -> int:
    """Insert properties"""
    if dry_run:
        print(f"    [DRY-RUN] Would insert {len(properties)} properties")
        return len(properties)

    conn = get_db_connection(DB_GRAPH)
    cursor = conn.cursor()

    inserted = 0

    for prop in properties:
        node_name = safe_db_value(prop.get('node'))
        key = safe_db_value(prop.get('key'))
        value = safe_db_value(prop.get('value'))

        if not node_name or not key or not value:
            continue

        node_id = node_id_map.get(node_name)
        if not node_id:
            continue

        cursor.execute("""
            INSERT INTO properties (node_id, key, value, source_node_id, created_by)
            VALUES (?, ?, ?, ?, 'haiku_extract')
        """, (node_id, key, value, source_id))

        inserted += 1

    conn.commit()
    conn.close()

    return inserted


def insert_signals(signals: List[Dict[str, Any]], source_id: int, dry_run: bool = False) -> int:
    """Insert signals as flags in scores.db"""
    if dry_run:
        print(f"    [DRY-RUN] Would insert {len(signals)} signal flags")
        return len(signals)

    conn = get_db_connection(DB_SCORES)
    cursor = conn.cursor()

    inserted = 0

    for signal in signals:
        signal_type = safe_db_value(signal.get('type', 'unknown'))
        detail = safe_db_value(signal.get('detail', ''))

        cursor.execute("""
            INSERT INTO flags (target_type, target_id, flag_type, description, severity, source_node_id, created_by)
            VALUES ('email', ?, ?, ?, 0, ?, 'haiku_extract')
        """, (source_id, signal_type, detail, source_id))

        inserted += 1

    conn.commit()
    conn.close()

    return inserted


def log_extraction(source_id: int, stats: Dict[str, Any], dry_run: bool = False):
    """Log to audit.db evidence_chain"""
    if dry_run:
        return

    conn = get_db_connection(DB_AUDIT)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO evidence_chain (
            target_type, target_id, action, new_value, reason, created_by
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, (
        'email',
        source_id,
        'batch_extracted',
        json.dumps(stats),
        'Haiku extraction completed',
        'haiku_extract'
    ))

    conn.commit()
    conn.close()


async def process_batch(emails: List[Dict[str, Any]], dry_run: bool = False) -> Dict[str, Any]:
    """Process one batch of emails"""
    batch_stats = {
        'emails': len(emails),
        'nodes': 0,
        'edges': 0,
        'properties': 0,
        'signals': 0,
        'cost_usd': 0.0,
        'tokens_in': 0,
        'tokens_out': 0,
        'errors': []
    }

    print(f"\n  Processing batch of {len(emails)} emails (IDs: {[e['doc_id'] for e in emails]})")

    # Call Haiku
    result = await call_haiku_extract(emails)

    if "error" in result:
        print(f"  ✗ Error: {result['error']}")
        batch_stats['errors'].append(result['error'])
        return batch_stats

    batch_stats['cost_usd'] = result.get('cost_usd', 0.0)
    batch_stats['tokens_in'] = result.get('usage', {}).get('input_tokens', 0)
    batch_stats['tokens_out'] = result.get('usage', {}).get('output_tokens', 0)

    print(f"  ✓ Haiku response: {batch_stats['tokens_in']} in / {batch_stats['tokens_out']} out tokens (${batch_stats['cost_usd']:.4f})")

    # Parse extraction
    source_ids = [e['doc_id'] for e in emails]
    data, error = parse_extraction_result(result, source_ids)

    if error:
        print(f"  ✗ Parse error: {error}")
        batch_stats['errors'].append(error)
        return batch_stats

    # Process each extraction
    extractions = data.get('extractions', [])

    if not extractions:
        print(f"  ⚠ No extractions found in response")
        return batch_stats

    for extraction in extractions:
        source_id = extraction.get('source_id')

        if source_id not in source_ids:
            print(f"  ⚠ Unknown source_id {source_id}, skipping")
            continue

        nodes = extraction.get('nodes', [])
        edges = extraction.get('edges', [])
        properties = extraction.get('properties', [])
        signals = extraction.get('signals', [])

        print(f"    Email #{source_id}: {len(nodes)} nodes, {len(edges)} edges, {len(properties)} props, {len(signals)} signals")

        if dry_run:
            print(f"      [DRY-RUN] Sample nodes: {nodes[:3]}")
            print(f"      [DRY-RUN] Sample edges: {edges[:3]}")

        # Insert
        node_id_map = insert_nodes(nodes, source_id, dry_run)
        edges_count = insert_edges(edges, node_id_map, source_id, dry_run)
        props_count = insert_properties(properties, node_id_map, source_id, dry_run)
        signals_count = insert_signals(signals, source_id, dry_run)

        batch_stats['nodes'] += len(nodes)
        batch_stats['edges'] += edges_count
        batch_stats['properties'] += props_count
        batch_stats['signals'] += signals_count

        # Log extraction
        log_extraction(source_id, {
            'nodes': len(nodes),
            'edges': edges_count,
            'properties': props_count,
            'signals': signals_count
        }, dry_run)

    return batch_stats


async def main(limit=None, dry_run=False, resume=True, batch_size=BATCH_SIZE, concurrency=DEFAULT_CONCURRENCY):
    """Main extraction loop with parallel processing"""
    print("=" * 80)
    print("GRAPH ENRICHMENT - Haiku Extraction (Parallel Mode)")
    print("=" * 80)

    if dry_run:
        print("\n⚠ DRY-RUN MODE - No data will be inserted\n")

    # Get unprocessed emails
    print(f"\nFetching emails (resume={resume}, limit={limit})...")
    emails = get_unprocessed_emails(limit, resume)

    if not emails:
        print("✓ No emails to process")
        return

    print(f"✓ Found {len(emails)} emails to process")

    # Split into batches
    batches = [emails[i:i + batch_size] for i in range(0, len(emails), batch_size)]
    print(f"✓ Split into {len(batches)} batches of {batch_size}")
    print(f"✓ Processing with concurrency = {concurrency}")

    # Shared state for parallel processing
    semaphore = asyncio.Semaphore(concurrency)
    progress_lock = asyncio.Lock()
    completed_count = 0
    total_batches = len(batches)

    # Shared stats
    total_stats = {
        'emails': 0,
        'nodes': 0,
        'edges': 0,
        'properties': 0,
        'signals': 0,
        'cost_usd': 0.0,
        'tokens_in': 0,
        'tokens_out': 0,
        'errors': []
    }
    stats_lock = asyncio.Lock()

    async def process_batch_with_semaphore(batch_idx: int, batch: List[Dict[str, Any]]):
        """Process batch with semaphore control and progress tracking"""
        nonlocal completed_count

        async with semaphore:
            # Show progress
            async with progress_lock:
                print(f"\n[Batch {batch_idx + 1}/{total_batches}] Starting (IDs: {[e['doc_id'] for e in batch]})")

            # Process with retry on rate limit
            max_rate_limit_retries = 3
            for retry in range(max_rate_limit_retries):
                try:
                    batch_stats = await process_batch(batch, dry_run)

                    # Update shared stats
                    async with stats_lock:
                        total_stats['emails'] += batch_stats['emails']
                        total_stats['nodes'] += batch_stats['nodes']
                        total_stats['edges'] += batch_stats['edges']
                        total_stats['properties'] += batch_stats['properties']
                        total_stats['signals'] += batch_stats['signals']
                        total_stats['cost_usd'] += batch_stats['cost_usd']
                        total_stats['tokens_in'] += batch_stats['tokens_in']
                        total_stats['tokens_out'] += batch_stats['tokens_out']
                        total_stats['errors'].extend(batch_stats['errors'])

                    # Update progress
                    async with progress_lock:
                        completed_count += 1
                        print(f"  ✓ Batch {batch_idx + 1}/{total_batches} complete ({completed_count}/{total_batches} total)")

                    return batch_stats

                except RateLimitError as e:
                    if retry < max_rate_limit_retries - 1:
                        backoff = 2 ** (retry + 1)  # 2, 4, 8 seconds
                        async with progress_lock:
                            print(f"  ⚠ Rate limit hit on batch {batch_idx + 1}, waiting {backoff}s before retry {retry + 1}/{max_rate_limit_retries}")
                        await asyncio.sleep(backoff)
                    else:
                        # Log error and return empty stats
                        error_msg = f"Rate limit exceeded after {max_rate_limit_retries} retries: {e}"
                        async with stats_lock:
                            total_stats['errors'].append(error_msg)
                        async with progress_lock:
                            print(f"  ✗ Batch {batch_idx + 1} failed: {error_msg}")
                        return {
                            'emails': 0, 'nodes': 0, 'edges': 0, 'properties': 0,
                            'signals': 0, 'cost_usd': 0.0, 'tokens_in': 0,
                            'tokens_out': 0, 'errors': [error_msg]
                        }
                except Exception as e:
                    # Handle other exceptions
                    error_msg = f"Unexpected error in batch {batch_idx + 1}: {e}"
                    async with stats_lock:
                        total_stats['errors'].append(error_msg)
                    async with progress_lock:
                        print(f"  ✗ Batch {batch_idx + 1} failed: {error_msg}")
                    return {
                        'emails': 0, 'nodes': 0, 'edges': 0, 'properties': 0,
                        'signals': 0, 'cost_usd': 0.0, 'tokens_in': 0,
                        'tokens_out': 0, 'errors': [error_msg]
                    }

    start_time = time.time()

    # Process all batches in parallel
    print(f"\nProcessing {total_batches} batches in parallel...")
    tasks = [process_batch_with_semaphore(i, batch) for i, batch in enumerate(batches)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Handle any uncaught exceptions
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            error_msg = f"Fatal error in batch {i + 1}: {result}"
            total_stats['errors'].append(error_msg)
            print(f"\n✗ {error_msg}")

    elapsed = time.time() - start_time

    # Final report
    print("\n" + "=" * 80)
    print("EXTRACTION COMPLETE")
    print("=" * 80)
    print(f"\nEmails processed:    {total_stats['emails']}")
    print(f"Batches completed:   {completed_count}/{total_batches}")
    print(f"Haiku calls:         {completed_count}")
    print(f"Input tokens:        {total_stats['tokens_in']:,}")
    print(f"Output tokens:       {total_stats['tokens_out']:,}")
    print(f"Estimated cost:      ${total_stats['cost_usd']:.4f}")
    print(f"\nNodes created:       {total_stats['nodes']}")
    print(f"Edges created:       {total_stats['edges']}")
    print(f"Properties created:  {total_stats['properties']}")
    print(f"Signals flagged:     {total_stats['signals']}")
    print(f"\nTime elapsed:        {elapsed:.1f}s")
    print(f"Throughput:          {total_stats['emails'] / elapsed:.1f} emails/sec" if elapsed > 0 else "")

    if total_stats['errors']:
        print(f"\n⚠ Errors encountered: {len(total_stats['errors'])}")
        for error in total_stats['errors'][:5]:
            print(f"  - {error}")
        if len(total_stats['errors']) > 5:
            print(f"  ... and {len(total_stats['errors']) - 5} more")

    if dry_run:
        print("\n⚠ DRY-RUN MODE - No data was inserted")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract entities and relationships from emails using Haiku (parallel mode)"
    )
    parser.add_argument("--limit", type=int, help="Max emails to process")
    parser.add_argument("--dry-run", action="store_true", help="Don't insert, just show what would happen")
    parser.add_argument("--no-resume", action="store_true", help="Reprocess all emails")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE, help=f"Emails per batch (default: {BATCH_SIZE})")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY,
                        help=f"Number of parallel API calls (default: {DEFAULT_CONCURRENCY})")

    args = parser.parse_args()

    try:
        asyncio.run(main(
            limit=args.limit,
            dry_run=args.dry_run,
            resume=not args.no_resume,
            batch_size=args.batch_size,
            concurrency=args.concurrency
        ))
    except KeyboardInterrupt:
        print("\n\n⚠ Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
