# Vibecaster Production Deployment Guide

This guide covers running Vibecaster in production mode with proper process management and logging.

## Quick Start

```bash
# Start all services in production mode
./start_production.sh

# Check status
./status_production.sh

# Stop all services
./stop_production.sh
```

## Scripts Overview

### `start_production.sh`
Starts both frontend and backend in production mode with:
- ✅ **Backend**: Uvicorn with 4 workers for better performance
- ✅ **Frontend**: Next.js optimized production build
- ✅ **Environment**: Sets `ENVIRONMENT=production` (enforces HTTPS for OAuth)
- ✅ **Background**: Runs as daemon processes
- ✅ **Logging**: All output captured to `logs/` directory
- ✅ **Process Management**: PIDs stored in `pids/` directory

### `stop_production.sh`
Gracefully stops all services:
- Sends SIGTERM for graceful shutdown
- Waits up to 10 seconds per service
- Force kills if graceful shutdown fails
- Cleans up PID files

### `status_production.sh`
Shows current status of all services:
- Process IDs and running state
- Service URLs
- Recent log activity (last 5 lines)
- Quick links to view full logs

## Directory Structure

```
vibecaster/
├── logs/              # Created by start script
│   ├── backend.log    # Backend logs
│   └── frontend.log   # Frontend logs
├── pids/              # Created by start script
│   ├── backend.pid    # Backend process ID
│   └── frontend.pid   # Frontend process ID
└── ...
```

## Prerequisites

### Backend
1. Python 3.8+ installed
2. `.env` file configured with production settings
3. All required Python packages in `requirements.txt`

### Frontend
1. Node.js 18+ installed
2. All npm dependencies installed

## Production Checklist

Before running in production:

- [ ] Set `ENVIRONMENT=production` in `.env` (or remove it - defaults to production)
- [ ] Configure HTTPS/SSL certificates for your domain
- [ ] Update OAuth redirect URIs to production URLs
- [ ] Set secure `JWT_SECRET_KEY`
- [ ] Configure proper CORS origins in `main.py`
- [ ] Test all OAuth flows work over HTTPS

## Configuration Differences

### Development vs Production

| Feature | Development | Production |
|---------|------------|------------|
| OAuth Transport | HTTP allowed | HTTPS required |
| Backend Workers | 1 (auto-reload) | 4 (performance) |
| Frontend Build | Dev mode | Optimized build |
| Logging | Console | Files in `logs/` |
| Process Mode | Foreground | Background daemon |
| Hot Reload | ✅ Yes | ❌ No |

## Monitoring

### View Logs
```bash
# Follow backend logs in real-time
tail -f logs/backend.log

# Follow frontend logs in real-time
tail -f logs/frontend.log

# View last 100 lines
tail -n 100 logs/backend.log
```

### Check Process Status
```bash
# Quick status check
./status_production.sh

# Check if processes are running
ps aux | grep uvicorn
ps aux | grep next
```

## Troubleshooting

### Services Won't Start

1. **Check if already running:**
   ```bash
   ./status_production.sh
   ```

2. **Stop existing services:**
   ```bash
   ./stop_production.sh
   ```

3. **Check logs for errors:**
   ```bash
   cat logs/backend.log
   cat logs/frontend.log
   ```

4. **Verify environment:**
   ```bash
   # Backend
   cd backend
   source venv/bin/activate
   python -c "from database import init_database; init_database()"

   # Frontend
   cd frontend
   npm run build
   ```

### OAuth Not Working

If OAuth fails in production:

1. Ensure `ENVIRONMENT=production` is NOT set to `development`
2. Verify you're accessing via HTTPS (not HTTP)
3. Check OAuth redirect URIs match your production domain
4. Review `logs/backend.log` for OAuth errors

### Port Already in Use

If ports 3000 or 8000 are taken:

```bash
# Find what's using the port
lsof -i :3000
lsof -i :8000

# Kill the process
kill -9 <PID>
```

## Performance Tuning

### Backend Workers

Default: 4 workers. Adjust in `start_production.sh`:

```bash
# For more concurrent requests (high CPU usage)
--workers 8

# For lower resource usage
--workers 2
```

**Rule of thumb:** `workers = (2 × CPU cores) + 1`

### Frontend Port

To change from default 3000, modify `frontend/package.json`:

```json
{
  "scripts": {
    "start": "next start -p 4000"
  }
}
```

## Advanced: Using with Reverse Proxy

For production deployments, use nginx or similar:

```nginx
# Example nginx config
server {
    listen 80;
    server_name yourdomain.com;

    # Frontend
    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # Backend API
    location /api {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Security Notes

🔒 **Important:**

- Never commit `logs/` or `pids/` directories (already in `.gitignore`)
- Keep `.env` file secure with proper permissions: `chmod 600 backend/.env`
- Use strong `JWT_SECRET_KEY` (32+ random characters)
- Enable HTTPS in production (required for OAuth)
- Regularly rotate API keys and tokens
- Monitor `logs/` for suspicious activity

## Backup & Disaster Recovery

### Database Backup

```bash
# Backup database
cp backend/vibecaster.db backup/vibecaster_$(date +%Y%m%d_%H%M%S).db

# Restore from backup
cp backup/vibecaster_20241123_120000.db backend/vibecaster.db
```

### Automated Backups

Add to crontab:
```bash
# Daily backup at 2 AM
0 2 * * * cp /path/to/vibecaster/backend/vibecaster.db /path/to/backups/vibecaster_$(date +\%Y\%m\%d).db
```

## Support

For issues:
1. Check `logs/backend.log` and `logs/frontend.log`
2. Review this documentation
3. Check GitHub issues: https://github.com/davidgeorgehope/vibecaster
