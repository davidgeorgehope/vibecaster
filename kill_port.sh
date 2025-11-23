#!/bin/bash

# Kill process using a specific port
# Usage: ./kill_port.sh [port_number]

PORT=${1:-8000}

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}Checking port $PORT...${NC}"

# Find process using the port
PID=$(lsof -ti :$PORT)

if [ -z "$PID" ]; then
    echo -e "${YELLOW}No process found using port $PORT${NC}"
    exit 0
fi

# Show what's using the port
echo ""
echo -e "${YELLOW}Process using port $PORT:${NC}"
lsof -i :$PORT

echo ""
read -p "Kill this process? (y/N): " -n 1 -r
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    kill $PID
    sleep 1

    # Check if it's still running
    if lsof -ti :$PORT >/dev/null 2>&1; then
        echo -e "${YELLOW}Process didn't stop, force killing...${NC}"
        kill -9 $PID
    fi

    echo -e "${GREEN}✅ Port $PORT is now free${NC}"
else
    echo -e "${YELLOW}Cancelled${NC}"
fi
