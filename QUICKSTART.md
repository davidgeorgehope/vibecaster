# Vibecaster - Quick Start Guide

## Setup (First Time Only)

### 1. Install Python Dependencies

```bash
cd backend
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux
# OR on Windows: venv\Scripts\activate
pip install -r requirements.txt
cd ..
```

### 2. Configure API Credentials

```bash
cd backend
cp .env.example .env
# Edit .env and add your API keys
cd ..
```

You need:
- **Google Gemini API Key**: Get from [Google AI Studio](https://makersuite.google.com/app/apikey)
- **X/Twitter OAuth**: From [Twitter Developer Portal](https://developer.twitter.com/en/portal/dashboard)
- **LinkedIn OAuth**: From [LinkedIn Developers](https://www.linkedin.com/developers/apps)

### 3. Install Frontend Dependencies

```bash
# Already done during project creation
# If needed: cd frontend && npm install
```

## Running the Application

### Option 1: Using Helper Scripts (Recommended)

**Terminal 1 - Backend:**
```bash
./start-backend.sh
```

**Terminal 2 - Frontend:**
```bash
./start-frontend.sh
```

### Option 2: Manual Start

**Terminal 1 - Backend:**
```bash
cd backend
source venv/bin/activate
python main.py
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
```

## Access the Application

Open your browser to: **http://localhost:3000**

## First Use

1. **Connect Accounts**:
   - Click "Connect" on X (Twitter)
   - Click "Connect" on LinkedIn
   - Authenticate with each platform

2. **Set Campaign Prompt**:
   - Example: "Post daily tips about Python programming"
   - Click "Activate Campaign"

3. **Run Now or Wait**:
   - Click "Run Now" to post immediately
   - Or wait for scheduled time (daily at 9 AM)

## Stopping the Application

Press `Ctrl+C` in both terminal windows to stop the servers.

## Troubleshooting

**Backend won't start:**
- Check that .env file exists with valid API keys
- Ensure Python 3.12+ is installed: `python3 --version`
- Activate virtual environment: `source backend/venv/bin/activate`

**Frontend won't start:**
- Ensure Node.js is installed: `node --version`
- Try: `cd frontend && rm -rf node_modules && npm install`

**OAuth not working:**
- Verify redirect URIs match exactly in developer portals
- Check that API credentials in .env are correct

## Next Steps

See [README.md](README.md) for full documentation, API reference, and customization options.
