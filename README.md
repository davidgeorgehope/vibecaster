# VIBECASTER

> AI-powered local-first social media automation platform

Vibecaster is a monolithic localhost application that uses Google Gemini AI and Imagen to automatically generate and post engaging content to your social media accounts.

## Features

- **AI-Powered Content Generation**: Uses Google Gemini 3 for intelligent content creation
- **Image Generation**: Automatic image creation with Imagen 3.0
- **Multi-Platform**: Supports X (Twitter) and LinkedIn
- **Smart Scheduling**: APScheduler for automated posting
- **Local-First**: All data stored locally in SQLite
- **OAuth Security**: Secure platform authentication
- **Real-time Grounding**: Uses Google Search for trending topics

## Architecture

- **Backend**: Python 3.12+ with FastAPI
- **Frontend**: Next.js 15 with App Router
- **Database**: SQLite (local)
- **AI**: Google Gen AI SDK (Gemini + Imagen)
- **Scheduler**: APScheduler

## Prerequisites

- Python 3.12 or higher
- Node.js 18 or higher
- npm or yarn
- Google AI API Key (Gemini/Imagen access)
- X (Twitter) Developer Account with OAuth 2.0 credentials
- LinkedIn Developer Account with OAuth credentials

## Installation

### 1. Clone the Repository

```bash
cd vibecaster
```

### 2. Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file from template
cp .env.example .env
```

### 3. Configure Environment Variables

Edit `backend/.env` and add your API credentials:

```env
# Google AI (Gemini/Imagen) API Key
GEMINI_API_KEY=your_gemini_api_key_here

# Twitter/X OAuth Credentials
X_API_KEY=your_x_api_key
X_API_SECRET=your_x_api_secret
X_CLIENT_ID=your_x_client_id
X_CLIENT_SECRET=your_x_client_secret
X_REDIRECT_URI=http://127.0.0.1:8000/auth/twitter/callback

# LinkedIn OAuth Credentials
LINKEDIN_CLIENT_ID=your_linkedin_client_id
LINKEDIN_CLIENT_SECRET=your_linkedin_client_secret
LINKEDIN_REDIRECT_URI=http://127.0.0.1:8000/auth/linkedin/callback

# Application Settings
FRONTEND_URL=http://localhost:3000
```

#### Getting API Credentials

**Google AI (Gemini/Imagen)**
1. Visit [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Create a new API key
3. Copy the key to `GEMINI_API_KEY`

**X (Twitter)**
1. Go to [Twitter Developer Portal](https://developer.twitter.com/en/portal/dashboard)
2. Create a new app with OAuth 2.0
3. Enable "Read and Write" permissions
4. Add callback URL: `http://127.0.0.1:8000/auth/twitter/callback`
5. Copy credentials to `.env`

