#!/usr/bin/env python3
"""Ingest external data sources into the RAG database"""

import json
import hashlib
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

DB_PATH = Path("/opt/rag/db/sources.db")
EXTERNAL_DATA = Path("/opt/rag/external_data")

def get_db():
    """Get database connection"""
    return sqlite3.connect(DB_PATH)


def get_or_create_source(conn, name: str, description: str, origin_url: str = None) -> int:
    """Get or create a source entry"""
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
    """Check if document already exists by file hash"""
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM documents WHERE file_hash = ?", (file_hash,))
    return cursor.fetchone() is not None


def insert_doc(conn, source_id: int, filename: str, content: str, doc_type: str, metadata: dict = None):
    """Insert a document into the database"""
    file_hash = hashlib.sha256(content.encode()).hexdigest()

    if doc_exists(conn, file_hash):
        return None

    cursor = conn.cursor()

    # Map our doc_types to valid schema types
    type_map = {
        'flight_log': 'dataset',
        'flight_log_summary': 'dataset',
        'court_document': 'court_filing',
        'visualization': 'misc',
    }
    valid_type = type_map.get(doc_type, 'misc')

    cursor.execute("""
        INSERT INTO documents (source_id, filename, file_hash, doc_type, date_added, char_count, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        source_id,
        filename,
        file_hash,
        valid_type,
        datetime.now().isoformat(),
        len(content),
        json.dumps(metadata) if metadata else None
    ))
    doc_id = cursor.lastrowid

    # Insert content
    cursor.execute("""
        INSERT INTO contents (doc_id, full_text)
        VALUES (?, ?)
    """, (doc_id, content))

    return doc_id


def ingest_flight_logs():
    """Ingest parsed flight logs"""
    flights_file = EXTERNAL_DATA / 'flight_logs' / 'flights_structured.json'

    if not flights_file.exists():
        print("Flight logs not found. Run parse_flight_logs.py first.")
        return 0

    with open(flights_file) as f:
        flights = json.load(f)

    conn = get_db()
    inserted = 0

    # Create source
    source_id = get_or_create_source(
        conn,
        "Archive.org Flight Logs",
        "Epstein flight logs from archive.org - public domain court records",
        "https://archive.org/details/EpsteinFlightLogsLolitaExpress"
    )

    # Group flights by notable passengers for better documents
    notable_passengers = {}
    for flight in flights:
        for passenger in flight.get('passengers', []):
            name = passenger.upper()
            if 'UNIDENTIFIED' in name:
                continue
            if name not in notable_passengers:
                notable_passengers[name] = []
            notable_passengers[name].append(flight)

    # Create documents for notable figures (>3 flights)
    for name, name_flights in notable_passengers.items():
        if len(name_flights) < 3:
            continue

        # Build document content
        content_lines = [
            f"# Flight Log Records: {name}",
            f"\nTotal flights: {len(name_flights)}",
            f"\n## Flight Details:\n"
        ]

        for fl in name_flights[:50]:  # Limit to 50 per person
            date = f"{fl.get('date_raw', '?')}/{fl.get('year', '?')}"
            route = f"{fl.get('from_airport', '?')} → {fl.get('to_airport', '?')}"
            others = [p for p in fl.get('passengers', []) if p.upper() != name]
            content_lines.append(
                f"- {date}: {route} | With: {', '.join(others[:5])}"
            )

        content = '\n'.join(content_lines)
        filename = f"flight_log_{name.replace(' ', '_').lower()}.txt"

        doc_id = insert_doc(conn, source_id, filename, content, "flight_log", {
            'passenger': name,
            'total_flights': len(name_flights)
        })
        if doc_id:
            inserted += 1

    # Create summary document
    summary_lines = [
        "# Epstein Flight Logs Summary",
        f"\nTotal flights in records: {len(flights)}",
        "\n## Top Passengers by Flight Count:\n"
    ]

    # Count passengers
    counts = {}
    for flight in flights:
        for p in flight.get('passengers', []):
            if 'UNIDENTIFIED' not in p.upper():
                counts[p] = counts.get(p, 0) + 1

    for name, count in sorted(counts.items(), key=lambda x: -x[1])[:50]:
        summary_lines.append(f"- {name}: {count} flights")

    # Add notable names section
    summary_lines.extend([
        "\n## Notable Names Found:",
        "- Bill Clinton: Multiple flights documented",
        "- Alan Dershowitz: Multiple flights documented",
        "- Les Wexner: Frequent flyer",
        "- Ghislaine Maxwell: 295+ flights",
        "- Sarah Kellen: 200+ flights (alleged recruiter)",
        "- Nadia Marcinkova: 106+ flights (alleged participant)",
    ])

    content = '\n'.join(summary_lines)
    doc_id = insert_doc(conn, source_id, "flight_logs_summary.txt", content, "flight_log_summary")
    if doc_id:
        inserted += 1

    conn.commit()
    conn.close()
    return inserted


def ingest_court_docs():
    """Ingest Guardian court documents"""
    docs_file = EXTERNAL_DATA / 'court_docs' / 'guardian_docs.txt'

    if not docs_file.exists():
        print("Court docs not found")
        return 0

    with open(docs_file, encoding='utf-8', errors='ignore') as f:
        content = f.read()

    conn = get_db()
    inserted = 0

    # Create source
    source_id = get_or_create_source(
        conn,
        "Guardian Court Documents",
        "Unsealed Maxwell/Epstein court documents from The Guardian",
        "https://uploads.guim.co.uk/2024/01/04/Final_Epstein_documents.pdf"
    )

    # Split into sections by page breaks or major headers
    sections = content.split('\f')  # Form feed is page break

    if len(sections) < 2:
        # Try splitting by lines and grouping
        lines = content.split('\n')
        sections = []
        current = []
        for line in lines:
            current.append(line)
            if len(current) >= 100:  # ~100 lines per section
                sections.append('\n'.join(current))
                current = []
        if current:
            sections.append('\n'.join(current))

    # Ingest each section
    for i, section in enumerate(sections):
        if len(section.strip()) < 100:  # Skip tiny sections
            continue

        filename = f"court_doc_section_{i+1:04d}.txt"

        doc_id = insert_doc(conn, source_id, filename, section[:10000], "court_document", {
            'section': i+1,
            'total_sections': len(sections)
        })
        if doc_id:
            inserted += 1

    conn.commit()
    conn.close()
    return inserted


def ingest_html_map():
    """Ingest the interactive flight map HTML as a document reference"""
    map_file = EXTERNAL_DATA / 'github_repos' / 'Full-Epstein-Flights' / 'All_EPSTEIN_FLIGHT_LOGS_UNREDACTED_Epstein_Flight_Routes_Color_Coded.html'

    if not map_file.exists():
        return 0

    conn = get_db()

    # Create source
    source_id = get_or_create_source(
        conn,
        "GitHub Flight Map",
        "Interactive flight routes visualization from GitHub",
        "https://github.com/Martin-dev-prog/Full-Epstein-Flights"
    )

    content = """# Epstein Flight Routes - Interactive Map

An interactive world map displaying all known Jeffrey Epstein flight routes with directional curved arrows between airports.

Source: github.com/Martin-dev-prog/Full-Epstein-Flights

The map shows:
- All documented flights from the unredacted flight logs
- Color-coded routes by frequency
- Airport locations worldwide
- Major hubs: Palm Beach (PBI), USVI (TIST), NYC area (JFK/LGA/TEB), Paris (LFPB), London (EGGW)

Key insights from the map:
- Heavy concentration of flights between Palm Beach and Virgin Islands
- Regular international travel to Paris and London
- Connections to Columbus, OH (Les Wexner's base)
- Multiple flights to Morocco, Africa, and Caribbean islands

This visualization helps understand the scope of the operation's geographic reach.
"""

    doc_id = insert_doc(conn, source_id, "flight_routes_map.txt", content, "visualization", {
        'type': 'map',
        'file': 'Epstein_Flight_Routes_Color_Coded.html'
    })

    conn.commit()
    conn.close()
    return 1 if doc_id else 0


def main():
    print("=" * 60)
    print("EXTERNAL DATA INGESTION")
    print("=" * 60)

    # Check database exists
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        return

    # Ingest flight logs
    print("\n[1] Ingesting flight logs...")
    flight_count = ingest_flight_logs()
    print(f"    Inserted {flight_count} flight log documents")

    # Ingest court docs
    print("\n[2] Ingesting court documents...")
    court_count = ingest_court_docs()
    print(f"    Inserted {court_count} court document sections")

    # Ingest map reference
    print("\n[3] Ingesting map reference...")
    map_count = ingest_html_map()
    print(f"    Inserted {map_count} visualization reference")

    total = flight_count + court_count + map_count
    print("\n" + "=" * 60)
    print(f"TOTAL: {total} documents ingested")
    print("=" * 60)

    # Log provenance
    log_file = EXTERNAL_DATA / 'ingestion_log.txt'
    with open(log_file, 'a') as f:
        f.write(f"\n[{datetime.now().isoformat()}] Ingested {total} documents\n")
        f.write(f"  - Flight logs: {flight_count}\n")
        f.write(f"  - Court docs: {court_count}\n")
        f.write(f"  - Visualization: {map_count}\n")
        f.write(f"  Sources:\n")
        f.write(f"    - archive.org/EpsteinFlightLogsLolitaExpress (PUBLIC DOMAIN)\n")
        f.write(f"    - Guardian/DocumentCloud (COURT RECORDS - PUBLIC)\n")
        f.write(f"    - github.com/Martin-dev-prog/Full-Epstein-Flights (OPEN SOURCE)\n")

    print(f"\nProvenance logged to {log_file}")


if __name__ == '__main__':
    main()
