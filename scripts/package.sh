#!/bin/bash
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}Creating GitHub release package...${NC}"
echo ""

# Package name
PACKAGE_NAME="l-investigation-framework"
PACKAGE_VERSION="1.0.0"
PACKAGE_FILE="${PACKAGE_NAME}-${PACKAGE_VERSION}.tar.gz"

# Create temporary directory structure
TEMP_DIR="/tmp/${PACKAGE_NAME}"
rm -rf "$TEMP_DIR"
mkdir -p "$TEMP_DIR"

echo -e "${GREEN}[1/4]${NC} Copying files..."

# Copy application files
cp -r app "$TEMP_DIR/"
cp -r static "$TEMP_DIR/"
cp -r scripts "$TEMP_DIR/"
cp -r modules "$TEMP_DIR/" 2>/dev/null || true
cp -r templates "$TEMP_DIR/" 2>/dev/null || true

# Copy configuration files
cp install.sh "$TEMP_DIR/"
cp requirements.txt "$TEMP_DIR/"
cp README.md "$TEMP_DIR/"
cp LICENSE "$TEMP_DIR/"
cp .gitignore "$TEMP_DIR/"
cp .env.example "$TEMP_DIR/"
cp Caddyfile "$TEMP_DIR/" 2>/dev/null || echo "Caddyfile" > "$TEMP_DIR/Caddyfile"
cp backend.py "$TEMP_DIR/" 2>/dev/null || true

# Copy database schemas (NOT data)
mkdir -p "$TEMP_DIR/db"
cp db/schema*.sql "$TEMP_DIR/db/" 2>/dev/null || true

# Create models directory with README
mkdir -p "$TEMP_DIR/models"
cp models/README.md "$TEMP_DIR/models/" 2>/dev/null || echo "Download Mistral 7B model here" > "$TEMP_DIR/models/README.md"

echo -e "${GREEN}[2/4]${NC} Excluding large files..."
# .gitignore already handles this

echo -e "${GREEN}[3/4]${NC} Creating tarball..."
cd /tmp
tar -czf "$PACKAGE_FILE" "$PACKAGE_NAME/"

# Move to original directory
mv "$PACKAGE_FILE" /opt/rag/

echo -e "${GREEN}[4/4]${NC} Cleanup..."
rm -rf "$TEMP_DIR"

echo ""
echo -e "${GREEN}Package created:${NC} ${YELLOW}/opt/rag/$PACKAGE_FILE${NC}"
echo ""
echo -e "${BLUE}Package contents:${NC}"
tar -tzf "/opt/rag/$PACKAGE_FILE" | head -20
echo "  ... (see full list with: tar -tzf $PACKAGE_FILE)"
echo ""
echo -e "${YELLOW}Upload to GitHub:${NC}"
echo "  1. Create new release on GitHub"
echo "  2. Upload $PACKAGE_FILE as asset"
echo "  3. Users download and run: tar -xzf $PACKAGE_FILE && cd $PACKAGE_NAME && sudo ./install.sh"
echo ""
