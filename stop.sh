#!/bin/bash
# Vibecaster - Simple Stop Script
# Only kills processes on ports 3001 and 8001 that are NOT docker

cd "$(dirname "$0")"

echo "Stopping Vibecaster..."

# Stop backend on 8001
PID=$(netstat -tlnp 2>/dev/null | grep ":8001 " | grep -v docker | awk '{print $7}' | cut -d'/' -f1)
if [ -n "$PID" ]; then
  echo "  Stopping backend (PID $PID)..."
  kill $PID 2>/dev/null
fi

# Stop frontend on 3001
PID=$(netstat -tlnp 2>/dev/null | grep ":3001 " | grep -v docker | awk '{print $7}' | cut -d'/' -f1)
if [ -n "$PID" ]; then
  echo "  Stopping frontend (PID $PID)..."
  kill $PID 2>/dev/null
fi

echo "Done."
