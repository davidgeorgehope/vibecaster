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
from logger_config import app_logger as logger
import time

load_dotenv()

router = APIRouter(prefix="/api/auth", tags=["auth"])

# OAuth state storage (in-memory for MVP, consider Redis for production)
# Format: {state: {service: str, user_id: int, timestamp: float, oauth_handler: Optional[object]}}
oauth_states = {}

# Environment variables
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# Twitter/X Configuration - OAuth 1.0a
X_API_KEY = os.getenv("X_API_KEY")
X_API_SECRET = os.getenv("X_API_SECRET")
X_REDIRECT_URI = os.getenv("X_REDIRECT_URI", "http://127.0.0.1:8000/api/auth/twitter/callback")

# LinkedIn Configuration
LINKEDIN_CLIENT_ID = os.getenv("LINKEDIN_CLIENT_ID")
LINKEDIN_CLIENT_SECRET = os.getenv("LINKEDIN_CLIENT_SECRET")
LINKEDIN_REDIRECT_URI = os.getenv("LINKEDIN_REDIRECT_URI", "http://127.0.0.1:8000/api/auth/linkedin/callback")

# YouTube/Google Configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
YOUTUBE_REDIRECT_URI = os.getenv("YOUTUBE_REDIRECT_URI", "http://127.0.0.1:8000/api/auth/youtube/callback")


# ===== TWITTER/X OAUTH =====

@router.get("/twitter/login")
async def twitter_login(user_id: int = Depends(get_current_user_id)):
    """Initiate Twitter OAuth 1.0a flow."""
    try:
        # Create OAuth1 handler
        oauth1_handler = tweepy.OAuth1UserHandler(
            consumer_key=X_API_KEY,
            consumer_secret=X_API_SECRET,
            callback=X_REDIRECT_URI
        )

        # Get authorization URL
        auth_url = oauth1_handler.get_authorization_url()
        logger.info(f"Twitter auth URL: {auth_url}")

        # Store request token for callback validation
        # OAuth 1.0a uses oauth_token as the identifier
        request_token = oauth1_handler.request_token["oauth_token"]
        oauth_states[request_token] = {
            "service": "twitter",
            "user_id": user_id,
            "timestamp": time.time(),
            "oauth_handler": oauth1_handler
        }
        logger.info(f"Stored Twitter OAuth request token: {request_token}")

        return {"auth_url": auth_url}

    except Exception as e:
        logger.error(f"Twitter login error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to initiate Twitter OAuth: {str(e)}")


@router.get("/twitter/callback")
async def twitter_callback(
    oauth_token: str = Query(...),
    oauth_verifier: str = Query(...),
    denied: Optional[str] = Query(None)
):
    """Handle Twitter OAuth 1.0a callback."""
    try:
        # Check if user denied authorization
        if denied:
            logger.warning(f"Twitter OAuth denied: {denied}")
            return RedirectResponse(url=f"{FRONTEND_URL}/dashboard?status=twitter_error&error=Authorization denied")

        # Validate oauth_token
        if not oauth_token or oauth_token not in oauth_states:
            return RedirectResponse(url=f"{FRONTEND_URL}/dashboard?status=twitter_error&error=Invalid oauth_token")

        # Get user_id and OAuth handler from stored state
        state_data = oauth_states.pop(oauth_token)
        user_id = state_data.get("user_id")
        oauth1_handler = state_data.get("oauth_handler")

        if not user_id:
            return RedirectResponse(url=f"{FRONTEND_URL}/dashboard?status=twitter_error&error=User not authenticated")

        if not oauth1_handler:
            return RedirectResponse(url=f"{FRONTEND_URL}/dashboard?status=twitter_error&error=OAuth handler not found")

        # Get access token using the verifier
        logger.info(f"Fetching Twitter access token with verifier...")
        access_token, access_token_secret = oauth1_handler.get_access_token(oauth_verifier)
        logger.info(f"Successfully received access token")

        # Create client with OAuth 1.0a credentials to get user info
        client = tweepy.Client(
            consumer_key=X_API_KEY,
            consumer_secret=X_API_SECRET,
            access_token=access_token,
            access_token_secret=access_token_secret
        )
        me = client.get_me()

        # Extract user ID
        platform_user_id = None
        if me and me.data:
            platform_user_id = str(me.data.id)
        else:
            logger.warning("Could not fetch Twitter user info")

        # Save tokens to database
        # OAuth 1.0a tokens don't expire, so we set a far future expiration
        save_oauth_tokens(
            user_id=user_id,
            service="twitter",
            access_token=access_token,
            refresh_token=access_token_secret,  # Store access_token_secret in refresh_token field
            platform_user_id=platform_user_id,
            expires_at=int(time.time()) + (365 * 24 * 60 * 60)  # 1 year (tokens don't expire)
        )

        logger.info(f"Successfully saved Twitter tokens for user {user_id}")

        # Redirect back to frontend with success
        return RedirectResponse(url=f"{FRONTEND_URL}/dashboard?status=twitter_connected")

    except Exception as e:
        # Log the full error for debugging
        logger.error(f"Twitter OAuth error: {str(e)}", exc_info=True)
        # Redirect back with error
        error_msg = str(e)[:200]  # Limit error message length for URL
        return RedirectResponse(url=f"{FRONTEND_URL}/dashboard?status=twitter_error&error={error_msg}")


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
            return RedirectResponse(url=f"{FRONTEND_URL}/dashboard?status=linkedin_error&error=Invalid state")

        # Get user_id from state
        state_data = oauth_states.pop(state)
        user_id = state_data.get("user_id")

        if not user_id:
            return RedirectResponse(url=f"{FRONTEND_URL}/dashboard?status=linkedin_error&error=User not authenticated")

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
        return RedirectResponse(url=f"{FRONTEND_URL}/dashboard?status=linkedin_connected")

    except Exception as e:
        # Redirect back with error
        return RedirectResponse(url=f"{FRONTEND_URL}/dashboard?status=linkedin_error&error={str(e)}")


