#!/opt/rag/venv/bin/python3
"""
L Auto-Ingest System
Drop files in /opt/rag/data/inbox/, this script processes them into the database.

Usage:
    python3 ingest.py                    # Process all inbox
    python3 ingest.py --file path.txt    # Single file
"""

import os
import sys
import hashlib
import json
import re
from pathlib import Path
from datetime import datetime
import requests
import psycopg2
from psycopg2.extras import RealDictCursor

# Add parent dir for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

BASE_DIR = Path("/opt/rag")
INBOX_DIR = BASE_DIR / "data/inbox"
LLM_URL = "http://127.0.0.1:8001/v1/chat/completions"

# Get DATABASE_URL from environment or .env file
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith('DATABASE_URL='):
                DATABASE_URL = line.split('=', 1)[1]
                break

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not found")


def get_db_conn():
    """Get PostgreSQL connection"""
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def file_hash(path):
    """Calculate SHA256 hash of file"""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def detect_type(content):
    """Detect document type from content"""
    c = content.lower()
    if 'from:' in c and 'subject:' in c:
        return 'email'
    if 'deposition' in c or ('q.' in c and 'a.' in c):
        return 'deposition'
    if 'transcript' in c:
        return 'transcript'
    if 'court' in c or 'plaintiff' in c:
        return 'court_filing'
    return 'misc'


def call_llm(prompt):
    """Call local Phi-3 for entity extraction"""
    try:
        r = requests.post(LLM_URL, json={
            "model": "phi-3",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1500,
            "temperature": 0.1
        }, timeout=60)
        if r.ok:
            return r.json()['choices'][0]['message']['content']
    except Exception as e:
        print(f"LLM error: {e}")
    return None


def extract_entities(content):
    """Extract entities using Phi-3"""
    prompt = f"""Extract entities from this document. Return ONLY valid JSON.

Document:
{content[:3000]}

Return format:
{{"persons": ["name1", "name2"], "organizations": ["org1"], "locations": ["loc1"], "emails": ["email@example.com"], "dates": ["2019-07-06"]}}

JSON:"""

    result = call_llm(prompt)
    if result:
        try:
            match = re.search(r'\{[^{}]+\}', result, re.DOTALL)
            if match:
                return json.loads(match.group())
        except:
            pass
    return {}


def normalize(s):
    """Normalize entity name for matching"""
    return re.sub(r'[^a-z0-9\s]', '', s.lower()).strip()


def ingest_file(cur, filepath, source_id):
    """Ingest single file into database"""

    with open(filepath, 'r', errors='ignore') as f:
        content = f.read()

    if len(content.strip()) < 50:
        return None, "too_short"

    fhash = file_hash(filepath)

    # Check if exists
    cur.execute("SELECT 1 FROM documents WHERE file_hash=%s", (fhash,))
    if cur.fetchone():
        return None, "duplicate"

    doc_type = detect_type(content)

    # Insert document
    cur.execute("""
        INSERT INTO documents (source_id, filename, filepath, file_hash, doc_type, char_count, status, date_added)
        VALUES (%s, %s, %s, %s, %s, %s, 'indexed', NOW())
        RETURNING id
    """, (source_id, os.path.basename(filepath), str(filepath), fhash, doc_type, len(content)))
    doc_id = cur.fetchone()['id']

    # Insert content
    cur.execute("""
        INSERT INTO contents (doc_id, full_text, created_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (doc_id) DO UPDATE SET full_text = EXCLUDED.full_text
    """, (doc_id, content))

    # Extract and store entities
    entities = extract_entities(content)
    entities_added = 0

    for etype, items in entities.items():
        node_type = etype.rstrip('s')  # persons -> person
        if node_type == 'date':
            node_type = 'event'
        for item in items:
            if not item or len(item) < 2:
                continue
            norm = normalize(item)
            if not norm:
                continue

            # Get or create node
            cur.execute(
                "SELECT id FROM nodes WHERE type=%s AND name_normalized=%s",
                (node_type, norm)
            )
            existing = cur.fetchone()

            if existing:
                node_id = existing['id']
            else:
                cur.execute("""
                    INSERT INTO nodes (type, name, name_normalized, source_id, created_at, created_by)
                    VALUES (%s, %s, %s, %s, NOW(), 'ingest')
                    RETURNING id
                """, (node_type, item, norm, doc_id))
                node_id = cur.fetchone()['id']
                entities_added += 1

    return doc_id, {"type": doc_type, "entities": entities_added, "chars": len(content)}


