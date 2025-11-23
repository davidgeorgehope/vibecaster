# Using Vibecaster with Cloudflare and HTTPS

If you're using Cloudflare as your DNS/proxy, here's how to configure Vibecaster properly.

## HTTPS vs HTTP

**Question:** Will it matter if I access it on HTTPS?

**Answer:** YES, it matters a lot! Here's what you need to know:

### The Problem

When users access your site via HTTPS (through Cloudflare), but your backend OAuth URLs are HTTP:

```
Browser: https://your-domain.com (HTTPS) ✅
   ↓
Cloudflare Proxy (HTTPS -> HTTP)
   ↓
Your Server: http://your-server (HTTP)
   ↓
OAuth Redirect: http://your-domain.com/auth/twitter/callback ❌ BREAKS!
```

**What breaks:**
- ❌ OAuth redirects fail (Twitter/LinkedIn require HTTPS in production)
- ❌ Mixed content warnings
- ❌ Cookies might not work properly
- ❌ Browser security warnings

---

## Solution: Configure for HTTPS

### Step 1: Update Backend Environment

Edit `backend/.env`:

```bash
# Change from:
FRONTEND_URL=http://your-domain.com
X_REDIRECT_URI=http://your-domain.com/auth/twitter/callback
LINKEDIN_REDIRECT_URI=http://your-domain.com/auth/linkedin/callback

# To:
FRONTEND_URL=https://your-domain.com
X_REDIRECT_URI=https://your-domain.com/auth/twitter/callback
LINKEDIN_REDIRECT_URI=https://your-domain.com/auth/linkedin/callback
ENVIRONMENT=production
```

**Important:** Use `https://` not `http://`

### Step 2: Update OAuth App Settings

**Twitter Developer Portal:**
- Go to: https://developer.twitter.com/en/portal/projects-and-apps
- Update Callback URL: `https://your-domain.com/auth/twitter/callback`

**LinkedIn Developer Portal:**
- Go to: https://www.linkedin.com/developers/apps
- Update Redirect URL: `https://your-domain.com/auth/linkedin/callback`

### Step 3: Configure Cloudflare SSL

**In Cloudflare Dashboard:**

1. Go to SSL/TLS settings
2. Set SSL mode to **"Flexible"** or **"Full"**

**"Flexible" (easiest):**
- Cloudflare to Browser: HTTPS ✅
- Cloudflare to Your Server: HTTP
- Good for: Getting started quickly

**"Full" (better):**
- Cloudflare to Browser: HTTPS ✅
- Cloudflare to Your Server: HTTPS
- Requires: SSL certificate on your server

### Step 4: (Optional) Enable Full SSL on Your Server

If using Cloudflare "Full" mode, install SSL on your server:

```bash
# Install certbot
sudo apt-get install certbot python3-certbot-nginx

# Get SSL certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal is configured automatically
```

**Note:** With Cloudflare, you can also use their Origin Certificates instead of Let's Encrypt.

### Step 5: Update Nginx for HTTPS (if using Full mode)

The `setup_nginx.sh` script creates HTTP config. For HTTPS:

```bash
# After running certbot, nginx config is auto-updated
# Or manually edit /etc/nginx/sites-available/vibecaster

# Test config
sudo nginx -t

# Reload
sudo systemctl reload nginx
```

### Step 6: Restart Services

```bash
cd ~/vibecaster
./stop_production.sh
./start_production.sh
```

---

## Cloudflare Settings Recommendations

### SSL/TLS Settings
- **SSL/TLS encryption mode:** Flexible (or Full if you have SSL on server)
- **Always Use HTTPS:** ON
- **Automatic HTTPS Rewrites:** ON
- **Minimum TLS Version:** 1.2

### Security Settings
- **Security Level:** Medium
- **Browser Integrity Check:** ON
- **Hotlink Protection:** Optional

### Speed Settings
- **Auto Minify:** Enable for JavaScript, CSS, HTML
- **Brotli:** ON
- **HTTP/2:** ON

