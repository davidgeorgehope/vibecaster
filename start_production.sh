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

# ===== FIND AVAILABLE PORTS =====
echo -e "${GREEN}[3/6] Checking ports...${NC}"

# Check if nginx reverse proxy is configured
NGINX_CONFIGURED=false
if [ -f "/etc/nginx/sites-enabled/vibecaster" ]; then
    NGINX_CONFIGURED=true
    echo -e "   ${GREEN}Nginx reverse proxy detected${NC}"
fi

# Function to find available port
find_port() {
    local start_port=$1
    local max_port=65535
    for port in $(seq $start_port $max_port); do
        if ! lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
            echo $port
            return 0
        fi
    done
    echo "0"
}

# Function to check if a port is available
is_port_available() {
    local port=$1
    if ! lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 0  # Available
    else
        return 1  # In use
    fi
}

if [ "$NGINX_CONFIGURED" = true ]; then
    # Nginx is configured - prefer ports 3001 and 8001, but use alternatives if needed
    echo -e "   ${YELLOW}Nginx reverse proxy detected${NC}"

    # Try standard ports first (3001/8001 to avoid conflicts with common services)
    if is_port_available 8001 && is_port_available 3001; then
        BACKEND_PORT=8001
        FRONTEND_PORT=3001
        echo -e "   ${GREEN}Using standard ports (3001, 8001)${NC}"
    else
        # Find alternative ports
        echo -e "   ${YELLOW}Standard ports unavailable, finding alternatives...${NC}"
        BACKEND_PORT=$(find_port 8001)
        FRONTEND_PORT=$(find_port 3001)

        if [ "$BACKEND_PORT" = "0" ] || [ "$FRONTEND_PORT" = "0" ]; then
            echo -e "${RED}❌ No available ports found${NC}"
            exit 1
        fi

        echo -e "   ${YELLOW}Using alternative ports: $FRONTEND_PORT, $BACKEND_PORT${NC}"
        echo -e "   ${YELLOW}⚠️  Nginx will be updated to use these ports${NC}"
    fi
else
    # No nginx - find any available ports (start from 3001/8001)
    echo -e "   ${YELLOW}Finding available ports (no nginx detected)${NC}"

    BACKEND_PORT=$(find_port 8001)
    FRONTEND_PORT=$(find_port 3001)

    if [ "$BACKEND_PORT" = "0" ]; then
        echo -e "${RED}❌ No available port found for backend${NC}"
        exit 1
    fi

    if [ "$FRONTEND_PORT" = "0" ]; then
        echo -e "${RED}❌ No available port found for frontend${NC}"
        exit 1
    fi
fi

echo -e "   ✅ Backend will use port: $BACKEND_PORT"
echo -e "   ✅ Frontend will use port: $FRONTEND_PORT"

# ===== CONFIGURE FRONTEND ENVIRONMENT =====
echo -e "${GREEN}[4/6] Configuring frontend environment...${NC}"

# Create or update frontend .env.local with backend URL
cat > "$FRONTEND_DIR/.env.local" <<EOF
# Auto-generated by start_production.sh
NEXT_PUBLIC_API_URL=http://localhost:$BACKEND_PORT
EOF

echo -e "   ✅ Frontend configured to use backend at http://localhost:$BACKEND_PORT"

# ===== START BACKEND =====
echo -e "${GREEN}[5/6] Starting Backend (Production Mode)...${NC}"
cd "$BACKEND_DIR"
source venv/bin/activate

# Set production environment
export ENVIRONMENT=production

# Start backend with uvicorn (4 workers for better performance)
nohup uvicorn main:app \
    --host 0.0.0.0 \
    --port $BACKEND_PORT \
    --workers 4 \
    --log-level warning \
    > "$LOGS_DIR/backend.log" 2>&1 &

