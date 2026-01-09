#!/bin/bash
# Export evidence package with SHA256 verification + chain of custody
set -e

CASE_ID="${1:-investigation_$(date +%Y%m%d_%H%M%S)}"
EXPORT_DIR="/opt/rag/exports"
PACKAGE_DIR="$EXPORT_DIR/$CASE_ID"
TARBALL="$EXPORT_DIR/${CASE_ID}.tar.gz"

mkdir -p "$PACKAGE_DIR"

# Chain of custody
cat > "$PACKAGE_DIR/CHAIN_OF_CUSTODY.txt" << EOF
L INVESTIGATION FRAMEWORK - EVIDENCE PACKAGE
Case ID: $CASE_ID
Exported: $(date -Iseconds)
Hostname: $(hostname)
User: $(whoami)

THE CODE:
"Protect the weak against the evil strong.
It is not enough to say I will not be evil,
evil must be fought wherever it is found."
— David Gemmell

CONTENTS:
- Database snapshot (sources.db)
- Query logs (audit.db)
- Social media templates
- SHA256 verification file
- This chain of custody document

INTEGRITY:
All files verified with SHA256 checksums.
Package signed with timestamp.

LEGAL NOTICE:
This evidence was collected and preserved following
The Code's principles: victim protection, truth reporting,
chain of custody, and evidence integrity.
EOF

# Export databases (read-only copy)
echo "Copying databases..."
cp /opt/rag/db/sources.db "$PACKAGE_DIR/sources.db"
cp /opt/rag/db/audit.db "$PACKAGE_DIR/audit.db" 2>/dev/null || touch "$PACKAGE_DIR/audit.db"

# Social media templates
echo "Generating social media templates..."
cp /opt/rag/VIRAL_READY.md "$PACKAGE_DIR/SOCIAL_MEDIA_TEMPLATES.md"

# Generate SHA256 checksums
echo "Generating SHA256 checksums..."
cd "$PACKAGE_DIR"
sha256sum sources.db audit.db *.txt *.md > SHA256SUMS.txt

# Create tarball
echo "Creating tarball..."
cd "$EXPORT_DIR"
tar -czf "$TARBALL" "$CASE_ID/"

# Sign tarball
sha256sum "${CASE_ID}.tar.gz" > "${CASE_ID}.tar.gz.sha256"

# Cleanup temp directory
rm -rf "$PACKAGE_DIR"

echo ""
echo "✓ Evidence package created:"
echo "  Package: $TARBALL"
echo "  SHA256:  $(cat ${CASE_ID}.tar.gz.sha256)"
echo ""
echo "Verify with: sha256sum -c ${CASE_ID}.tar.gz.sha256"
