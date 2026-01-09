#!/bin/bash
# Claude Haiku Entity Extraction Script
# Bulk NER (Named Entity Recognition) for email corpus
# DO NOT RUN without .env configured with HAIKU_API_KEY

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}  Entity Extraction Tool (Haiku NER)  ${NC}"
echo -e "${BLUE}=======================================${NC}"
echo ""

# Default parameters
BATCH_SIZE=100
MAX_DOCS=-1
FORCE=false
START_DOC_ID=0

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --batch-size)
            BATCH_SIZE="$2"
            shift 2
            ;;
        --max-docs)
            MAX_DOCS="$2"
            shift 2
            ;;
        --force)
            FORCE=true
            shift
            ;;
        --start)
            START_DOC_ID="$2"
            shift 2
            ;;
        *)
            echo "Usage: $0 [--batch-size N] [--max-docs N] [--force] [--start DOC_ID]"
            exit 1
            ;;
    esac
done

# Check for .env
if [ ! -f "/opt/rag/.env" ]; then
    echo -e "${RED}Error: .env file not found${NC}"
    echo "Create .env with HAIKU_API_KEY=sk-ant-..."
    exit 1
fi

# Load .env
set -a
source /opt/rag/.env
set +a

if [ -z "$HAIKU_API_KEY" ]; then
    echo -e "${RED}Error: HAIKU_API_KEY not set in .env${NC}"
    exit 1
fi

echo -e "${YELLOW}Configuration:${NC}"
echo "  Batch size: $BATCH_SIZE emails per API call"
echo "  Max docs: ${MAX_DOCS} (use -1 for all)"
echo "  Force re-extract: $FORCE"
echo "  Start doc_id: $START_DOC_ID"
echo ""

# Count total emails to process
if [ "$FORCE" == "true" ]; then
    TOTAL_EMAILS=$(sqlite3 /opt/rag/db/sources.db "SELECT COUNT(*) FROM emails WHERE doc_id >= $START_DOC_ID;")
else
    # Only process emails not yet in graph.nodes
    TOTAL_EMAILS=$(sqlite3 /opt/rag/db/sources.db "SELECT COUNT(*) FROM emails e WHERE doc_id >= $START_DOC_ID AND NOT EXISTS (SELECT 1 FROM (SELECT DISTINCT source_id FROM nodes WHERE source_db = 'sources') n WHERE n.source_id = e.doc_id);" 2>/dev/null || echo 0)
fi

if [ "$MAX_DOCS" -ne -1 ] && [ "$TOTAL_EMAILS" -gt "$MAX_DOCS" ]; then
    TOTAL_EMAILS=$MAX_DOCS
fi

echo -e "${BLUE}Emails to process: $TOTAL_EMAILS${NC}"

if [ "$TOTAL_EMAILS" -eq 0 ]; then
    echo -e "${GREEN}No emails to process. Use --force to re-extract all.${NC}"
    exit 0
fi

# Estimate API cost
BATCHES=$((TOTAL_EMAILS / BATCH_SIZE + 1))
EST_TOKENS=$((TOTAL_EMAILS * 500))  # ~500 tokens per email avg
EST_COST=$(echo "scale=2; $EST_TOKENS / 1000000 * 0.25" | bc)

echo -e "${YELLOW}Estimated:${NC}"
echo "  API calls: $BATCHES"
echo "  Input tokens: ~$EST_TOKENS"
echo "  Cost: ~\$${EST_COST} (at \$0.25 per 1M tokens)"
echo ""

read -p "Continue? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "Aborted."
    exit 0
fi

# Create temp directory for batch processing
TEMP_DIR="/tmp/entity_extraction_$(date +%s)"
mkdir -p "$TEMP_DIR"

echo -e "${GREEN}Starting extraction...${NC}"
echo ""

# Python script for batch processing
cat > "$TEMP_DIR/extract.py" << 'EOPY'
import os
import sys
import json
import sqlite3
import anthropic
import time
from typing import List, Dict, Any

