#!/usr/bin/env python3
"""
Bulk ingest text files into documents/contents tables.
Optimized for parallel processing.

Usage:
    python3 bulk_ingest_text.py /path/to/text/files --workers 4
"""

import os
import sys
import hashlib
import argparse
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import psycopg2
from psycopg2.extras import execute_values

# Database URL
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    env_file = Path("/opt/rag/.env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith('DATABASE_URL='):
                DATABASE_URL = line.split('=', 1)[1]
                break

if not DATABASE_URL:
    print("ERROR: DATABASE_URL not found")
    sys.exit(1)


def file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def detect_doc_type(filename: str, content: str) -> str:
    """Detect document type from filename and content"""
    fn = filename.lower()
    c = content.lower()[:2000]

    if 'efta' in fn:
        return 'foia'
    if 'deposition' in fn or ('q.' in c and 'a.' in c):
        return 'deposition'
    if 'from:' in c and 'subject:' in c:
        return 'email'
    if 'transcript' in c:
        return 'transcript'
    if 'court' in c or 'plaintiff' in c or 'defendant' in c:
        return 'court_filing'
    return 'misc'


def get_existing_hashes(conn) -> set:
    """Get all existing file hashes to avoid duplicates"""
    with conn.cursor() as cur:
        cur.execute("SELECT file_hash FROM documents WHERE file_hash IS NOT NULL")
        return {row[0] for row in cur.fetchall()}


def process_file(filepath: Path) -> dict:
    """Process a single file, return data for insertion"""
    try:
        content_bytes = filepath.read_bytes()
        content = content_bytes.decode('utf-8', errors='replace')

        if len(content.strip()) < 50:
            return None

        return {
            'filename': filepath.name,
            'filepath': str(filepath),
            'file_hash': file_hash(content_bytes),
            'doc_type': detect_doc_type(filepath.name, content),
            'origin': 'dataset8_foia',
            'char_count': len(content),
            'content': content
        }
    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return None


def ingest_batch(batch: list, conn) -> int:
    """Insert a batch of documents"""
    if not batch:
        return 0

    inserted = 0
    with conn.cursor() as cur:
        for doc in batch:
            try:
                # Insert document
                cur.execute("""
                    INSERT INTO documents (filename, filepath, file_hash, doc_type, origin, char_count, date_added, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'processed')
                    ON CONFLICT DO NOTHING
                    RETURNING id
                """, (doc['filename'], doc['filepath'], doc['file_hash'], doc['doc_type'],
                      doc['origin'], doc['char_count'], datetime.now()))

                result = cur.fetchone()
                if result:
                    doc_id = result[0]
                    # Insert content
                    cur.execute("""
                        INSERT INTO contents (doc_id, full_text, created_at)
                        VALUES (%s, %s, %s)
                        ON CONFLICT DO NOTHING
                    """, (doc_id, doc['content'], datetime.now()))
                    inserted += 1
            except Exception as e:
                print(f"Error inserting {doc['filename']}: {e}")
                continue

        conn.commit()
    return inserted


def main():
    parser = argparse.ArgumentParser(description='Bulk ingest text files')
    parser.add_argument('input_dir', help='Directory containing text files')
    parser.add_argument('--workers', type=int, default=4, help='Number of parallel workers')
    parser.add_argument('--batch-size', type=int, default=100, help='Batch size for DB inserts')
    parser.add_argument('--limit', type=int, default=0, help='Limit number of files (0=all)')
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        print(f"ERROR: Directory not found: {input_dir}")
        sys.exit(1)

    # Get all text files
    files = list(input_dir.glob('*.txt'))
    if args.limit > 0:
        files = files[:args.limit]

    print(f"Found {len(files)} text files to process")

    # Get existing hashes
    conn = psycopg2.connect(DATABASE_URL)
    existing_hashes = get_existing_hashes(conn)
    print(f"Found {len(existing_hashes)} existing documents in DB")

    # Process files in parallel
    processed = []
    skipped = 0

    print(f"Processing with {args.workers} workers...")
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_file, f): f for f in files}

        for i, future in enumerate(as_completed(futures)):
            result = future.result()
            if result:
                if result['file_hash'] in existing_hashes:
                    skipped += 1
                else:
                    processed.append(result)
                    existing_hashes.add(result['file_hash'])

            if (i + 1) % 500 == 0:
                print(f"  Processed {i + 1}/{len(files)} files...")

    print(f"Processed {len(processed)} new files, skipped {skipped} duplicates")

    # Insert in batches
    if processed:
        print(f"Inserting {len(processed)} documents in batches of {args.batch_size}...")
        total_inserted = 0

        for i in range(0, len(processed), args.batch_size):
            batch = processed[i:i + args.batch_size]
            inserted = ingest_batch(batch, conn)
            total_inserted += inserted
            print(f"  Inserted batch {i // args.batch_size + 1}: {inserted} documents")

        print(f"\nTotal inserted: {total_inserted} documents")

    conn.close()
    print("Done!")


if __name__ == '__main__':
    main()
