import os
import secrets
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import RedirectResponse
import tweepy
import requests
from dotenv import load_dotenv
from database import save_oauth_tokens, get_oauth_tokens, delete_oauth_tokens
from auth_utils import get_current_user_id
import time

load_dotenv()

router = APIRouter(prefix="/auth", tags=["auth"])

# OAuth state storage (in-memory for MVP, consider Redis for production)
# Format: {state: {service: str, user_id: int, timestamp: float}}
oauth_states = {}

# Environment variables
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# Twitter/X Configuration
X_CLIENT_ID = os.getenv("X_CLIENT_ID")
X_CLIENT_SECRET = os.getenv("X_CLIENT_SECRET")
X_REDIRECT_URI = os.getenv("X_REDIRECT_URI", "http://127.0.0.1:8000/auth/twitter/callback")

# LinkedIn Configuration
LINKEDIN_CLIENT_ID = os.getenv("LINKEDIN_CLIENT_ID")
LINKEDIN_CLIENT_SECRET = os.getenv("LINKEDIN_CLIENT_SECRET")
LINKEDIN_REDIRECT_URI = os.getenv("LINKEDIN_REDIRECT_URI", "http://127.0.0.1:8000/auth/linkedin/callback")


# ===== TWITTER/X OAUTH =====

@router.get("/twitter/login")
async def twitter_login(user_id: int = Depends(get_current_user_id)):
    """Initiate Twitter OAuth flow."""
    try:
        # Create OAuth2 handler
        oauth2_user_handler = tweepy.OAuth2UserHandler(
            client_id=X_CLIENT_ID,
            redirect_uri=X_REDIRECT_URI,
            scope=["tweet.read", "tweet.write", "users.read", "offline.access"],
            client_secret=X_CLIENT_SECRET
        )

        # Generate authorization URL
        auth_url = oauth2_user_handler.get_authorization_url()

        # Store state for validation (extract from URL)
        state = auth_url.split("state=")[1].split("&")[0] if "state=" in auth_url else None
        if state:
            oauth_states[state] = {"service": "twitter", "user_id": user_id, "timestamp": time.time()}

        return {"auth_url": auth_url}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initiate Twitter OAuth: {str(e)}")


@router.get("/twitter/callback")
async def twitter_callback(code: str = Query(...), state: Optional[str] = Query(None)):
    """Handle Twitter OAuth callback."""
    try:
        # Validate state if present
        if not state or state not in oauth_states:
            return RedirectResponse(url=f"{FRONTEND_URL}?status=twitter_error&error=Invalid state")

        # Get user_id from state
        state_data = oauth_states.pop(state)
        user_id = state_data.get("user_id")

        if not user_id:
            return RedirectResponse(url=f"{FRONTEND_URL}?status=twitter_error&error=User not authenticated")

        # Exchange code for tokens
        oauth2_user_handler = tweepy.OAuth2UserHandler(
            client_id=X_CLIENT_ID,
            redirect_uri=X_REDIRECT_URI,
            scope=["tweet.read", "tweet.write", "users.read", "offline.access"],
            client_secret=X_CLIENT_SECRET
        )

        # Fetch access token
        access_token = oauth2_user_handler.fetch_token(code)

        # Get user info
        client = tweepy.Client(access_token["access_token"])
        me = client.get_me()

        # Save tokens to database
        save_oauth_tokens(
            user_id=user_id,
            service="twitter",
            access_token=access_token["access_token"],
            refresh_token=access_token.get("refresh_token"),
            platform_user_id=str(me.data.id) if me.data else None,
            expires_at=int(time.time()) + access_token.get("expires_in", 7200)
        )

        # Redirect back to frontend with success
        return RedirectResponse(url=f"{FRONTEND_URL}?status=twitter_connected")

    except Exception as e:
        # Redirect back with error
        return RedirectResponse(url=f"{FRONTEND_URL}?status=twitter_error&error={str(e)}")


@router.post("/twitter/disconnect")
async def twitter_disconnect(user_id: int = Depends(get_current_user_id)):
    """Disconnect Twitter account."""
    try:
        delete_oauth_tokens(user_id, "twitter")
        return {"success": True, "message": "Twitter disconnected"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===== LINKEDIN OAUTH =====

@router.get("/linkedin/login")
async def linkedin_login(user_id: int = Depends(get_current_user_id)):
    """Initiate LinkedIn OAuth flow."""
    try:
        # Generate state for CSRF protection
        state = secrets.token_urlsafe(32)
        oauth_states[state] = {"service": "linkedin", "user_id": user_id, "timestamp": time.time()}

        # LinkedIn OAuth URL
        scopes = ["openid", "profile", "w_member_social"]
        auth_url = (
            f"https://www.linkedin.com/oauth/v2/authorization?"
            f"response_type=code&"
            f"client_id={LINKEDIN_CLIENT_ID}&"
            f"redirect_uri={LINKEDIN_REDIRECT_URI}&"
            f"state={state}&"
            f"scope={' '.join(scopes)}"
        )

        return {"auth_url": auth_url}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initiate LinkedIn OAuth: {str(e)}")


@router.get("/linkedin/callback")
async def linkedin_callback(code: str = Query(...), state: Optional[str] = Query(None)):
    """Handle LinkedIn OAuth callback."""
    try:
        # Validate state
        if not state or state not in oauth_states:
            return RedirectResponse(url=f"{FRONTEND_URL}?status=linkedin_error&error=Invalid state")

        # Get user_id from state
        state_data = oauth_states.pop(state)
        user_id = state_data.get("user_id")

        if not user_id:
            return RedirectResponse(url=f"{FRONTEND_URL}?status=linkedin_error&error=User not authenticated")

        # Exchange code for access token
        token_url = "https://www.linkedin.com/oauth/v2/accessToken"
        token_data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": LINKEDIN_REDIRECT_URI,
            "client_id": LINKEDIN_CLIENT_ID,
            "client_secret": LINKEDIN_CLIENT_SECRET
        }

        token_response = requests.post(token_url, data=token_data)
        token_response.raise_for_status()
        tokens = token_response.json()

        # Get user info
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        user_response = requests.get("https://api.linkedin.com/v2/userinfo", headers=headers)
        user_response.raise_for_status()
        user_info = user_response.json()

        # Save tokens to database
        save_oauth_tokens(
            user_id=user_id,
            service="linkedin",
            access_token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token"),
            platform_user_id=user_info.get("sub"),
            expires_at=int(time.time()) + tokens.get("expires_in", 5184000)
        )

        # Redirect back to frontend with success
        return RedirectResponse(url=f"{FRONTEND_URL}?status=linkedin_connected")

    except Exception as e:
        # Redirect back with error
        return RedirectResponse(url=f"{FRONTEND_URL}?status=linkedin_error&error={str(e)}")


@router.post("/linkedin/disconnect")
async def linkedin_disconnect(user_id: int = Depends(get_current_user_id)):
    """Disconnect LinkedIn account."""
    try:
        delete_oauth_tokens(user_id, "linkedin")
        return {"success": True, "message": "LinkedIn disconnected"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===== STATUS ENDPOINT =====

@router.get("/status")
async def get_auth_status(user_id: int = Depends(get_current_user_id)):
    """Get authentication status for all services."""
    from database import get_connection_status
    return get_connection_status(user_id)
