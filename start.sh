#!/bin/bash
# Vibecaster - Simple Start Script
# Ports: Frontend 3001, Backend 8001

cd "$(dirname "$0")"

echo "Starting Vibecaster..."

# Backend
if ! netstat -tlnp 2>/dev/null | grep -q ":8001 "; then
  echo "  Starting backend on 8001..."
  cd backend && source venv/bin/activate
  nohup uvicorn main:app --host 127.0.0.1 --port 8001 > /tmp/vibecaster-backend.log 2>&1 &
  echo $! > ../pids/backend.pid
  echo "8001" > ../pids/backend.port
  cd ..
  sleep 2
else
  echo "  Backend already running on 8001"
fi

# Frontend
if ! netstat -tlnp 2>/dev/null | grep -q ":3001 "; then
  echo "  Starting frontend on 3001..."
  cd frontend
  nohup npm run start -- -p 3001 > /tmp/vibecaster-frontend.log 2>&1 &
  echo $! > ../pids/frontend.pid
  echo "3001" > ../pids/frontend.port
  cd ..
  sleep 3
else
  echo "  Frontend already running on 3001"
fi

echo "Done. Check: http://localhost:3001"