@router.post("/linkedin/disconnect")
async def linkedin_disconnect(user_id: int = Depends(get_current_user_id)):
    """Disconnect LinkedIn account."""
    try:
        delete_oauth_tokens(user_id, "linkedin")
        return {"success": True, "message": "LinkedIn disconnected"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===== YOUTUBE/GOOGLE OAUTH =====

@router.get("/youtube/login")
async def youtube_login(user_id: int = Depends(get_current_user_id)):
    """Initiate YouTube OAuth flow using Google OAuth 2.0."""
    try:
        # Generate state for CSRF protection
        state = secrets.token_urlsafe(32)
        oauth_states[state] = {"service": "youtube", "user_id": user_id, "timestamp": time.time()}

        # YouTube/Google OAuth URL with youtube.upload scope
        scopes = [
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube.readonly"
        ]
        auth_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth?"
            f"response_type=code&"
            f"client_id={GOOGLE_CLIENT_ID}&"
            f"redirect_uri={YOUTUBE_REDIRECT_URI}&"
            f"state={state}&"
            f"scope={' '.join(scopes)}&"
            f"access_type=offline&"
            f"prompt=consent"
        )

        return {"auth_url": auth_url}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initiate YouTube OAuth: {str(e)}")


@router.get("/youtube/callback")
async def youtube_callback(code: str = Query(...), state: str = Query(None), error: str = Query(None)):
    """Handle YouTube/Google OAuth callback."""
    try:
        # Check for error from Google
        if error:
            logger.warning(f"YouTube OAuth error: {error}")
            return RedirectResponse(url=f"{FRONTEND_URL}/dashboard?status=youtube_error&error={error}")

        # Validate state
        if not state or state not in oauth_states:
            return RedirectResponse(url=f"{FRONTEND_URL}/dashboard?status=youtube_error&error=Invalid state")

        # Get user_id from state
        state_data = oauth_states.pop(state)
        user_id = state_data.get("user_id")

        if not user_id:
            return RedirectResponse(url=f"{FRONTEND_URL}/dashboard?status=youtube_error&error=User not authenticated")

        # Exchange code for access token
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": YOUTUBE_REDIRECT_URI,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET
        }

        token_response = requests.post(token_url, data=token_data)
        token_response.raise_for_status()
        tokens = token_response.json()

        # Get YouTube channel info to verify access
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        channel_response = requests.get(
            "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true",
            headers=headers
        )

        platform_user_id = None
        if channel_response.ok:
            channel_data = channel_response.json()
            if channel_data.get("items"):
                platform_user_id = channel_data["items"][0]["id"]
                logger.info(f"YouTube channel connected: {platform_user_id}")

        # Save tokens to database
        save_oauth_tokens(
            user_id=user_id,
            service="youtube",
            access_token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token"),
            platform_user_id=platform_user_id,
            expires_at=int(time.time()) + tokens.get("expires_in", 3600)
        )

        logger.info(f"Successfully saved YouTube tokens for user {user_id}")

        # Redirect back to frontend with success
        return RedirectResponse(url=f"{FRONTEND_URL}/dashboard?status=youtube_connected")

    except Exception as e:
        logger.error(f"YouTube OAuth error: {str(e)}", exc_info=True)
        error_msg = str(e)[:200]
        return RedirectResponse(url=f"{FRONTEND_URL}/dashboard?status=youtube_error&error={error_msg}")


@router.post("/youtube/disconnect")
async def youtube_disconnect(user_id: int = Depends(get_current_user_id)):
    """Disconnect YouTube account."""
    try:
        delete_oauth_tokens(user_id, "youtube")
        return {"success": True, "message": "YouTube disconnected"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===== STATUS ENDPOINT =====

@router.get("/status")
async def get_auth_status(user_id: int = Depends(get_current_user_id)):
    """Get authentication status for all services."""
    from database import get_connection_status
    return get_connection_status(user_id)
