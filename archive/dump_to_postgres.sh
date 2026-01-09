#!/bin/bash
# Simple SQLite → PostgreSQL dump and load

DB_NAMES=("sources" "graph" "audit" "sessions" "scores")

echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║  SQLite Dump → PostgreSQL Load                                  ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""

for db in "${DB_NAMES[@]}"; do
    echo "════════════════════════════════════════════════════════════════════"
    echo "  ${db}.db"
    echo "════════════════════════════════════════════════════════════════════"

    # Skip if database doesn't exist
    if [ ! -f "/opt/rag/db/${db}.db" ]; then
        echo "  ⚠ File not found, skipping"
        continue
    fi

    # Dump SQLite
    echo "  → Dumping SQLite schema and data..."
    sqlite3 /opt/rag/db/${db}.db .dump > /tmp/${db}_dump.sql

    # Transform for PostgreSQL
    echo "  → Transforming SQL syntax..."
    sed -i 's/AUTOINCREMENT//' /tmp/${db}_dump.sql
    sed -i 's/DATETIME/TIMESTAMP/g' /tmp/${db}_dump.sql
    sed -i "s/datetime('now')/NOW()/g" /tmp/${db}_dump.sql
    sed -i 's/CURRENT_TIMESTAMP/NOW()/g' /tmp/${db}_dump.sql
    sed -i '/^CREATE TABLE.*_fts/,/);$/d' /tmp/${db}_dump.sql  # Remove FTS tables
    sed -i '/^INSERT INTO.*_fts/d' /tmp/${db}_dump.sql  # Remove FTS inserts
    sed -i 's/^BEGIN TRANSACTION/BEGIN/g' /tmp/${db}_dump.sql
    sed -i 's/^COMMIT/COMMIT/g' /tmp/${db}_dump.sql

    # Count lines
    lines=$(wc -l < /tmp/${db}_dump.sql)
    echo "  → SQL dump: $lines lines"

    # Load to PostgreSQL
    echo "  → Loading to PostgreSQL..."
    export PGPASSWORD='secure_pw_2026'
    psql -U lframework -d ldb -f /tmp/${db}_dump.sql 2>&1 | head -20

    echo ""
done

echo "════════════════════════════════════════════════════════════════════"
echo "  Verifying tables..."
echo "════════════════════════════════════════════════════════════════════"

export PGPASSWORD='secure_pw_2026'
psql -U lframework -d ldb -c "\dt" | head -30
