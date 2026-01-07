#!/bin/bash

# Vibecaster Production Startup Script
# Starts frontend (port 3001) and backend (port 8001)

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Fixed ports - nginx is configured for these
FRONTEND_PORT=3001
BACKEND_PORT=8001

# Directories
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$BASE_DIR/backend"
FRONTEND_DIR="$BASE_DIR/frontend"
LOGS_DIR="$BASE_DIR/logs"
PIDS_DIR="$BASE_DIR/pids"

mkdir -p "$LOGS_DIR" "$PIDS_DIR"

echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Vibecaster Production Startup        ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
echo ""

# Helper to check if process belongs to vibecaster
is_vibecaster_process() {
    local pid=$1
    local proc_cwd=$(readlink -f /proc/$pid/cwd 2>/dev/null)
    [[ "$proc_cwd" == "$BASE_DIR"* ]]
}

# Cleanup existing processes
echo -e "${GREEN}[1/5] Cleaning up existing processes...${NC}"

for pid in $(ps aux | grep -E "next|next-server" | grep -v grep | awk '{print $2}'); do
    if is_vibecaster_process $pid; then
        pkill -9 -P $pid 2>/dev/null || true
        kill -9 $pid 2>/dev/null || true
    fi
done

for pid in $(ps aux | grep "uvicorn main:app" | grep -v grep | awk '{print $2}'); do
    if is_vibecaster_process $pid; then
        kill -9 $pid 2>/dev/null || true
    fi
done
sleep 1
rm -f "$PIDS_DIR/backend.pid" "$PIDS_DIR/frontend.pid" 2>/dev/null
echo -e "   ✅ Done"

# Backend setup
echo -e "${GREEN}[2/5] Setting up Backend...${NC}"
cd "$BACKEND_DIR"

if [ ! -f ".env" ]; then
    echo -e "${RED}❌ .env file not found in backend/${NC}"
    exit 1
fi

if [ ! -f "venv/bin/activate" ]; then
    rm -rf venv 2>/dev/null
    echo "   Creating virtual environment..."
    python3 -m venv venv || { echo -e "${RED}❌ Failed to create venv${NC}"; exit 1; }
fi

source venv/bin/activate
echo "   Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo "   Initializing database..."
python3 -c "from database import init_database; init_database()"

# Frontend setup
echo -e "${GREEN}[3/5] Building Frontend...${NC}"
cd "$FRONTEND_DIR"

[ ! -d "node_modules" ] && npm install

rm -rf .next node_modules/.cache
npm run build

# Start backend
echo -e "${GREEN}[4/5] Starting Backend on port $BACKEND_PORT...${NC}"
cd "$BACKEND_DIR"
source venv/bin/activate
export ENVIRONMENT=production

nohup uvicorn main:app \
    --host 0.0.0.0 \
    --port $BACKEND_PORT \
    --workers 1 \
    --log-level warning \
    > "$LOGS_DIR/backend.log" 2>&1 &

BACKEND_PID=$!
echo $BACKEND_PID > "$PIDS_DIR/backend.pid"

# Wait for backend
for i in {1..30}; do
    fuser $BACKEND_PORT/tcp >/dev/null 2>&1 && break
    [ $i -eq 30 ] && { echo -e "${RED}❌ Backend failed to start${NC}"; tail -20 "$LOGS_DIR/backend.log"; exit 1; }
    sleep 1
done
echo -e "   ✅ Backend running (PID: $BACKEND_PID)"

# Start frontend
echo -e "${GREEN}[5/5] Starting Frontend on port $FRONTEND_PORT...${NC}"
cd "$FRONTEND_DIR"

nohup node_modules/.bin/next start -p $FRONTEND_PORT -H 0.0.0.0 > "$LOGS_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
disown $FRONTEND_PID 2>/dev/null || true
echo $FRONTEND_PID > "$PIDS_DIR/frontend.pid"

# Wait for frontend
for i in {1..45}; do
    curl -s -o /dev/null http://127.0.0.1:$FRONTEND_PORT/ 2>/dev/null && break
    [ $i -eq 45 ] && { echo -e "${RED}❌ Frontend failed to start${NC}"; tail -20 "$LOGS_DIR/frontend.log"; exit 1; }
    sleep 1
done
echo -e "   ✅ Frontend running (PID: $FRONTEND_PID)"

# Save ports for stop script
echo "$FRONTEND_PORT" > "$PIDS_DIR/frontend.port"
echo "$BACKEND_PORT" > "$PIDS_DIR/backend.port"

# Verify
echo -e "${GREEN}Verifying...${NC}"
BACKEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:$BACKEND_PORT/docs 2>/dev/null || echo "000")
FRONTEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:$FRONTEND_PORT/ 2>/dev/null || echo "000")

[ "$BACKEND_STATUS" != "200" ] && { echo -e "${RED}❌ Backend not responding${NC}"; exit 1; }
[ "$FRONTEND_STATUS" != "200" ] && { echo -e "${RED}❌ Frontend not responding${NC}"; exit 1; }

echo -e "   ✅ All services healthy"

echo ""
echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   🚀 Vibecaster is running!            ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
echo ""
echo -e "   Site:     http://vibecaster.ai"
echo -e "   Frontend: http://localhost:$FRONTEND_PORT"
echo -e "   Backend:  http://localhost:$BACKEND_PORT"
echo -e "   Docs:     http://localhost:$BACKEND_PORT/docs"
echo ""
echo -e "   Logs:     tail -f $LOGS_DIR/backend.log"
echo -e "   Stop:     ./stop_production.sh"
echo ""
