#!/bin/bash
# Entity Deduplication Script
# Merges duplicate nodes using fuzzy string matching (Levenshtein distance)

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}  Entity Deduplication Tool            ${NC}"
echo -e "${BLUE}=======================================${NC}"
echo ""

# Default parameters
ENTITY=""
MERGE_THRESHOLD=0.85
DRY_RUN=false
AUTO_MERGE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --entity)
            ENTITY="$2"
            shift 2
            ;;
        --merge-threshold)
            MERGE_THRESHOLD="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --auto)
            AUTO_MERGE=true
            shift
            ;;
        *)
            echo "Usage: $0 [--entity 'NAME'] [--merge-threshold 0.85] [--dry-run] [--auto]"
            exit 1
            ;;
    esac
done

echo -e "${YELLOW}Configuration:${NC}"
echo "  Entity filter: ${ENTITY:-all entities}"
echo "  Merge threshold: $MERGE_THRESHOLD (0-1, higher = stricter)"
echo "  Dry run: $DRY_RUN"
echo "  Auto merge: $AUTO_MERGE"
echo ""

# Python script for fuzzy matching
TEMP_DIR="/tmp/dedupe_$(date +%s)"
mkdir -p "$TEMP_DIR"

cat > "$TEMP_DIR/dedupe.py" << 'EOPY'
import os
import sys
import sqlite3
from typing import List, Dict, Tuple
import difflib

ENTITY_FILTER = os.getenv("ENTITY_FILTER", "")
MERGE_THRESHOLD = float(os.getenv("MERGE_THRESHOLD", "0.85"))
DRY_RUN = os.getenv("DRY_RUN", "false") == "true"
AUTO_MERGE = os.getenv("AUTO_MERGE", "false") == "true"

def levenshtein_similarity(s1: str, s2: str) -> float:
    """Calculate similarity ratio between two strings (0-1)"""
    return difflib.SequenceMatcher(None, s1.lower(), s2.lower()).ratio()

def find_duplicates(conn) -> List[Tuple[int, int, float, str, str, str]]:
    """Find potential duplicate nodes using fuzzy matching"""
    cursor = conn.cursor()

    # Get all nodes, optionally filtered
    if ENTITY_FILTER:
        query = """
            SELECT id, name, type
            FROM nodes
            WHERE name LIKE ?
            ORDER BY type, name
        """
        cursor.execute(query, (f"%{ENTITY_FILTER}%",))
    else:
        query = """
            SELECT id, name, type
            FROM nodes
            ORDER BY type, name
        """
        cursor.execute(query)

    nodes = cursor.fetchall()
    duplicates = []

    # Compare each pair within same type
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            id1, name1, type1 = nodes[i]
            id2, name2, type2 = nodes[j]

            # Only compare same type
            if type1 != type2:
                continue

            # Calculate similarity
            similarity = levenshtein_similarity(name1, name2)

            if similarity >= MERGE_THRESHOLD:
                duplicates.append((id1, id2, similarity, name1, name2, type1))

    return duplicates

def merge_nodes(conn, canonical_id: int, duplicate_id: int, canonical_name: str, duplicate_name: str):
    """Merge duplicate_id into canonical_id"""
    cursor = conn.cursor()

    # Update all edges to point to canonical node
    cursor.execute("""
        UPDATE edges
        SET from_node_id = ?
        WHERE from_node_id = ?
    """, (canonical_id, duplicate_id))

    cursor.execute("""
        UPDATE edges
        SET to_node_id = ?
        WHERE to_node_id = ?
    """, (canonical_id, duplicate_id))

    # Create alias entry (if aliases table exists)
    try:
        cursor.execute("""
            INSERT INTO aliases (canonical_node_id, alias_name, confidence)
            VALUES (?, ?, 1.0)
        """, (canonical_id, duplicate_name))
    except sqlite3.OperationalError:
        # aliases table doesn't exist, skip
        pass

    # Delete duplicate node
    cursor.execute("DELETE FROM nodes WHERE id = ?", (duplicate_id,))

    conn.commit()

    print(f"  ✓ Merged '{duplicate_name}' (id={duplicate_id}) → '{canonical_name}' (id={canonical_id})")

def main():
    conn = sqlite3.connect("/opt/rag/db/graph.db")

    print(f"Finding duplicates (threshold={MERGE_THRESHOLD})...", flush=True)
    duplicates = find_duplicates(conn)

    if not duplicates:
        print("No duplicates found.")
        conn.close()
        return

    print(f"Found {len(duplicates)} potential duplicates:")
    print("")

    merged_count = 0

    for id1, id2, similarity, name1, name2, node_type in duplicates:
        print(f"[{node_type}] '{name1}' ↔ '{name2}' (similarity={similarity:.2f})")
        print(f"  Node IDs: {id1} ↔ {id2}")

        if DRY_RUN:
            print("  [DRY RUN] Would merge")
            continue

        # Decide merge direction (keep shorter/cleaner name as canonical)
        if len(name1) <= len(name2):
            canonical_id, canonical_name = id1, name1
            duplicate_id, duplicate_name = id2, name2
        else:
            canonical_id, canonical_name = id2, name2
            duplicate_id, duplicate_name = id1, name1

        if AUTO_MERGE:
            merge_nodes(conn, canonical_id, duplicate_id, canonical_name, duplicate_name)
            merged_count += 1
        else:
            choice = input(f"  Merge '{duplicate_name}' → '{canonical_name}'? (y/n/q): ").strip().lower()

            if choice == 'q':
                print("Aborted.")
                break
            elif choice == 'y':
                merge_nodes(conn, canonical_id, duplicate_id, canonical_name, duplicate_name)
                merged_count += 1
            else:
                print("  Skipped")

        print("")

    conn.close()

    print("")
    print(f"Deduplication complete!")
    print(f"  Duplicates found: {len(duplicates)}")
    print(f"  Merged: {merged_count}")
    print(f"  Skipped: {len(duplicates) - merged_count}")

if __name__ == "__main__":
    main()
EOPY

# Run deduplication
export ENTITY_FILTER="$ENTITY"
export MERGE_THRESHOLD
export DRY_RUN
export AUTO_MERGE

python3 "$TEMP_DIR/dedupe.py"

# Cleanup
rm -rf "$TEMP_DIR"

echo ""
echo -e "${GREEN}=======================================${NC}"
echo -e "${GREEN}  Deduplication Complete!              ${NC}"
echo -e "${GREEN}=======================================${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Check graph.db: sqlite3 /opt/rag/db/graph.db 'SELECT COUNT(*) FROM nodes;'"
echo "  2. Rebuild services: ./scripts/rebuild.sh"
echo ""