async def ingest_with_progress(source_name="inbox_upload"):
    """Generator for SSE progress updates"""

    conn = get_db_conn()
    cur = conn.cursor()

    try:
        # Get or create source
        cur.execute("SELECT id FROM sources WHERE name=%s", (source_name,))
        src = cur.fetchone()
        if src:
            source_id = src['id']
        else:
            cur.execute("""
                INSERT INTO sources (name, date_acquired, created_at)
                VALUES (%s, %s, NOW())
                RETURNING id
            """, (source_name, datetime.now().strftime('%Y-%m-%d')))
            source_id = cur.fetchone()['id']
            conn.commit()

        # Get files
        INBOX_DIR.mkdir(parents=True, exist_ok=True)
        files = list(INBOX_DIR.rglob('*.txt')) + list(INBOX_DIR.rglob('*.eml'))
        total = len(files)

        yield {"type": "start", "total": total, "source": source_name}

        if total == 0:
            yield {"type": "complete", "processed": 0, "skipped": 0, "errors": 0, "message": "No files in inbox"}
            return

        processed = 0
        skipped = 0
        errors = 0

        for i, f in enumerate(files):
            try:
                doc_id, result = ingest_file(cur, str(f), source_id)

                if doc_id:
                    processed += 1
                    yield {
                        "type": "progress",
                        "current": i + 1,
                        "total": total,
                        "file": f.name,
                        "status": "ingested",
                        "details": result
                    }
                    # Move to processed folder
                    processed_dir = INBOX_DIR / "processed"
                    processed_dir.mkdir(exist_ok=True)
                    f.rename(processed_dir / f.name)
                else:
                    skipped += 1
                    yield {
                        "type": "progress",
                        "current": i + 1,
                        "total": total,
                        "file": f.name,
                        "status": "skipped",
                        "reason": result
                    }

                # Commit every 10 files
                if (i + 1) % 10 == 0:
                    conn.commit()

            except Exception as e:
                errors += 1
                yield {
                    "type": "progress",
                    "current": i + 1,
                    "total": total,
                    "file": f.name,
                    "status": "error",
                    "error": str(e)
                }

        conn.commit()

        yield {
            "type": "complete",
            "processed": processed,
            "skipped": skipped,
            "errors": errors,
            "message": f"Ingestion complete: {processed} new, {skipped} skipped, {errors} errors"
        }

    finally:
        cur.close()
        conn.close()


def main():
    import argparse
    import asyncio

    parser = argparse.ArgumentParser()
    parser.add_argument('--file', help='Single file to ingest')
    parser.add_argument('--source', default='manual_ingest', help='Source name')
    args = parser.parse_args()

    if args.file:
        # Single file mode
        conn = get_db_conn()
        cur = conn.cursor()

        cur.execute("SELECT id FROM sources WHERE name=%s", (args.source,))
        src = cur.fetchone()
        if src:
            source_id = src['id']
        else:
            cur.execute("""
                INSERT INTO sources (name, date_acquired, created_at)
                VALUES (%s, %s, NOW())
                RETURNING id
            """, (args.source, datetime.now().strftime('%Y-%m-%d')))
            source_id = cur.fetchone()['id']

        doc_id, result = ingest_file(cur, args.file, source_id)
        conn.commit()

        if doc_id:
            print(f"Ingested: {args.file} -> doc_id={doc_id}")
            print(f"  Details: {result}")
        else:
            print(f"Skipped: {args.file} ({result})")

        conn.close()
    else:
        # Batch mode
        async def run():
            async for event in ingest_with_progress(args.source):
                if event['type'] == 'start':
                    print(f"Starting ingestion of {event['total']} files...")
                elif event['type'] == 'progress':
                    print(f"  [{event['current']}/{event['total']}] {event['file']}: {event['status']}")
                elif event['type'] == 'complete':
                    print(f"\n{event['message']}")

        asyncio.run(run())


if __name__ == "__main__":
    main()
