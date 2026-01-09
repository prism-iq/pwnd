#!/bin/bash
# Test script to verify auto-investigation flow works correctly

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}=========================================${NC}"
echo -e "${BLUE}  Testing Auto-Investigation Flow       ${NC}"
echo -e "${BLUE}=========================================${NC}"
echo ""

# Test endpoint
API_URL="http://127.0.0.1:8002/api/ask"

# Test queries to simulate auto-investigation
QUERIES=(
    "Who is Jeffrey Epstein?"
    "What connections does he have to Trump?"
    "What financial entities appear in the communications?"
)

echo -e "${GREEN}[TEST 1/3]${NC} Testing sequential queries..."
echo ""

for i in "${!QUERIES[@]}"; do
    QUERY="${QUERIES[$i]}"
    QUERY_NUM=$((i+1))

    echo -e "${YELLOW}Query ${QUERY_NUM}/${#QUERIES[@]}:${NC} $QUERY"
    echo -e "${BLUE}Sending request...${NC}"

    # Make request and capture response
    RESPONSE=$(curl -s -N "${API_URL}?q=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$QUERY'))")" 2>&1)

    # Check if request succeeded
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Query completed successfully${NC}"

        # Extract key information from response
        SOURCES=$(echo "$RESPONSE" | grep -o '"type":"sources"' | wc -l)
        CHUNKS=$(echo "$RESPONSE" | grep -o '"type":"chunk"' | wc -l)

        echo -e "  Sources: $SOURCES"
        echo -e "  Chunks: $CHUNKS"
    else
        echo -e "${RED}✗ Query failed${NC}"
        echo "$RESPONSE"
    fi

    echo ""

    # Wait between queries (simulate user/auto-investigate delay)
    if [ $QUERY_NUM -lt ${#QUERIES[@]} ]; then
        echo -e "${BLUE}Waiting 2 seconds before next query...${NC}"
        sleep 2
        echo ""
    fi
done

echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}  Test Complete                         ${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""
echo -e "${YELLOW}Manual Test:${NC}"
echo "1. Open browser to http://localhost or https://pwnd.icu"
echo "2. Enable 'Auto-investigate' toggle"
echo "3. Submit query: 'Who is Jeffrey Epstein?'"
echo "4. Watch it automatically chain through suggested queries"
echo "5. Verify no frontend bugs occur (no stuck inputs, no duplicate messages)"
echo ""
