#!/bin/bash

# Vibecaster Server Setup Script
# Run this FIRST on a fresh Ubuntu/Debian server to install all dependencies

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Vibecaster Server Setup              ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
echo ""

# Check if running as root or with sudo
if [ "$EUID" -ne 0 ]; then
    echo -e "${YELLOW}⚠️  This script needs sudo privileges for system package installation${NC}"
    echo "   Re-run with: sudo ./setup_server.sh"
    exit 1
fi

# Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$NAME
    VER=$VERSION_ID
else
    echo -e "${RED}❌ Cannot detect OS${NC}"
    exit 1
fi

echo -e "${GREEN}Detected OS: $OS $VER${NC}"
echo ""

# Update package list
echo -e "${GREEN}[1/5] Updating package list...${NC}"
apt-get update -qq

# Install Python 3 and venv
echo -e "${GREEN}[2/5] Installing Python 3 and dependencies...${NC}"
apt-get install -y -qq python3 python3-pip python3-venv python3-dev build-essential

PYTHON_VERSION=$(python3 --version)
echo -e "   ✅ Installed: $PYTHON_VERSION"

# Install Node.js and npm
echo -e "${GREEN}[3/5] Installing Node.js and npm...${NC}"

# Check if Node.js is already installed and version is adequate
if command -v node &> /dev/null; then
    NODE_VERSION=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
    if [ "$NODE_VERSION" -ge 18 ]; then
        echo -e "   ✅ Node.js $(node -v) already installed"
    else
        echo "   Upgrading Node.js (current version too old)..."
        curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
        apt-get install -y -qq nodejs
    fi
else
    # Install Node.js 20.x
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y -qq nodejs
fi

NODE_VERSION=$(node -v)
NPM_VERSION=$(npm -v)
echo -e "   ✅ Node.js: $NODE_VERSION"
echo -e "   ✅ npm: $NPM_VERSION"

# Install additional useful tools
echo -e "${GREEN}[4/5] Installing additional tools...${NC}"
apt-get install -y -qq git curl wget

echo -e "   ✅ git: $(git --version | cut -d' ' -f3)"
echo -e "   ✅ curl: $(curl --version | head -n1 | cut -d' ' -f2)"

# Verify installation
echo -e "${GREEN}[5/5] Verifying installation...${NC}"

MISSING=0

if ! command -v python3 &> /dev/null; then
    echo -e "   ${RED}❌ Python 3 not found${NC}"
    MISSING=1
else
    echo -e "   ✅ Python 3: $(python3 --version)"
fi

if ! python3 -m pip --version &> /dev/null; then
    echo -e "   ${RED}❌ pip not found${NC}"
    MISSING=1
else
    echo -e "   ✅ pip: $(python3 -m pip --version | cut -d' ' -f2)"
fi

if ! python3 -c "import venv" 2>/dev/null; then
    echo -e "   ${RED}❌ python3-venv not found${NC}"
    MISSING=1
else
    echo -e "   ✅ python3-venv: installed"
fi

if ! command -v node &> /dev/null; then
    echo -e "   ${RED}❌ Node.js not found${NC}"
    MISSING=1
else
    echo -e "   ✅ Node.js: $(node -v)"
fi

if ! command -v npm &> /dev/null; then
    echo -e "   ${RED}❌ npm not found${NC}"
    MISSING=1
else
    echo -e "   ✅ npm: $(npm -v)"
fi

echo ""

if [ $MISSING -eq 1 ]; then
    echo -e "${RED}❌ Some dependencies are missing. Please install them manually.${NC}"
    exit 1
fi

# Success message
echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   ✅ Server setup complete!            ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}Next steps:${NC}"
echo -e "   1. Configure backend/.env with your API keys"
echo -e "   2. Run: ./start_production.sh"
echo ""
echo -e "${GREEN}Optional: Configure firewall${NC}"
echo -e "   ufw allow 22     # SSH"
echo -e "   ufw allow 80     # HTTP"
echo -e "   ufw allow 443    # HTTPS"
echo -e "   ufw allow 3000   # Frontend (if not using reverse proxy)"
echo -e "   ufw allow 8000   # Backend (if not using reverse proxy)"
echo -e "   ufw enable"
echo ""
