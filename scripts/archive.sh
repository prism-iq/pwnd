#!/bin/bash
# L Investigation Framework - Archive Script
# Creates distributable tarball excluding databases, models, and cache files

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}  L Investigation Framework - Archive ${NC}"
echo -e "${BLUE}=======================================${NC}"
echo ""

# Archive name with timestamp
DATE=$(date +%Y-%m-%d)
ARCHIVE_NAME="l-framework-${DATE}.tar.gz"
ARCHIVE_PATH="/tmp/${ARCHIVE_NAME}"

# Source directory
SOURCE_DIR="/opt/rag"

echo -e "${YELLOW}Configuration:${NC}"
echo "  Source: $SOURCE_DIR"
echo "  Archive: $ARCHIVE_PATH"
echo "  Date: $DATE"
echo ""

echo -e "${GREEN}[1/4]${NC} Creating archive (excluding databases, models, cache)..."

# Create tarball with exclusions
cd "$SOURCE_DIR"
tar -czf "$ARCHIVE_PATH" \
    --exclude="venv" \
    --exclude="__pycache__" \
    --exclude="*.pyc" \
    --exclude="*.pyo" \
    --exclude="*.pyd" \
    --exclude="db/*.db" \
    --exclude="db/*.db-journal" \
    --exclude="db/*.db-wal" \
    --exclude="db/*.db-shm" \
    --exclude="llm/*.gguf" \
    --exclude="llm/*.bin" \
    --exclude="models/*.gguf" \
    --exclude="models/*.bin" \
    --exclude=".env" \
    --exclude=".env.local" \
    --exclude="*.log" \
    --exclude="*.bak" \
    --exclude="*.backup" \
    --exclude=".git" \
    --exclude="tmp" \
    --exclude="temp" \
    --exclude="node_modules" \
    --exclude=".DS_Store" \
    --exclude="*.swp" \
    --exclude="app" \
    --exclude="static/.*.new" \
    --exclude="l-investigation-framework-*.tar.gz" \
    .

echo -e "${GREEN}[2/4]${NC} Verifying archive integrity..."
tar -tzf "$ARCHIVE_PATH" > /dev/null && echo "  ✓ Archive is valid" || {
    echo -e "${RED}  ✗ Archive validation failed${NC}"
    exit 1
}

echo -e "${GREEN}[3/4]${NC} Archive statistics..."
ARCHIVE_SIZE=$(du -h "$ARCHIVE_PATH" | cut -f1)
FILE_COUNT=$(tar -tzf "$ARCHIVE_PATH" | wc -l)

echo "  Size: $ARCHIVE_SIZE"
echo "  Files: $FILE_COUNT"
echo ""

echo -e "${GREEN}[4/4]${NC} Archive contents (first 50 files):"
echo ""
tar -tzf "$ARCHIVE_PATH" | head -50
echo ""
echo "  ... (see full list with: tar -tzf $ARCHIVE_PATH)"
echo ""

echo -e "${GREEN}=======================================${NC}"
echo -e "${GREEN}  Archive Created Successfully!       ${NC}"
echo -e "${GREEN}=======================================${NC}"
echo ""
echo -e "${YELLOW}Location:${NC} $ARCHIVE_PATH"
echo -e "${YELLOW}Size:${NC} $ARCHIVE_SIZE"
echo -e "${YELLOW}Files:${NC} $FILE_COUNT"
echo ""
echo -e "${BLUE}To extract:${NC}"
echo "  tar -xzf $ARCHIVE_PATH"
echo ""
echo -e "${BLUE}Contents:${NC}"
echo "  ✓ Source code (app/, static/, scripts/)"
echo "  ✓ Documentation (docs/, README.md, etc.)"
echo "  ✓ Configuration (config/, .env.example)"
echo "  ✓ Database schemas (db/schema*.sql)"
echo "  ✗ Databases (excluded - data separate)"
echo "  ✗ Models (excluded - download separately)"
echo "  ✗ Virtual environment (excluded - recreate with pip)"
echo ""