BATCH_SIZE = int(os.getenv("BATCH_SIZE", "100"))
MAX_DOCS = int(os.getenv("MAX_DOCS", "-1"))
FORCE = os.getenv("FORCE", "false") == "true"
START_DOC_ID = int(os.getenv("START_DOC_ID", "0"))
HAIKU_API_KEY = os.getenv("HAIKU_API_KEY")

client = anthropic.Anthropic(api_key=HAIKU_API_KEY)

def get_emails_batch(conn_sources, offset: int, limit: int) -> List[Dict]:
    """Fetch batch of emails from sources.db"""
    cursor = conn_sources.cursor()

    if FORCE:
        query = """
            SELECT doc_id, subject, sender_name, sender_email, body_text
            FROM emails
            WHERE doc_id >= ?
            ORDER BY doc_id
            LIMIT ? OFFSET ?
        """
        cursor.execute(query, (START_DOC_ID, limit, offset))
    else:
        # Only unprocessed emails
        query = """
            SELECT e.doc_id, e.subject, e.sender_name, e.sender_email, e.body_text
            FROM emails e
            WHERE e.doc_id >= ?
              AND NOT EXISTS (
                  SELECT 1 FROM (SELECT DISTINCT source_id FROM nodes WHERE source_db = 'sources') n
                  WHERE n.source_id = e.doc_id
              )
            ORDER BY e.doc_id
            LIMIT ? OFFSET ?
        """
        cursor.execute(query, (START_DOC_ID, limit, offset))

    rows = cursor.fetchall()
    return [
        {
            "doc_id": r[0],
            "subject": r[1] or "",
            "sender_name": r[2] or "",
            "sender_email": r[3] or "",
            "body": (r[4] or "")[:2000]  # Truncate to 2000 chars
        }
        for r in rows
    ]

def extract_entities_batch(emails: List[Dict]) -> Dict[str, Any]:
    """Call Haiku API for batch entity extraction"""

    # Format emails for prompt
    email_texts = []
    for i, email in enumerate(emails):
        text = f"""Email {i+1} (doc_id={email['doc_id']}):
Subject: {email['subject']}
From: {email['sender_name']} <{email['sender_email']}>
Body: {email['body'][:1000]}
---"""
        email_texts.append(text)

    prompt = f"""Extract entities and relationships from these {len(emails)} emails.

For each email, identify:
1. **Entities**: People, organizations, locations, dates, amounts, objects
2. **Relationships**: Connections between entities (e.g., "works_for", "sent_email_to", "owns")

Return JSON in this exact format:
{{
    "emails": [
        {{
            "doc_id": 123,
            "entities": [
                {{"name": "Jeffrey Epstein", "type": "person", "confidence": 0.95}},
                {{"name": "Little St. James", "type": "location", "confidence": 0.9}}
            ],
            "relationships": [
                {{"from": "Jeffrey Epstein", "to": "Little St. James", "type": "owns_property", "excerpt": "Epstein owns the island"}}
            ]
        }}
    ]
}}

Entity types: person, organization, location, date, amount, email_address, phone, document, event, object, unknown

Relationship types: sent_email_to, knows, works_for, owns_property, associated_with, mentioned_with, attended, signed, transferred_money, connection_invite

Focus on substantive entities (not spam like "Amazon Customer Service").

Emails:

{chr(10).join(email_texts)}

JSON:"""

    try:
        response = client.messages.create(
            model="claude-haiku-4-20250115",
            max_tokens=4000,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}]
        )

        # Parse JSON response
        content = response.content[0].text.strip()

        # Remove markdown code fences if present
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join([l for l in lines if not l.startswith("```")])

        result = json.loads(content.strip())

        return result

    except Exception as e:
        print(f"  ✗ API error: {e}", file=sys.stderr)
        return {"emails": []}

