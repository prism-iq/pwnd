#!/bin/bash
# Process dataset8: Extract PDFs and convert to text
# 11,033 PDFs, ~10GB

set -e

DATASET_ZIP="/opt/rag/data/import/dataset8.zip"
EXTRACT_DIR="/opt/rag/data/import/dataset8_full"
TEXT_DIR="/opt/rag/data/import/dataset8_text"
LOG_FILE="/tmp/dataset8_progress.log"

echo "=== Dataset8 Processing ===" | tee $LOG_FILE
echo "Started: $(date)" | tee -a $LOG_FILE

# Create directories
mkdir -p "$EXTRACT_DIR" "$TEXT_DIR"

# Step 1: Extract ZIP (if not already done)
if [ ! -f "$EXTRACT_DIR/.extracted" ]; then
    echo "[1/3] Extracting ZIP..." | tee -a $LOG_FILE
    unzip -o -q "$DATASET_ZIP" -d "$EXTRACT_DIR"
    touch "$EXTRACT_DIR/.extracted"
    echo "Extraction complete: $(find "$EXTRACT_DIR" -name "*.pdf" | wc -l) PDFs" | tee -a $LOG_FILE
else
    echo "[1/3] Already extracted" | tee -a $LOG_FILE
fi

# Step 2: Convert PDFs to text
echo "[2/3] Converting PDFs to text..." | tee -a $LOG_FILE

TOTAL=$(find "$EXTRACT_DIR" -name "*.pdf" | wc -l)
COUNT=0
ERRORS=0

find "$EXTRACT_DIR" -name "*.pdf" | while read pdf; do
    COUNT=$((COUNT + 1))
    BASENAME=$(basename "$pdf" .pdf)
    OUTFILE="$TEXT_DIR/${BASENAME}.txt"

    # Skip if already processed
    if [ -f "$OUTFILE" ]; then
        continue
    fi

    # Convert PDF to text
    if pdftotext -layout "$pdf" "$OUTFILE" 2>/dev/null; then
        # Check if output is not empty
        if [ ! -s "$OUTFILE" ]; then
            rm -f "$OUTFILE"
            ERRORS=$((ERRORS + 1))
        fi
    else
        ERRORS=$((ERRORS + 1))
    fi

    # Progress every 500 files
    if [ $((COUNT % 500)) -eq 0 ]; then
        echo "Progress: $COUNT / $TOTAL (errors: $ERRORS)" | tee -a $LOG_FILE
    fi
done

echo "Text conversion complete" | tee -a $LOG_FILE
echo "Total text files: $(ls "$TEXT_DIR"/*.txt 2>/dev/null | wc -l)" | tee -a $LOG_FILE

echo "[3/3] Ready for ingestion" | tee -a $LOG_FILE
echo "Finished: $(date)" | tee -a $LOG_FILE
