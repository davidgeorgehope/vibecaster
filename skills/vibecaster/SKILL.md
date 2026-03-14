---
name: vibecaster
description: Manage Vibecaster social media posts via the vibecaster CLI. Vibecaster is a skill for AI agents that generates and posts content to Twitter/X, LinkedIn, and YouTube. Use when a user asks to post to social media, manage campaigns, transcribe media, generate video, or manage API keys.
metadata:
  author: davidgeorgehope
  version: "1.0.0"
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
vibecaster campaign edit --schedule daily --time 09:00  # Edit campaign settings
vibecaster campaign reset                                # Delete and reset campaign
```

### Content Generation

```bash
vibecaster create "topic"            # AI-generate a post from a prompt
vibecaster generate <url>            # Generate posts from URL (preview only)
vibecaster post <url>                # Generate + post to connected platforms
```

### Direct Posting

```bash
vibecaster post "text" --platform linkedin          # Post custom text
vibecaster post "text" --media image.png            # Post with image/video
vibecaster post "text" --imagegen "prompt"           # Post with AI-generated image
```

### Transcribe & Video

```bash
vibecaster transcribe <file>            # Transcribe audio/video → transcript, summary, blog post
vibecaster transcribe <file> -o ./out   # Save output to files
vibecaster video "topic"                # Generate multi-scene AI video
vibecaster video "topic" --style educational --duration 24
vibecaster video-post <file>            # Transcribe video + generate platform posts
vibecaster video-post <file> -p all     # Transcribe + post to all platforms
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
