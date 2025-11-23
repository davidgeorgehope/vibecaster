#!/bin/bash

# Vibecaster Production Startup Script
# This script starts both frontend and backend in production mode

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Base directory
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$BASE_DIR/backend"
FRONTEND_DIR="$BASE_DIR/frontend"
LOGS_DIR="$BASE_DIR/logs"
PIDS_DIR="$BASE_DIR/pids"

# Create directories for logs and PIDs
mkdir -p "$LOGS_DIR"
mkdir -p "$PIDS_DIR"

echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Vibecaster Production Startup        ║${NC}"
echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo ""

# Check if already running
if [ -f "$PIDS_DIR/backend.pid" ] && kill -0 $(cat "$PIDS_DIR/backend.pid") 2>/dev/null; then
    echo -e "${YELLOW}⚠️  Backend is already running (PID: $(cat "$PIDS_DIR/backend.pid"))${NC}"
    echo "   Run ./stop_production.sh first to stop existing processes"
    exit 1
fi

if [ -f "$PIDS_DIR/frontend.pid" ] && kill -0 $(cat "$PIDS_DIR/frontend.pid") 2>/dev/null; then
    echo -e "${YELLOW}⚠️  Frontend is already running (PID: $(cat "$PIDS_DIR/frontend.pid"))${NC}"
    echo "   Run ./stop_production.sh first to stop existing processes"
    exit 1
fi

# ===== BACKEND SETUP =====
echo -e "${GREEN}[1/4] Setting up Backend...${NC}"
cd "$BACKEND_DIR"

# Check for .env file
if [ ! -f ".env" ]; then
    echo -e "${RED}❌ ERROR: .env file not found in backend/${NC}"
    echo "   Please create .env from .env.example with your credentials"
    exit 1
fi

# Verify ENVIRONMENT is not set to development in .env
if grep -q "^ENVIRONMENT=development" .env; then
    echo -e "${YELLOW}⚠️  WARNING: ENVIRONMENT=development found in .env${NC}"
    echo "   For production, this should be set to 'production'"
    read -p "   Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Setup virtual environment
# Check if venv exists AND is valid (has activate script)
if [ ! -f "venv/bin/activate" ]; then
    if [ -d "venv" ]; then
        echo "   Removing corrupted virtual environment..."
        rm -rf venv
    fi

    echo "   Creating Python virtual environment..."
    python3 -m venv venv

    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ Failed to create virtual environment${NC}"
        echo "   Install python3-venv with: apt-get install python3-venv"
        exit 1
    fi

    if [ ! -f "venv/bin/activate" ]; then
        echo -e "${RED}❌ Virtual environment creation failed${NC}"
        exit 1
    fi
fi

source venv/bin/activate

# Install dependencies
echo "   Installing Python dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Initialize database
echo "   Initializing database..."
python3 -c "from database import init_database; init_database()"

# ===== FRONTEND BUILD =====
echo -e "${GREEN}[2/4] Building Frontend for Production...${NC}"
cd "$FRONTEND_DIR"

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "   Installing Node dependencies..."
    npm install
fi

# Build Next.js for production
echo "   Building Next.js application..."
npm run build

# ===== START BACKEND =====
echo -e "${GREEN}[3/4] Starting Backend (Production Mode)...${NC}"
cd "$BACKEND_DIR"
source venv/bin/activate

# Set production environment
export ENVIRONMENT=production

# Start backend with uvicorn (4 workers for better performance)
nohup uvicorn main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 4 \
    --log-level warning \
    > "$LOGS_DIR/backend.log" 2>&1 &

BACKEND_PID=$!
echo $BACKEND_PID > "$PIDS_DIR/backend.pid"
echo -e "   ✅ Backend started (PID: $BACKEND_PID)"
echo -e "      Logs: $LOGS_DIR/backend.log"
echo -e "      URL: http://localhost:8000"

# ===== START FRONTEND =====
echo -e "${GREEN}[4/4] Starting Frontend (Production Mode)...${NC}"
cd "$FRONTEND_DIR"

# Start Next.js in production mode
nohup npm start > "$LOGS_DIR/frontend.log" 2>&1 &

FRONTEND_PID=$!
echo $FRONTEND_PID > "$PIDS_DIR/frontend.pid"
echo -e "   ✅ Frontend started (PID: $FRONTEND_PID)"
echo -e "      Logs: $LOGS_DIR/frontend.log"
echo -e "      URL: http://localhost:3000"

# Wait a moment to check if processes started successfully
sleep 3

# Verify processes are still running
if ! kill -0 $BACKEND_PID 2>/dev/null; then
    echo -e "${RED}❌ Backend failed to start! Check logs:${NC}"
    echo "   tail -f $LOGS_DIR/backend.log"
    exit 1
fi

if ! kill -0 $FRONTEND_PID 2>/dev/null; then
    echo -e "${RED}❌ Frontend failed to start! Check logs:${NC}"
    echo "   tail -f $LOGS_DIR/frontend.log"
    exit 1
fi

# ===== SUCCESS =====
echo ""
echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   🚀 Vibecaster is now running!       ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
echo ""
echo -e "📊 ${GREEN}Status:${NC}"
echo -e "   Frontend: http://localhost:3000"
echo -e "   Backend:  http://localhost:8000"
echo -e "   Docs:     http://localhost:8000/docs"
echo ""
echo -e "📝 ${GREEN}Logs:${NC}"
echo -e "   Backend:  tail -f $LOGS_DIR/backend.log"
echo -e "   Frontend: tail -f $LOGS_DIR/frontend.log"
echo ""
echo -e "🛑 ${GREEN}To stop:${NC}"
echo -e "   ./stop_production.sh"
echo ""
