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

# Stop Backend - first by PID file, then by port
if [ -f "$PIDS_DIR/backend.pid" ]; then
    BACKEND_PID=$(cat "$PIDS_DIR/backend.pid")
    if kill -0 $BACKEND_PID 2>/dev/null; then
        echo -e "${GREEN}Stopping Backend (PID: $BACKEND_PID)...${NC}"
        kill $BACKEND_PID 2>/dev/null || true

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

# Also kill any process on port 8001 that might have been missed
BACKEND_PORT_PID=$(lsof -ti :8001 2>/dev/null)
if [ ! -z "$BACKEND_PORT_PID" ]; then
    echo -e "${YELLOW}Found process on port 8001 (PID: $BACKEND_PORT_PID), killing...${NC}"
    kill $BACKEND_PORT_PID 2>/dev/null || true
    sleep 2
    if kill -0 $BACKEND_PORT_PID 2>/dev/null; then
        kill -9 $BACKEND_PORT_PID 2>/dev/null || true
    fi
    STOPPED=1
fi

# Stop Frontend
if [ -f "$PIDS_DIR/frontend.pid" ]; then
    FRONTEND_PID=$(cat "$PIDS_DIR/frontend.pid")
    if kill -0 $FRONTEND_PID 2>/dev/null; then
        echo -e "${GREEN}Stopping Frontend (PID: $FRONTEND_PID)...${NC}"

        # Kill the entire process group to catch all child processes (Next.js spawns children)
        # Using pkill with parent PID to kill all descendants
        pkill -TERM -P $FRONTEND_PID 2>/dev/null || true
        kill $FRONTEND_PID 2>/dev/null || true

        # Wait for graceful shutdown (max 10 seconds)
        for i in {1..10}; do
            if ! kill -0 $FRONTEND_PID 2>/dev/null; then
                echo -e "   ✅ Frontend stopped gracefully"
                break
            fi
            sleep 1
        done

        # Force kill if still running (including all descendants)
        if kill -0 $FRONTEND_PID 2>/dev/null; then
            echo -e "${YELLOW}   ⚠️  Force killing frontend and children...${NC}"
            pkill -9 -P $FRONTEND_PID 2>/dev/null || true
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

# Also kill any process on port 3000 that might have been missed
FRONTEND_PORT_PID=$(lsof -ti :3000 2>/dev/null)
if [ ! -z "$FRONTEND_PORT_PID" ]; then
    echo -e "${YELLOW}Found process on port 3000 (PID: $FRONTEND_PORT_PID), killing...${NC}"
    pkill -9 -P $FRONTEND_PORT_PID 2>/dev/null || true
    kill -9 $FRONTEND_PORT_PID 2>/dev/null || true
    STOPPED=1
fi

# Also kill any orphaned processes by port
echo -e "${GREEN}Checking for orphaned processes...${NC}"

# Function to kill all processes on a port (including children)
kill_port_processes() {
    local port=$1
    local pids=$(lsof -ti :$port 2>/dev/null)

    if [ ! -z "$pids" ]; then
        echo -e "${YELLOW}Found process(es) on port $port (PIDs: $pids)${NC}"

        # Kill each PID
        for pid in $pids; do
            # First try graceful kill
            kill $pid 2>/dev/null || true
        done

        # Wait a moment for graceful shutdown
        sleep 2

        # Force kill any remaining processes
        for pid in $pids; do
            if kill -0 $pid 2>/dev/null; then
                echo -e "${YELLOW}   Force killing PID $pid...${NC}"
                kill -9 $pid 2>/dev/null || true
            fi
        done

        # Double-check the port is free
        local remaining=$(lsof -ti :$port 2>/dev/null)
        if [ ! -z "$remaining" ]; then
            echo -e "${RED}   Still found processes on port $port: $remaining${NC}"
            echo -e "${RED}   Force killing all...${NC}"
            for pid in $remaining; do
                kill -9 $pid 2>/dev/null || true
            done
        fi

        STOPPED=1
        return 0
    fi
    return 1
}

# Kill any process on common frontend ports (starting with default 3000)
for port in 3000 3001 3002 3003; do
    kill_port_processes $port || true
done

# Kill any process on common backend ports (starting with new defaults)
for port in 8001 8002 8003 8000; do
    kill_port_processes $port || true
done

# Also kill any lingering Next.js or uvicorn processes related to vibecaster
echo -e "${GREEN}Checking for lingering Node/Python processes...${NC}"
VIBECASTER_DIR="$(cd "$(dirname "$0")" && pwd)"

# Find and kill any Next.js processes (including next-server which is the actual running process)
# Check for both "next start" and "next-server" patterns
NEXTJS_PIDS=$(ps aux | grep -E "(next start|next-server)" | grep -v grep | awk '{print $2}')
if [ ! -z "$NEXTJS_PIDS" ]; then
    echo -e "${YELLOW}Found lingering Next.js processes: $NEXTJS_PIDS${NC}"
    for pid in $NEXTJS_PIDS; do
        # Kill process and any children
        pkill -9 -P $pid 2>/dev/null || true
        kill -9 $pid 2>/dev/null || true
    done
    STOPPED=1
fi

# Find and kill any uvicorn processes in the vibecaster backend directory
UVICORN_PIDS=$(ps aux | grep "uvicorn main:app" | grep "$VIBECASTER_DIR" | grep -v grep | awk '{print $2}')
if [ ! -z "$UVICORN_PIDS" ]; then
    echo -e "${YELLOW}Found lingering uvicorn processes: $UVICORN_PIDS${NC}"
    for pid in $UVICORN_PIDS; do
        kill -9 $pid 2>/dev/null || true
    done
    STOPPED=1
fi

# Final verification - ensure ports are free
echo -e "${GREEN}Final verification...${NC}"
sleep 1

STILL_ON_3000=$(lsof -ti :3000 2>/dev/null)
STILL_ON_8001=$(lsof -ti :8001 2>/dev/null)

if [ ! -z "$STILL_ON_3000" ]; then
    echo -e "${RED}⚠️  Port 3000 still in use by PID: $STILL_ON_3000${NC}"
    echo -e "${RED}   Force killing...${NC}"
    kill -9 $STILL_ON_3000 2>/dev/null || true
fi

if [ ! -z "$STILL_ON_8001" ]; then
    echo -e "${RED}⚠️  Port 8001 still in use by PID: $STILL_ON_8001${NC}"
    echo -e "${RED}   Force killing...${NC}"
    kill -9 $STILL_ON_8001 2>/dev/null || true
fi

# Confirm ports are now free
sleep 1
if lsof -ti :3000 >/dev/null 2>&1 || lsof -ti :8001 >/dev/null 2>&1; then
    echo -e "${RED}❌ WARNING: Some ports may still be in use${NC}"
else
    echo -e "   ✅ Ports 3000 and 8001 are free"
fi

echo ""
if [ $STOPPED -eq 1 ]; then
    echo -e "${GREEN}✅ All services stopped successfully${NC}"
else
    echo -e "${YELLOW}No running services found${NC}"
fi
echo ""