BACKEND_PID=$!
echo $BACKEND_PID > "$PIDS_DIR/backend.pid"
echo -e "   ✅ Backend started (PID: $BACKEND_PID)"
echo -e "      Logs: $LOGS_DIR/backend.log"
echo -e "      URL: http://localhost:$BACKEND_PORT"

# ===== START FRONTEND =====
echo -e "${GREEN}[6/6] Starting Frontend (Production Mode)...${NC}"
cd "$FRONTEND_DIR"

# Start Next.js in production mode with custom port
nohup npx next start -p $FRONTEND_PORT > "$LOGS_DIR/frontend.log" 2>&1 &

FRONTEND_PID=$!
echo $FRONTEND_PID > "$PIDS_DIR/frontend.pid"
echo -e "   ✅ Frontend started (PID: $FRONTEND_PID)"
echo -e "      Logs: $LOGS_DIR/frontend.log"
echo -e "      URL: http://localhost:$FRONTEND_PORT"

# ===== UPDATE NGINX IF USING NON-STANDARD PORTS =====
if [ "$NGINX_CONFIGURED" = true ] && { [ "$BACKEND_PORT" != "8001" ] || [ "$FRONTEND_PORT" != "3001" ]; }; then
    echo -e "${GREEN}Updating Nginx configuration for ports $FRONTEND_PORT and $BACKEND_PORT...${NC}"

    if [ "$EUID" -eq 0 ] || sudo -n true 2>/dev/null; then
        # We have sudo access, update nginx config
        sudo sed -i "s|http://localhost:3001|http://localhost:$FRONTEND_PORT|g" /etc/nginx/sites-available/vibecaster
        sudo sed -i "s|http://localhost:8001|http://localhost:$BACKEND_PORT|g" /etc/nginx/sites-available/vibecaster

        # Test and reload nginx
        if sudo nginx -t >/dev/null 2>&1; then
            sudo systemctl reload nginx
            echo -e "   ✅ Nginx configuration updated and reloaded"
        else
            echo -e "${YELLOW}   ⚠️  Nginx config test failed, manual update may be needed${NC}"
        fi
    else
        echo -e "${YELLOW}   ⚠️  Cannot update nginx (no sudo access)${NC}"
        echo -e "   Manually update /etc/nginx/sites-available/vibecaster:"
        echo -e "   - Change port 3001 to $FRONTEND_PORT"
        echo -e "   - Change port 8001 to $BACKEND_PORT"
        echo -e "   Then: sudo nginx -t && sudo systemctl reload nginx"
    fi
fi

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

if [ "$NGINX_CONFIGURED" = true ]; then
    # Get the domain from nginx config
    NGINX_DOMAIN=$(grep -E "^\s*server_name" /etc/nginx/sites-available/vibecaster | head -1 | awk '{print $2}' | sed 's/;//')
    echo -e "📊 ${GREEN}Access your site at:${NC}"
    echo -e "   ${GREEN}http://$NGINX_DOMAIN${NC}"
    echo ""
    echo -e "📡 ${GREEN}Internal services (localhost only):${NC}"
    echo -e "   Frontend: http://localhost:$FRONTEND_PORT"
    echo -e "   Backend:  http://localhost:$BACKEND_PORT"
    echo -e "   Docs:     http://localhost:$BACKEND_PORT/docs"
else
    echo -e "📊 ${GREEN}Status:${NC}"
    echo -e "   Frontend: http://localhost:$FRONTEND_PORT"
    echo -e "   Backend:  http://localhost:$BACKEND_PORT"
    echo -e "   Docs:     http://localhost:$BACKEND_PORT/docs"
fi

echo ""
echo -e "📝 ${GREEN}Logs:${NC}"
echo -e "   Backend:  tail -f $LOGS_DIR/backend.log"
echo -e "   Frontend: tail -f $LOGS_DIR/frontend.log"
echo ""
echo -e "🛑 ${GREEN}To stop:${NC}"
echo -e "   ./stop_production.sh"
echo ""