**LinkedIn**
1. Visit [LinkedIn Developers](https://www.linkedin.com/developers/apps)
2. Create a new app
3. Add required products: "Sign In with LinkedIn" and "Share on LinkedIn"
4. Add redirect URL: `http://127.0.0.1:8000/auth/linkedin/callback`
5. Copy credentials to `.env`

### 4. Frontend Setup

```bash
# Navigate to frontend directory
cd ../frontend

# Install dependencies (already done during setup)
npm install

# Start development server
npm run dev
```

## Usage

### Starting the Application

1. **Start the Backend** (in `backend/` directory):
```bash
source venv/bin/activate  # On macOS/Linux
python main.py
```

The backend will start on `http://127.0.0.1:8000`

2. **Start the Frontend** (in `frontend/` directory):
```bash
npm run dev
```

The frontend will start on `http://localhost:3000`

3. **Open your browser** and navigate to `http://localhost:3000`

### Configuring Your Campaign

1. **Connect Social Accounts**:
   - Click "Connect" on the X (Twitter) box
   - Click "Connect" on the LinkedIn box
   - Authenticate with each platform

2. **Set Your Campaign Prompt**:
   - Enter your content theme in the prompt box
   - Example: "Post anime OpenTelemetry memes daily"
   - Click "Activate Campaign"

3. **AI Analysis**:
   - The system will analyze your prompt
   - Generate a refined persona for your account
   - Create visual style guidelines
   - Configure the posting schedule

4. **Automated Posting**:
   - Posts will be generated daily at 9 AM (configurable)
   - Each cycle includes:
     - Search for trending topics
     - Draft post with AI
     - Critique and refine
     - Generate accompanying image
     - Post to connected platforms

### Manual Run

Click the "Run Now" button to trigger an immediate posting cycle without waiting for the scheduled time.

## Project Structure

```
vibecaster/
├── backend/
│   ├── main.py              # FastAPI app + Scheduler
│   ├── database.py          # SQLite operations
│   ├── agents.py            # Gemini/Imagen AI logic
│   ├── auth.py              # OAuth handlers
│   ├── .env                 # Environment variables (create from .env.example)
│   ├── .env.example         # Environment template
│   ├── requirements.txt     # Python dependencies
│   └── vibecaster.db        # SQLite database (auto-created)
│
├── frontend/
│   ├── app/
│   │   ├── page.tsx         # Main UI (three-box layout)
│   │   ├── layout.tsx       # Root layout
│   │   └── globals.css      # Global styles
│   ├── components/
│   │   ├── ConnectionBox.tsx # OAuth connection UI
│   │   └── PromptBox.tsx     # Campaign prompt UI
│   ├── next.config.ts       # Next.js config (API proxy)
│   └── package.json         # Node dependencies
│
└── README.md                # This file
```

## API Endpoints

### Authentication
- `GET /auth/twitter/login` - Initiate Twitter OAuth
- `GET /auth/twitter/callback` - Twitter OAuth callback
- `POST /auth/twitter/disconnect` - Disconnect Twitter
- `GET /auth/linkedin/login` - Initiate LinkedIn OAuth
- `GET /auth/linkedin/callback` - LinkedIn OAuth callback
- `POST /auth/linkedin/disconnect` - Disconnect LinkedIn
- `GET /auth/status` - Get connection status

### Campaign Management
- `GET /api/status` - System status
- `GET /api/campaign` - Get campaign configuration
- `POST /api/setup` - Setup/update campaign
- `POST /api/run-now` - Manually trigger posting cycle
- `DELETE /api/campaign` - Delete campaign

## Customization

### Changing Schedule

Edit the cron schedule in the setup request (default is `0 9 * * *` for daily at 9 AM):

```typescript
// In page.tsx
schedule_cron: '0 */4 * * *'  // Every 4 hours
schedule_cron: '0 9,17 * * *' // Twice daily at 9 AM and 5 PM
```

### Adjusting AI Behavior

Edit `backend/agents.py` to customize:
- Temperature for creativity
- Search query formatting
- Post length and style
- Image generation parameters

## Troubleshooting

### Backend Issues

**Database errors**:
```bash
# Delete and reinitialize database
rm backend/vibecaster.db
python backend/main.py
```

**Import errors**:
```bash
# Ensure virtual environment is activated
source backend/venv/bin/activate
pip install -r backend/requirements.txt
```

### Frontend Issues

**Module not found**:
```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
```

**API connection errors**:
- Ensure backend is running on port 8000
- Check `next.config.ts` rewrites configuration

### OAuth Issues

**Twitter/X callback fails**:
- Verify redirect URI matches exactly in Twitter Developer Portal
- Ensure app has "Read and Write" permissions

**LinkedIn callback fails**:
- Verify redirect URI in LinkedIn Developer Portal
- Ensure required products are added to the app

## Security Notes

- **Never commit `.env` files** - they contain sensitive credentials
- **OAuth tokens** are stored locally in SQLite
- **Database file** should be backed up regularly
- **API keys** should be rotated periodically
- Run on **localhost only** for MVP (not production-ready)

## Limitations

This is an MVP (Minimum Viable Product) with the following limitations:

- **Single user only** - designed for personal use
- **No authentication** - frontend has no login
- **Local only** - not designed for deployment
- **Limited error handling** - may require manual intervention
- **No image upload for LinkedIn** - text posts only (MVP limitation)

## Future Enhancements

- Multi-user support with authentication
- Advanced scheduling options (time zones, multiple schedules)
- Analytics dashboard
- Post preview before publishing
- Content approval workflow
- Support for more platforms (Instagram, Facebook, etc.)
- Image upload for LinkedIn
- A/B testing for post variations

## License

MIT License - feel free to modify and use for personal projects.

## Support

For issues and questions:
1. Check the Troubleshooting section
2. Review API credentials in `.env`
3. Check backend logs in terminal
4. Ensure all dependencies are installed

---

Built with ❤️ using Google Gemini AI and Imagen
