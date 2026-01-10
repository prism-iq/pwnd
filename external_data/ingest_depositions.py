#!/usr/bin/env python3
"""Ingest depositions and interview transcripts"""

import json
import hashlib
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path("/opt/rag/db/sources.db")
TEXT_DIR = Path("/opt/rag/data/extracted/text")
CSV_DIR = Path("/opt/rag/data/extracted")

def get_db():
    return sqlite3.connect(DB_PATH)

def get_or_create_source(conn, name: str, description: str, origin_url: str = None) -> int:
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM sources WHERE name = ?", (name,))
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor.execute("""
        INSERT INTO sources (name, description, origin_url, date_acquired)
        VALUES (?, ?, ?, ?)
    """, (name, description, origin_url, datetime.now().date().isoformat()))
    return cursor.lastrowid

def doc_exists(conn, file_hash: str) -> bool:
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM documents WHERE file_hash = ?", (file_hash,))
    return cursor.fetchone() is not None

def insert_doc(conn, source_id: int, filename: str, content: str, doc_type: str, metadata: dict = None):
    file_hash = hashlib.sha256(content.encode()).hexdigest()
    if doc_exists(conn, file_hash):
        return None

    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO documents (source_id, filename, file_hash, doc_type, date_added, char_count, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (source_id, filename, file_hash, doc_type, datetime.now().isoformat(), len(content),
          json.dumps(metadata) if metadata else None))
    doc_id = cursor.lastrowid

    cursor.execute("INSERT INTO contents (doc_id, full_text) VALUES (?, ?)", (doc_id, content))
    return doc_id

def chunk_text(text: str, chunk_size: int = 4000, overlap: int = 200) -> list:
    """Split text into overlapping chunks"""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start = end - overlap
    return chunks

def ingest_text_files():
    """Ingest text depositions and transcripts"""
    if not TEXT_DIR.exists():
        print("Text directory not found")
        return 0

    conn = get_db()
    inserted = 0

    # Create source
    source_id = get_or_create_source(
        conn,
        "Depositions & Transcripts",
        "Court depositions and DOJ interview transcripts",
        "DOJ/Court Records"
    )

    for txt_file in TEXT_DIR.glob("*.txt"):
        print(f"  Processing {txt_file.name}...")
        content = txt_file.read_text(encoding='utf-8', errors='ignore')

        # Determine doc type
        name = txt_file.name.lower()
        if 'maxwell' in name and 'interview' in name:
            doc_type = 'transcript'
        elif 'deposition' in name:
            doc_type = 'deposition'
        else:
            doc_type = 'transcript'

        # For large files, chunk them
        if len(content) > 50000:
            chunks = chunk_text(content, 10000, 500)
            for i, chunk in enumerate(chunks):
                chunk_filename = f"{txt_file.stem}_chunk_{i+1:03d}.txt"
                doc_id = insert_doc(conn, source_id, chunk_filename, chunk, doc_type, {
                    'original_file': txt_file.name,
                    'chunk': i+1,
                    'total_chunks': len(chunks)
                })
                if doc_id:
                    inserted += 1
        else:
            doc_id = insert_doc(conn, source_id, txt_file.name, content, doc_type)
            if doc_id:
                inserted += 1

    conn.commit()
    conn.close()
    return inserted

def ingest_csv_data():
    """Ingest CSV datasets as documents"""
    if not CSV_DIR.exists():
        return 0

    conn = get_db()
    inserted = 0

    source_id = get_or_create_source(
        conn,
        "House Oversight Nov 2025",
        "20,000 pages from House Committee on Oversight - November 2025 release",
        "House Oversight Committee"
    )

    # Process the main CSV files
    csv_files = [
        "EPS_FILES_20K_NOV2025.csv",
        "dataset_text_extract.csv",
        "giuffre-v-maxwell.nysd.4355835.2025-12-21.csv"
    ]

    import csv
    csv.field_size_limit(10_000_000)  # 10MB field limit

    for csv_name in csv_files:
        csv_path = CSV_DIR / csv_name
        if not csv_path.exists():
            continue

        print(f"  Processing {csv_name}...")

        # Read CSV and extract text content
        try:
            with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        except Exception as e:
            print(f"    Error reading {csv_name}: {e}")
            continue

        print(f"    Found {len(rows)} rows")

        # For large CSVs, group by document/batch
        batch_size = 100
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i+batch_size]

            # Build content from batch
            content_lines = [f"# {csv_name} - Batch {i//batch_size + 1}\n"]
            for row in batch:
                # Try common column names for text content
                text = row.get('text') or row.get('content') or row.get('body') or row.get('full_text') or ''
                title = row.get('title') or row.get('filename') or row.get('subject') or ''

                if text or title:
                    content_lines.append(f"## {title}\n{text[:2000]}\n")

            content = '\n'.join(content_lines)
            if len(content) > 500:  # Only insert if meaningful content
                filename = f"{csv_name.replace('.csv', '')}_batch_{i//batch_size + 1:04d}.txt"
                doc_id = insert_doc(conn, source_id, filename, content[:15000], 'dataset', {
                    'source_csv': csv_name,
                    'batch': i//batch_size + 1,
                    'rows': len(batch)
                })
                if doc_id:
                    inserted += 1

    conn.commit()
    conn.close()
    return inserted

def main():
    print("=" * 60)
    print("DEPOSITIONS & TRANSCRIPTS INGESTION")
    print("=" * 60)

    print("\n[1] Ingesting text files (depositions, transcripts)...")
    text_count = ingest_text_files()
    print(f"    Inserted {text_count} documents")

    print("\n[2] Ingesting CSV datasets...")
    csv_count = ingest_csv_data()
    print(f"    Inserted {csv_count} documents")

    total = text_count + csv_count
    print("\n" + "=" * 60)
    print(f"TOTAL: {total} documents ingested")
    print("=" * 60)

if __name__ == '__main__':
    main()
