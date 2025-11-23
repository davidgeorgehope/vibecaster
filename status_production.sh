#!/bin/bash

# Vibecaster Production Status Script
# Check if services are running and show their status

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Base directory
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
PIDS_DIR="$BASE_DIR/pids"
LOGS_DIR="$BASE_DIR/logs"

echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Vibecaster Production Status         ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
echo ""

ALL_RUNNING=1

# Check Backend
echo -e "${GREEN}Backend:${NC}"
if [ -f "$PIDS_DIR/backend.pid" ]; then
    BACKEND_PID=$(cat "$PIDS_DIR/backend.pid")
    if kill -0 $BACKEND_PID 2>/dev/null; then
        echo -e "   ✅ Running (PID: $BACKEND_PID)"
        echo -e "      URL: http://localhost:8000"
        echo -e "      Docs: http://localhost:8000/docs"
        if [ -f "$LOGS_DIR/backend.log" ]; then
            echo -e "      Log: tail -f $LOGS_DIR/backend.log"
        fi
    else
        echo -e "   ${RED}❌ Not running (stale PID file)${NC}"
        ALL_RUNNING=0
    fi
else
    echo -e "   ${RED}❌ Not running${NC}"
    ALL_RUNNING=0
fi

echo ""

# Check Frontend
echo -e "${GREEN}Frontend:${NC}"
if [ -f "$PIDS_DIR/frontend.pid" ]; then
    FRONTEND_PID=$(cat "$PIDS_DIR/frontend.pid")
    if kill -0 $FRONTEND_PID 2>/dev/null; then
        echo -e "   ✅ Running (PID: $FRONTEND_PID)"
        echo -e "      URL: http://localhost:3000"
        if [ -f "$LOGS_DIR/frontend.log" ]; then
            echo -e "      Log: tail -f $LOGS_DIR/frontend.log"
        fi
    else
        echo -e "   ${RED}❌ Not running (stale PID file)${NC}"
        ALL_RUNNING=0
    fi
else
    echo -e "   ${RED}❌ Not running${NC}"
    ALL_RUNNING=0
fi

echo ""

if [ $ALL_RUNNING -eq 1 ]; then
    echo -e "${GREEN}✅ All services are running${NC}"
else
    echo -e "${YELLOW}⚠️  Some services are not running${NC}"
    echo -e "   Start with: ./start_production.sh"
fi

echo ""

# Show recent log activity
if [ -f "$LOGS_DIR/backend.log" ] || [ -f "$LOGS_DIR/frontend.log" ]; then
    echo -e "${GREEN}Recent Activity:${NC}"
    echo ""

    if [ -f "$LOGS_DIR/backend.log" ]; then
        echo -e "   ${GREEN}Backend (last 5 lines):${NC}"
        tail -n 5 "$LOGS_DIR/backend.log" 2>/dev/null | sed 's/^/      /' || echo "      (no logs yet)"
        echo ""
    fi

    if [ -f "$LOGS_DIR/frontend.log" ]; then
        echo -e "   ${GREEN}Frontend (last 5 lines):${NC}"
        tail -n 5 "$LOGS_DIR/frontend.log" 2>/dev/null | sed 's/^/      /' || echo "      (no logs yet)"
        echo ""
    fi
fi
