#!/bin/bash
#===============================================================================
# download-model.sh - Download Phi-3-Mini GGUF model from HuggingFace
#===============================================================================
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_DIR="$INSTALL_DIR/llm"
MODEL_FILE="phi-3-mini-4k-instruct.Q4_K_M.gguf"
MODEL_PATH="$MODEL_DIR/$MODEL_FILE"

# HuggingFace download URL (Phi-3-Mini-4K-Instruct GGUF Q4_K_M)
MODEL_URL="https://huggingface.co/microsoft/Phi-3-mini-4k-instruct-gguf/resolve/main/Phi-3-mini-4k-instruct-q4.gguf"
CHECKSUM_URL="https://huggingface.co/microsoft/Phi-3-mini-4k-instruct-gguf/raw/main/Phi-3-mini-4k-instruct-q4.gguf.sha256"

echo -e "${GREEN}[1/3]${NC} Checking for existing model..."

# Create model directory
mkdir -p "$MODEL_DIR"

# Check if model already exists
if [ -f "$MODEL_PATH" ]; then
    echo -e "${YELLOW}Model already exists: $MODEL_PATH${NC}"
    echo -e "${GREEN}Skipping download${NC}"
    exit 0
fi

echo -e "${GREEN}[2/3]${NC} Downloading Phi-3-Mini GGUF (2.4GB)..."
echo "  URL: $MODEL_URL"
echo "  Destination: $MODEL_PATH"

# Download model using wget or curl
if command -v wget &> /dev/null; then
    wget -q --show-progress -O "$MODEL_PATH" "$MODEL_URL"
elif command -v curl &> /dev/null; then
    curl -L --progress-bar -o "$MODEL_PATH" "$MODEL_URL"
else
    echo "Error: wget or curl required for download"
    exit 1
fi

echo -e "${GREEN}[3/3]${NC} Verifying download..."

# Basic size check (Phi-3-Mini Q4 should be ~2.4GB)
SIZE=$(stat -f%z "$MODEL_PATH" 2>/dev/null || stat -c%s "$MODEL_PATH" 2>/dev/null)
SIZE_GB=$((SIZE / 1024 / 1024 / 1024))

if [ "$SIZE_GB" -lt 2 ]; then
    echo "Error: Downloaded file too small ($SIZE_GB GB). Expected ~2.4GB"
    echo "Download may be incomplete. Delete $MODEL_PATH and try again."
    exit 1
fi

echo -e "${GREEN}✓ Model downloaded successfully${NC}"
echo "  Size: ${SIZE_GB}GB"
echo "  Path: $MODEL_PATH"
