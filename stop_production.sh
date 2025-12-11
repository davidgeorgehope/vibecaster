#!/bin/bash

# Vibecaster Production Stop Script
# Gracefully stops both frontend and backend services

# Don't use set -e - we want to continue even if some kills fail
# set -e

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

# Read the ports we were using (saved by start script)
FRONTEND_PORT=3000
BACKEND_PORT=8001
if [ -f "$PIDS_DIR/frontend.port" ]; then
    FRONTEND_PORT=$(cat "$PIDS_DIR/frontend.port")
fi
if [ -f "$PIDS_DIR/backend.port" ]; then
    BACKEND_PORT=$(cat "$PIDS_DIR/backend.port")
fi
echo -e "Looking for services on ports: frontend=$FRONTEND_PORT, backend=$BACKEND_PORT"
echo ""

# Helper function to check if a PID is a Docker process (which we should NOT kill)
is_docker_process() {
    local pid=$1
    local cmdline=$(ps -p $pid -o comm= 2>/dev/null)
    if [[ "$cmdline" == *"docker"* ]]; then
        return 0  # true, is docker
    fi
    # Also check if it's a docker-proxy
    local full_cmd=$(ps -p $pid -o args= 2>/dev/null)
    if [[ "$full_cmd" == *"docker-proxy"* ]]; then
        return 0  # true, is docker
    fi
    return 1  # false, not docker
}

# Helper function to safely kill a process (skips Docker)
safe_kill() {
    local pid=$1
    local signal=${2:-TERM}

    if is_docker_process $pid; then
        echo -e "${YELLOW}   Skipping PID $pid (Docker process)${NC}"
        return 1
    fi

    kill -$signal $pid 2>/dev/null
    return $?
}

# Stop Backend - first by PID file, then by port
if [ -f "$PIDS_DIR/backend.pid" ]; then
    BACKEND_PID=$(cat "$PIDS_DIR/backend.pid")
    if kill -0 $BACKEND_PID 2>/dev/null; then
        echo -e "${GREEN}Stopping Backend (PID: $BACKEND_PID)...${NC}"
        safe_kill $BACKEND_PID TERM

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
            safe_kill $BACKEND_PID 9
        fi

        STOPPED=1
    else
        echo -e "${YELLOW}Backend PID file exists but process not running${NC}"
    fi
    rm -f "$PIDS_DIR/backend.pid"
else
    echo -e "${YELLOW}Backend not running (no PID file)${NC}"
fi

# Also kill any non-Docker process on the backend port that might have been missed
BACKEND_PORT_PIDS=$(lsof -ti :$BACKEND_PORT 2>/dev/null)
for pid in $BACKEND_PORT_PIDS; do
    if ! is_docker_process $pid; then
        echo -e "${YELLOW}Found process on port $BACKEND_PORT (PID: $pid), killing...${NC}"
        safe_kill $pid TERM
        sleep 2
        if kill -0 $pid 2>/dev/null; then
            safe_kill $pid 9
        fi
        STOPPED=1
    fi
done

# Stop Frontend
if [ -f "$PIDS_DIR/frontend.pid" ]; then
    FRONTEND_PID=$(cat "$PIDS_DIR/frontend.pid")
    if kill -0 $FRONTEND_PID 2>/dev/null; then
        echo -e "${GREEN}Stopping Frontend (PID: $FRONTEND_PID)...${NC}"

        # Kill the entire process group to catch all child processes (Next.js spawns children)
        pkill -TERM -P $FRONTEND_PID 2>/dev/null || true
        safe_kill $FRONTEND_PID TERM

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
            safe_kill $FRONTEND_PID 9
        fi

        STOPPED=1
    else
        echo -e "${YELLOW}Frontend PID file exists but process not running${NC}"
    fi
    rm -f "$PIDS_DIR/frontend.pid"
else
    echo -e "${YELLOW}Frontend not running (no PID file)${NC}"
fi

# Also kill any non-Docker process on the frontend port that might have been missed
FRONTEND_PORT_PIDS=$(lsof -ti :$FRONTEND_PORT 2>/dev/null)
for pid in $FRONTEND_PORT_PIDS; do
    if ! is_docker_process $pid; then
        echo -e "${YELLOW}Found process on port $FRONTEND_PORT (PID: $pid), killing...${NC}"
        pkill -9 -P $pid 2>/dev/null || true
        safe_kill $pid 9
        STOPPED=1
    fi
done

# Also kill any lingering Next.js or uvicorn processes related to vibecaster
echo -e "${GREEN}Checking for lingering Node/Python processes...${NC}"

# Find and kill any Next.js processes in the vibecaster directory
# Check for both "next start" and "next-server" patterns
NEXTJS_PIDS=$(ps aux | grep -E "(next start|next-server)" | grep "$BASE_DIR" | grep -v grep | awk '{print $2}')
if [ ! -z "$NEXTJS_PIDS" ]; then
    echo -e "${YELLOW}Found lingering Next.js processes: $NEXTJS_PIDS${NC}"
    for pid in $NEXTJS_PIDS; do
        if ! is_docker_process $pid; then
            pkill -9 -P $pid 2>/dev/null || true
            safe_kill $pid 9
        fi
    done
    STOPPED=1
fi

# Find and kill any uvicorn processes in the vibecaster backend directory
UVICORN_PIDS=$(ps aux | grep "uvicorn main:app" | grep "$BASE_DIR" | grep -v grep | awk '{print $2}')
if [ ! -z "$UVICORN_PIDS" ]; then
    echo -e "${YELLOW}Found lingering uvicorn processes: $UVICORN_PIDS${NC}"
    for pid in $UVICORN_PIDS; do
        if ! is_docker_process $pid; then
            safe_kill $pid 9
        fi
    done
    STOPPED=1
fi

# Final verification - check our specific ports (not hardcoded 3000/8001)
echo -e "${GREEN}Final verification...${NC}"
sleep 1

# Check frontend port
STILL_ON_FRONTEND=$(lsof -ti :$FRONTEND_PORT 2>/dev/null)
for pid in $STILL_ON_FRONTEND; do
    if ! is_docker_process $pid; then
        echo -e "${RED}⚠️  Port $FRONTEND_PORT still in use by PID: $pid${NC}"
        echo -e "${RED}   Force killing...${NC}"
        safe_kill $pid 9
    else
        echo -e "${YELLOW}   Port $FRONTEND_PORT in use by Docker (ignoring)${NC}"
    fi
done

# Check backend port
STILL_ON_BACKEND=$(lsof -ti :$BACKEND_PORT 2>/dev/null)
for pid in $STILL_ON_BACKEND; do
    if ! is_docker_process $pid; then
        echo -e "${RED}⚠️  Port $BACKEND_PORT still in use by PID: $pid${NC}"
        echo -e "${RED}   Force killing...${NC}"
        safe_kill $pid 9
    else
        echo -e "${YELLOW}   Port $BACKEND_PORT in use by Docker (ignoring)${NC}"
    fi
done

# Clean up port files
rm -f "$PIDS_DIR/frontend.port" "$PIDS_DIR/backend.port"

echo ""
if [ $STOPPED -eq 1 ]; then
    echo -e "${GREEN}✅ Vibecaster services stopped${NC}"
else
    echo -e "${YELLOW}No Vibecaster services were running${NC}"
fi
echo ""
