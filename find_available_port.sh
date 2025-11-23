#!/bin/bash

# Find an available port starting from a given port number
# Usage: ./find_available_port.sh [starting_port]

START_PORT=${1:-8000}
MAX_PORT=65535

for port in $(seq $START_PORT $MAX_PORT); do
    if ! lsof -i :$port >/dev/null 2>&1 && ! netstat -tuln 2>/dev/null | grep -q ":$port "; then
        echo $port
        exit 0
    fi
done

echo "No available ports found" >&2
exit 1
