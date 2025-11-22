#!/bin/bash

# Start Vibecaster Backend
echo "Starting Vibecaster Backend..."

cd "$(dirname "$0")/backend"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Creating one..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "WARNING: .env file not found!"
    echo "Please copy .env.example to .env and add your API credentials."
    exit 1
fi

# Install/update dependencies
echo "Checking dependencies..."
pip install -q -r requirements.txt

# Start the server
echo "Starting FastAPI server on http://127.0.0.1:8000"
python main.py
