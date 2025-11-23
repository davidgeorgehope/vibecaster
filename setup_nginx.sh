#!/bin/bash

# Nginx Setup Script for Vibecaster
# Sets up reverse proxy for production deployment

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Vibecaster Nginx Setup               ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}❌ This script must be run as root${NC}"
    echo "   Run with: sudo ./setup_nginx.sh"
    exit 1
fi

# Get domain/IP from user
echo -e "${YELLOW}Enter your domain name or server IP:${NC}"
read -p "Domain/IP: " DOMAIN

if [ -z "$DOMAIN" ]; then
    echo -e "${RED}❌ Domain/IP is required${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}[1/5] Installing Nginx...${NC}"
apt-get update -qq
apt-get install -y -qq nginx

echo -e "${GREEN}[2/5] Creating Nginx configuration...${NC}"

# Create nginx config
cat > /etc/nginx/sites-available/vibecaster <<EOF
server {
    listen 80;
    server_name $DOMAIN;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Increase max upload size for images
    client_max_body_size 10M;

    # Next.js static files and assets (must come before / location)
    location /_next/static/ {
        proxy_pass http://localhost:3001;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        # Cache static assets for 1 year
        proxy_cache_bypass \$http_upgrade;
        add_header Cache-Control "public, max-age=31536000, immutable";
    }

    # Next.js public files
    location /public/ {
        proxy_pass http://localhost:3001;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
    }

    # Frontend - Next.js (catch-all for pages)
    location / {
        proxy_pass http://localhost:3001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_cache_bypass \$http_upgrade;
    }

    # Backend API - FastAPI
    location /api {
        proxy_pass http://localhost:8001;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Auth endpoints
    location /auth {
        proxy_pass http://localhost:8001;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # API docs
    location /docs {
        proxy_pass http://localhost:8001;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
    }

    location /openapi.json {
        proxy_pass http://localhost:8001;
    }
}
EOF

echo -e "   ✅ Config created: /etc/nginx/sites-available/vibecaster"

echo -e "${GREEN}[3/5] Enabling site...${NC}"
ln -sf /etc/nginx/sites-available/vibecaster /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default  # Remove default site

echo -e "${GREEN}[4/5] Testing Nginx configuration...${NC}"
nginx -t

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Nginx configuration test failed${NC}"
    exit 1
fi

echo -e "${GREEN}[5/5] Restarting Nginx...${NC}"
systemctl restart nginx
systemctl enable nginx

echo ""
echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   ✅ Nginx setup complete!            ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}Your site is now accessible at:${NC}"
echo -e "   http://$DOMAIN"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo ""
echo -e "1. Update backend/.env with your domain:"
echo -e "   ${GREEN}FRONTEND_URL=http://$DOMAIN${NC}"
echo ""
echo -e "2. Update OAuth redirect URIs in Twitter/LinkedIn:"
echo -e "   Twitter:  http://$DOMAIN/auth/twitter/callback"
echo -e "   LinkedIn: http://$DOMAIN/auth/linkedin/callback"
echo ""
echo -e "3. Configure firewall (if using ufw):"
echo -e "   sudo ufw allow 'Nginx Full'"
echo -e "   sudo ufw allow 22  # Keep SSH open!"
echo -e "   sudo ufw enable"
echo ""
echo -e "4. (Optional) Set up HTTPS with Let's Encrypt:"
echo -e "   sudo apt-get install certbot python3-certbot-nginx"
echo -e "   sudo certbot --nginx -d $DOMAIN"
echo ""
echo -e "${YELLOW}⚠️  Important:${NC}"
echo -e "   - Frontend and Backend should run on localhost:3001 and :8000"
echo -e "   - Nginx will proxy all external traffic through port 80"
echo -e "   - Browser will only talk to Nginx (single domain)"
echo ""
