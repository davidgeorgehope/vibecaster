#!/bin/bash

# Vibecaster Production Stop Script
# Gracefully stops both frontend and backend services

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Base directory
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
PIDS_DIR="$BASE_DIR/pids"

echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Vibecaster Production Shutdown       ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
echo ""

STOPPED=0

# Stop Backend
if [ -f "$PIDS_DIR/backend.pid" ]; then
    BACKEND_PID=$(cat "$PIDS_DIR/backend.pid")
    if kill -0 $BACKEND_PID 2>/dev/null; then
        echo -e "${GREEN}Stopping Backend (PID: $BACKEND_PID)...${NC}"
        kill $BACKEND_PID

        # Wait for graceful shutdown (max 10 seconds)
        for i in {1..10}; do
            if ! kill -0 $BACKEND_PID 2>/dev/null; then
                echo -e "   ✅ Backend stopped gracefully"
                break
            fi
            sleep 1
        done

        # Force kill if still running
        if kill -0 $BACKEND_PID 2>/dev/null; then
            echo -e "${YELLOW}   ⚠️  Force killing backend...${NC}"
            kill -9 $BACKEND_PID 2>/dev/null || true
        fi

        STOPPED=1
    else
        echo -e "${YELLOW}Backend PID file exists but process not running${NC}"
    fi
    rm -f "$PIDS_DIR/backend.pid"
else
    echo -e "${YELLOW}Backend not running (no PID file)${NC}"
fi

# Stop Frontend
if [ -f "$PIDS_DIR/frontend.pid" ]; then
    FRONTEND_PID=$(cat "$PIDS_DIR/frontend.pid")
    if kill -0 $FRONTEND_PID 2>/dev/null; then
        echo -e "${GREEN}Stopping Frontend (PID: $FRONTEND_PID)...${NC}"
        kill $FRONTEND_PID

        # Wait for graceful shutdown (max 10 seconds)
        for i in {1..10}; do
            if ! kill -0 $FRONTEND_PID 2>/dev/null; then
                echo -e "   ✅ Frontend stopped gracefully"
                break
            fi
            sleep 1
        done

        # Force kill if still running
        if kill -0 $FRONTEND_PID 2>/dev/null; then
            echo -e "${YELLOW}   ⚠️  Force killing frontend...${NC}"
            kill -9 $FRONTEND_PID 2>/dev/null || true
        fi

        STOPPED=1
    else
        echo -e "${YELLOW}Frontend PID file exists but process not running${NC}"
    fi
    rm -f "$PIDS_DIR/frontend.pid"
else
    echo -e "${YELLOW}Frontend not running (no PID file)${NC}"
fi

# Also kill any orphaned processes by port
echo -e "${GREEN}Checking for orphaned processes...${NC}"

# Kill any process on common frontend ports (starting with new defaults)
for port in 3001 3002 3003 3000; do
    ORPHAN_PID=$(lsof -ti :$port 2>/dev/null)
    if [ ! -z "$ORPHAN_PID" ]; then
        echo -e "${YELLOW}Found orphaned process on port $port (PID: $ORPHAN_PID)${NC}"
        kill $ORPHAN_PID 2>/dev/null || true
        sleep 1
        if lsof -ti :$port >/dev/null 2>&1; then
            echo -e "${YELLOW}   Force killing...${NC}"
            kill -9 $ORPHAN_PID 2>/dev/null || true
        fi
        STOPPED=1
    fi
done

# Kill any process on common backend ports (starting with new defaults)
for port in 8001 8002 8003 8000; do
    ORPHAN_PID=$(lsof -ti :$port 2>/dev/null)
    if [ ! -z "$ORPHAN_PID" ]; then
        echo -e "${YELLOW}Found orphaned process on port $port (PID: $ORPHAN_PID)${NC}"
        kill $ORPHAN_PID 2>/dev/null || true
        sleep 1
        if lsof -ti :$port >/dev/null 2>&1; then
            echo -e "${YELLOW}   Force killing...${NC}"
            kill -9 $ORPHAN_PID 2>/dev/null || true
        fi
        STOPPED=1
    fi
done

echo ""
if [ $STOPPED -eq 1 ]; then
    echo -e "${GREEN}✅ All services stopped successfully${NC}"
else
    echo -e "${YELLOW}No running services found${NC}"
fi
echo ""
