#!/bin/bash
# Apply LLM tuning configuration
# Updates systemd service and restarts l-llm

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}  Apply LLM Configuration              ${NC}"
echo -e "${BLUE}=======================================${NC}"
echo ""

CONFIG_FILE="${1:-/opt/rag/config/llm_tuning.yaml}"

if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${RED}Error: Config file not found: $CONFIG_FILE${NC}"
    exit 1
fi

echo -e "${YELLOW}Configuration:${NC}"
echo "  Config file: $CONFIG_FILE"
echo ""

# Extract values from YAML (simple grep/sed, not full YAML parser)
MODEL_PATH=$(grep "model_path:" "$CONFIG_FILE" | head -1 | sed 's/.*"\(.*\)".*/\1/')
N_CTX=$(grep "n_ctx:" "$CONFIG_FILE" | head -1 | awk '{print $2}')
N_THREADS=$(grep "n_threads:" "$CONFIG_FILE" | head -1 | awk '{print $2}')
N_BATCH=$(grep "n_batch:" "$CONFIG_FILE" | head -1 | awk '{print $2}')
USE_MLOCK=$(grep "use_mlock:" "$CONFIG_FILE" | head -1 | awk '{print $2}')
USE_MMAP=$(grep "use_mmap:" "$CONFIG_FILE" | head -1 | awk '{print $2}')
TEMPERATURE=$(grep "temperature:" "$CONFIG_FILE" | head -1 | awk '{print $2}')

echo -e "${BLUE}Settings to apply:${NC}"
echo "  Model: $MODEL_PATH"
echo "  Context: $N_CTX"
echo "  Threads: $N_THREADS"
echo "  Batch: $N_BATCH"
echo "  MMap: $USE_MMAP"
echo "  MLock: $USE_MLOCK"
echo "  Temperature: $TEMPERATURE"
echo ""

# Check if model file exists
if [ ! -f "$MODEL_PATH" ]; then
    echo -e "${YELLOW}Warning: Model file not found: $MODEL_PATH${NC}"
    echo "Download it first before applying config"
    exit 1
fi

# Check if systemd service exists
if [ ! -f "/etc/systemd/system/l-llm.service" ]; then
    echo -e "${YELLOW}Warning: l-llm.service not found${NC}"
    echo "Creating systemd service..."

    # Create systemd service
    cat > /etc/systemd/system/l-llm.service << EOSERVICE
[Unit]
Description=L Investigation LLM Backend (Mistral 7B)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/rag
ExecStart=/usr/bin/python3 -m llama_cpp.server \\
    --model $MODEL_PATH \\
    --host 127.0.0.1 \\
    --port 8001 \\
    --n_ctx $N_CTX \\
    --n_threads $N_THREADS \\
    --n_batch $N_BATCH \\
    --use_mmap true \\
    --use_mlock true
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOSERVICE

    systemctl daemon-reload
    systemctl enable l-llm
else
    echo -e "${GREEN}Updating l-llm.service...${NC}"

    # Update ExecStart line in existing service
    sed -i "s|--model .*|--model $MODEL_PATH \\\\|" /etc/systemd/system/l-llm.service
    sed -i "s|--n_ctx .*|--n_ctx $N_CTX \\\\|" /etc/systemd/system/l-llm.service
    sed -i "s|--n_threads .*|--n_threads $N_THREADS \\\\|" /etc/systemd/system/l-llm.service
    sed -i "s|--n_batch .*|--n_batch $N_BATCH \\\\|" /etc/systemd/system/l-llm.service

    systemctl daemon-reload
fi

echo -e "${GREEN}Service file updated${NC}"
echo ""

read -p "Restart l-llm service now? (yes/no): " restart
if [ "$restart" == "yes" ]; then
    echo -e "${BLUE}Restarting l-llm service...${NC}"
    systemctl restart l-llm

    sleep 2

    # Check status
    if systemctl is-active --quiet l-llm; then
        echo -e "${GREEN}✓ l-llm service restarted successfully${NC}"

        # Test connection
        echo -e "${BLUE}Testing connection...${NC}"
        if curl -s http://localhost:8001/v1/models > /dev/null 2>&1; then
            echo -e "${GREEN}✓ LLM backend is responding${NC}"
        else
            echo -e "${YELLOW}Warning: LLM backend not responding yet (may take a few seconds to load)${NC}"
        fi
    else
        echo -e "${RED}✗ Failed to start l-llm service${NC}"
        echo "Check logs: journalctl -u l-llm -n 50"
        exit 1
    fi
else
    echo "Skipped restart. Run manually: sudo systemctl restart l-llm"
fi

echo ""
echo -e "${GREEN}=======================================${NC}"
echo -e "${GREEN}  Configuration Applied!               ${NC}"
echo -e "${GREEN}=======================================${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Monitor performance: journalctl -u l-llm -f"
echo "  2. Test query: curl 'http://localhost:8002/api/ask?q=test'"
echo "  3. Compare timing vs previous config"
echo ""
