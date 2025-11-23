#!/bin/bash

# Quick fix for nginx to properly serve Next.js static files
# Run this if you're getting 404 errors for _next/static/* files

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}Fixing Nginx for Next.js static files...${NC}"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}❌ This script must be run as root${NC}"
    echo "   Run with: sudo ./fix_nginx.sh"
    exit 1
fi

# Check if nginx config exists
if [ ! -f "/etc/nginx/sites-available/vibecaster" ]; then
    echo -e "${RED}❌ Nginx config not found${NC}"
    echo "   Run: sudo ./setup_nginx.sh first"
    exit 1
fi

# Backup existing config
cp /etc/nginx/sites-available/vibecaster /etc/nginx/sites-available/vibecaster.backup
echo -e "${GREEN}✅ Backed up config to vibecaster.backup${NC}"

# Check if _next/static location already exists
if grep -q "location /_next/static/" /etc/nginx/sites-available/vibecaster; then
    echo -e "${YELLOW}⚠️  Config already has _next/static location block${NC}"
    echo "   Your config might already be fixed"
    exit 0
fi

# Add _next/static location block before the first 'location /' block
# This is a bit tricky, so we'll recreate the relevant section
echo -e "${GREEN}Updating nginx configuration...${NC}"

# Use sed to add the new location blocks before 'location / {'
sed -i '/location \/ {/i\
    # Next.js static files and assets (must come before / location)\
    location /_next/static/ {\
        proxy_pass http://localhost:3000;\
        proxy_http_version 1.1;\
        proxy_set_header Host $host;\
        proxy_set_header X-Real-IP $remote_addr;\
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\
        proxy_set_header X-Forwarded-Proto $scheme;\
        # Cache static assets for 1 year\
        proxy_cache_bypass $http_upgrade;\
        add_header Cache-Control "public, max-age=31536000, immutable";\
    }\
\
    # Next.js public files\
    location /public/ {\
        proxy_pass http://localhost:3000;\
        proxy_http_version 1.1;\
        proxy_set_header Host $host;\
    }\
' /etc/nginx/sites-available/vibecaster

echo -e "${GREEN}✅ Configuration updated${NC}"

# Test nginx configuration
echo -e "${GREEN}Testing nginx configuration...${NC}"
if nginx -t; then
    echo -e "${GREEN}✅ Configuration is valid${NC}"

    # Reload nginx
    echo -e "${GREEN}Reloading nginx...${NC}"
    systemctl reload nginx

    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║   ✅ Nginx fixed successfully!        ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "Try accessing your site again."
    echo -e "The _next/static/* files should now load correctly."
    echo ""
else
    echo -e "${RED}❌ Nginx configuration test failed!${NC}"
    echo -e "   Restoring backup..."
    cp /etc/nginx/sites-available/vibecaster.backup /etc/nginx/sites-available/vibecaster
    echo -e "   ${YELLOW}Config restored to previous version${NC}"
    exit 1
fi