def insert_entities(conn_graph, doc_id: int, entities: List[Dict], relationships: List[Dict]):
    """Insert extracted entities and relationships into graph.db"""
    cursor = conn_graph.cursor()

    entity_map = {}  # name -> node_id

    # Insert entities as nodes
    for entity in entities:
        name = entity.get("name", "").strip()
        entity_type = entity.get("type", "unknown")
        confidence = entity.get("confidence", 1.0)

        if not name:
            continue

        # Check if entity already exists
        cursor.execute("""
            SELECT id FROM nodes
            WHERE name = ? AND type = ?
            LIMIT 1
        """, (name, entity_type))

        existing = cursor.fetchone()

        if existing:
            node_id = existing[0]
        else:
            # Insert new node
            cursor.execute("""
                INSERT INTO nodes (type, name, name_normalized, source_db, source_id, created_by)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (entity_type, name, name.lower(), "sources", doc_id, "haiku_extraction"))

            node_id = cursor.lastrowid

        entity_map[name] = node_id

    # Insert relationships as edges
    for rel in relationships:
        from_name = rel.get("from", "").strip()
        to_name = rel.get("to", "").strip()
        rel_type = rel.get("type", "associated_with")
        excerpt = rel.get("excerpt", "")

        if not from_name or not to_name:
            continue

        from_id = entity_map.get(from_name)
        to_id = entity_map.get(to_name)

        if not from_id or not to_id:
            continue

        # Insert edge
        cursor.execute("""
            INSERT INTO edges (from_node_id, to_node_id, type, excerpt, created_by)
            VALUES (?, ?, ?, ?, ?)
        """, (from_id, to_id, rel_type, excerpt, "haiku_extraction"))

    conn_graph.commit()

def main():
    conn_sources = sqlite3.connect("/opt/rag/db/sources.db")
    conn_graph = sqlite3.connect("/opt/rag/db/graph.db")

    # Count total
    total = MAX_DOCS if MAX_DOCS != -1 else conn_sources.execute(
        "SELECT COUNT(*) FROM emails WHERE doc_id >= ?", (START_DOC_ID,)
    ).fetchone()[0]

    processed = 0
    entities_count = 0
    relationships_count = 0

    while processed < total:
        batch = get_emails_batch(conn_sources, processed, BATCH_SIZE)

        if not batch:
            break

        print(f"[{processed+1}/{total}] Processing batch of {len(batch)} emails...", end=" ", flush=True)

        # Extract entities
        result = extract_entities_batch(batch)

        # Insert into graph.db
        for email_result in result.get("emails", []):
            doc_id = email_result.get("doc_id")
            entities = email_result.get("entities", [])
            relationships = email_result.get("relationships", [])

            if entities or relationships:
                insert_entities(conn_graph, doc_id, entities, relationships)
                entities_count += len(entities)
                relationships_count += len(relationships)

        print(f"✓ (+{entities_count} entities, +{relationships_count} rels)")

        processed += len(batch)

        # Rate limiting: 5 req/sec = 200ms between requests
        time.sleep(0.2)

    conn_sources.close()
    conn_graph.close()

    print("")
    print(f"Extraction complete!")
    print(f"  Processed: {processed} emails")
    print(f"  Entities: {entities_count}")
    print(f"  Relationships: {relationships_count}")

if __name__ == "__main__":
    main()
EOPY

# Run extraction
export BATCH_SIZE
export MAX_DOCS
export FORCE
export START_DOC_ID
export HAIKU_API_KEY

python3 "$TEMP_DIR/extract.py"

# Cleanup
rm -rf "$TEMP_DIR"

echo ""
echo -e "${GREEN}=======================================${NC}"
echo -e "${GREEN}  Extraction Complete!                 ${NC}"
echo -e "${GREEN}=======================================${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Check graph.db: sqlite3 /opt/rag/db/graph.db 'SELECT COUNT(*) FROM nodes;'"
echo "  2. Deduplicate entities: ./scripts/deduplicate_entities.sh"
echo "  3. Restart services: ./scripts/rebuild.sh"
echo ""
