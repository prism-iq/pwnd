#!/opt/rag/venv/bin/python3
"""
Enrich VOL8 documents with entity extraction via Haiku API
PostgreSQL version
"""

import os
import sys
import json
import time
import asyncio
import httpx
import psycopg2
from psycopg2.extras import RealDictCursor
from pathlib import Path

# Load env
env_file = Path("/opt/rag/.env")
for line in env_file.read_text().splitlines():
    if '=' in line and not line.startswith('#'):
        k, v = line.split('=', 1)
        os.environ.setdefault(k, v)

DATABASE_URL = os.environ.get('DATABASE_URL')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')

BATCH_SIZE = 5  # docs per API call
CONCURRENCY = 10  # parallel calls
MAX_CHARS = 3000  # chars per doc to send

EXTRACTION_PROMPT = '''Extract entities from these documents. Return JSON only.

DOCUMENTS:
{documents}

Return this exact JSON structure:
{{
  "entities": [
    {{"type": "person", "name": "John Smith", "doc_ids": [1,2]}},
    {{"type": "organization", "name": "Company Inc", "doc_ids": [3]}},
    {{"type": "location", "name": "New York", "doc_ids": [1]}},
    {{"type": "email", "name": "john@example.com", "doc_ids": [2]}},
    {{"type": "date", "name": "2019-07-06", "doc_ids": [1,3]}},
    {{"type": "amount", "name": "$50,000", "doc_ids": [2]}}
  ]
}}

Types: person, organization, location, email, phone, date, amount, event, document, vehicle, property

JSON:'''


def get_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def get_unprocessed_docs(limit=1000):
    """Get docs that haven't been enriched yet"""
    conn = get_conn()
    cur = conn.cursor()

    # Get docs from source 2 (epstein_vol8) that don't have nodes yet
    cur.execute("""
        SELECT d.id, d.filename, c.full_text
        FROM documents d
        JOIN contents c ON d.id = c.doc_id
        WHERE d.source_id = 2
        AND d.id NOT IN (
            SELECT DISTINCT source_id FROM nodes WHERE source_id IS NOT NULL
        )
        LIMIT %s
    """, (limit,))

    docs = cur.fetchall()
    conn.close()
    return docs


def normalize_name(s):
    """Normalize entity name"""
    import re
    return re.sub(r'[^a-z0-9\s]', '', s.lower()).strip()


async def call_haiku(client, docs_batch):
    """Call Haiku API for entity extraction"""

    # Format documents
    doc_text = "\n\n".join([
        f"[DOC {d['id']}] {d['filename']}\n{d['full_text'][:MAX_CHARS]}"
        for d in docs_batch
    ])

    prompt = EXTRACTION_PROMPT.format(documents=doc_text)

    try:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-3-haiku-20240307",
                "max_tokens": 2000,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=60.0
        )

        if response.status_code == 200:
            data = response.json()
            content = data['content'][0]['text']

            # Parse JSON from response
            import re
            match = re.search(r'\{[\s\S]*\}', content)
            if match:
                return json.loads(match.group()), [d['id'] for d in docs_batch]
        else:
            print(f"API error {response.status_code}: {response.text[:200]}")

    except Exception as e:
        print(f"Error: {e}")

    return None, [d['id'] for d in docs_batch]


def save_entities(entities_data, doc_ids):
    """Save extracted entities to nodes table"""
    if not entities_data or 'entities' not in entities_data:
        return 0

    conn = get_conn()
    cur = conn.cursor()

    added = 0
    for ent in entities_data['entities']:
        etype = ent.get('type', 'unknown')
        name = ent.get('name', '').strip()

        if not name or len(name) < 2:
            continue

        norm = normalize_name(name)
        if not norm:
            continue

        # Check if exists
        cur.execute(
            "SELECT id FROM nodes WHERE type=%s AND name_normalized=%s",
            (etype, norm)
        )
        existing = cur.fetchone()

        if not existing:
            # Get first doc_id from this entity
            edoc_ids = ent.get('doc_ids', doc_ids)
            source_id = edoc_ids[0] if edoc_ids else doc_ids[0]

            cur.execute("""
                INSERT INTO nodes (type, name, name_normalized, source_id, created_at, created_by)
                VALUES (%s, %s, %s, %s, NOW(), 'enrich_vol8')
                RETURNING id
            """, (etype, name, norm, source_id))
            added += 1

    conn.commit()
    conn.close()
    return added


async def process_batch(semaphore, client, batch, batch_num, total_batches):
    """Process a single batch with semaphore for rate limiting"""
    async with semaphore:
        result, doc_ids = await call_haiku(client, batch)

        if result:
            added = save_entities(result, doc_ids)
            print(f"[{batch_num}/{total_batches}] +{added} entities from {len(batch)} docs")
            return added
        else:
            print(f"[{batch_num}/{total_batches}] Failed")
            return 0


async def main(limit=10000, concurrency=CONCURRENCY):
    """Main enrichment loop"""

    print(f"Loading unprocessed docs (limit={limit})...")
    docs = get_unprocessed_docs(limit)

    if not docs:
        print("No unprocessed documents found!")
        return

    print(f"Found {len(docs)} docs to process")

    # Create batches
    batches = [docs[i:i+BATCH_SIZE] for i in range(0, len(docs), BATCH_SIZE)]
    total_batches = len(batches)

    print(f"Processing {total_batches} batches with concurrency={concurrency}")

    semaphore = asyncio.Semaphore(concurrency)
    total_added = 0

    async with httpx.AsyncClient() as client:
        tasks = [
            process_batch(semaphore, client, batch, i+1, total_batches)
            for i, batch in enumerate(batches)
        ]

        results = await asyncio.gather(*tasks)
        total_added = sum(r for r in results if r)

    print(f"\nDone! Added {total_added} new entities")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=10000, help='Max docs to process')
    parser.add_argument('--concurrency', type=int, default=CONCURRENCY, help='Parallel API calls')
    parser.add_argument('--dry-run', action='store_true', help='Just count docs')
    args = parser.parse_args()

    if args.dry_run:
        docs = get_unprocessed_docs(args.limit)
        print(f"Would process {len(docs)} documents")
    else:
        asyncio.run(main(args.limit, args.concurrency))
