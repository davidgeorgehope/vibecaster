---
name: vibecaster
description: Manage Vibecaster campaigns and posts via the `vibecaster` CLI. Use when a user asks to check Vibecaster status, manage social media campaigns, generate or post content from URLs, trigger campaign runs, or manage Vibecaster API keys. Vibecaster is an AI-powered social media automation platform (Twitter/X, LinkedIn, YouTube).
metadata:
  {
    "openclaw": { "emoji": "📣", "requires": { "anyBins": ["vibecaster"] } }
  }
---

# Vibecaster CLI

AI-powered social media automation. Generate and post content to Twitter/X, LinkedIn, and YouTube.

## Setup

Config lives at `~/.vibecaster/config.json`. Login with an API key created from the Vibecaster web UI (https://vibecaster.ai → Dashboard → CLI tab).

```bash
# No install needed — just use npx
npx vibecaster login
# Prompts for API URL (default: https://vibecaster.ai/api) and API key (vb_...)

# Or install globally
npm install -g vibecaster
vibecaster login
```

## Commands

### Status & Campaign

```bash
vibecaster status                    # Connections + campaign overview
vibecaster campaign                  # Detailed campaign info
vibecaster campaign setup "prompt"   # Create/update campaign with AI prompt
vibecaster campaign activate         # Start automated posting
vibecaster campaign deactivate       # Pause posting
vibecaster run                       # Trigger immediate campaign run
```

### Content Generation

```bash
vibecaster generate <url>            # Generate posts from URL (preview only)
vibecaster post <url>                # Generate + post to connected platforms
```

### API Key Management

```bash
vibecaster keys list                 # List all API keys
vibecaster keys create "key name"    # Create new key (shown once!) — JWT only, use web UI
vibecaster keys revoke <id>          # Revoke a key — JWT only, use web UI
```

**Note:** Creating and revoking keys requires JWT auth (web session). Use the web UI at https://vibecaster.ai → Dashboard → CLI tab. The `keys list` command works with API key auth.

## Auth

All API calls use `X-API-Key` header. Keys are prefixed `vb_` and stored hashed server-side. The full key is shown exactly once on creation.

## API Base

- Production: `https://vibecaster.ai/api`
- Proxied through Cloudflare tunnel → Hetzner backend (FastAPI + SQLite)

## Infrastructure

- Backend: `/root/vibecaster/backend/` on Hetzner (FastAPI, port 8001)
- Frontend: `/root/vibecaster/frontend/` (Next.js, port 3001)
- CLI source: `/root/vibecaster/cli/` (Node.js + commander)
- Start/stop: `/root/vibecaster/start.sh` / `/root/vibecaster/stop.sh`
- DB: `/root/vibecaster/backend/vibecaster.db` (SQLite)