### Page Rules (Optional)
Create a page rule for `https://your-domain.com/*`:
- Cache Level: Standard
- Browser Cache TTL: Respect Existing Headers

---

## Troubleshooting

### "Redirect URI Mismatch" Error

**Problem:** OAuth fails with redirect URI error

**Solution:**
1. Check `backend/.env` has `https://` URLs
2. Verify Twitter/LinkedIn apps use `https://` URLs
3. Make sure URLs exactly match (no trailing slashes, etc.)

### Mixed Content Warnings

**Problem:** Browser shows "Not Secure" warnings

**Solution:**
1. Make sure all URLs in `backend/.env` use `https://`
2. Enable "Automatic HTTPS Rewrites" in Cloudflare
3. Check frontend code doesn't hardcode `http://` URLs

### OAuth Works Locally but Not in Production

**Problem:** OAuth works on `localhost` but fails on production

**Reason:**
- Development uses `ENVIRONMENT=development` (allows HTTP)
- Production uses `ENVIRONMENT=production` (requires HTTPS)

**Solution:**
1. Set `ENVIRONMENT=production` in `backend/.env`
2. Use HTTPS URLs for all OAuth redirects
3. Update OAuth apps to use HTTPS

---

## Quick Reference

### Backend .env for Cloudflare HTTPS

```bash
# API Keys
GEMINI_API_KEY=your_key_here
X_CLIENT_ID=your_client_id
X_CLIENT_SECRET=your_secret
LINKEDIN_CLIENT_ID=your_client_id
LINKEDIN_CLIENT_SECRET=your_secret

# Production URLs (HTTPS!)
FRONTEND_URL=https://your-domain.com
X_REDIRECT_URI=https://your-domain.com/auth/twitter/callback
LINKEDIN_REDIRECT_URI=https://your-domain.com/auth/linkedin/callback

# Production mode (enforces HTTPS for OAuth)
ENVIRONMENT=production

# JWT Secret
JWT_SECRET_KEY=your_generated_secret_key
```

### Cloudflare SSL Modes Explained

| Mode | Browser → CF | CF → Server | Use Case |
|------|--------------|-------------|----------|
| **Off** | HTTP | HTTP | Never use |
| **Flexible** | HTTPS | HTTP | Quick setup, good enough |
| **Full** | HTTPS | HTTPS (any cert) | Better security |
| **Full (Strict)** | HTTPS | HTTPS (valid cert) | Best security |

For Vibecaster: **Flexible** or **Full** are fine.

---

## Testing

After configuration:

1. **Access your site:** https://your-domain.com
2. **Check SSL:** Should show padlock in browser
3. **Test OAuth:** Try connecting Twitter and LinkedIn
4. **Check redirects:** Should redirect to https:// URLs
5. **Monitor logs:** `tail -f logs/backend.log`

---

## Common Issues

### "This site can't provide a secure connection"

**Cause:** Cloudflare SSL not configured

**Fix:**
- Go to Cloudflare → SSL/TLS
- Set to "Flexible" or "Full"
- Wait 5 minutes for propagation

### OAuth callback gets 404

**Cause:** Nginx not proxying /auth correctly

**Fix:**
- Check `/etc/nginx/sites-available/vibecaster` has `/auth` location block
- Reload nginx: `sudo systemctl reload nginx`

### Backend logs show "OAUTHLIB_INSECURE_TRANSPORT"

**Cause:** `ENVIRONMENT=development` in production

**Fix:**
- Set `ENVIRONMENT=production` in `backend/.env`
- Restart: `./stop_production.sh && ./start_production.sh`

---

## Summary

✅ **DO:**
- Use `https://` URLs in `backend/.env`
- Set `ENVIRONMENT=production`
- Update OAuth apps to use `https://` callback URLs
- Enable Cloudflare SSL (Flexible or Full mode)

❌ **DON'T:**
- Use `http://` URLs in production
- Keep `ENVIRONMENT=development` in production
- Mix HTTP and HTTPS URLs
- Forget to update OAuth app settings
