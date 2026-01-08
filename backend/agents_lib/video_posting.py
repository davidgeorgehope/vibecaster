"""Video posting functions for Twitter/X, LinkedIn, and YouTube."""
import os
import time
import json
import tempfile
from typing import Optional, Tuple
from io import BytesIO
import tweepy
import requests

from database import get_oauth_tokens
from logger_config import agent_logger as logger


# ===== TWITTER/X VIDEO UPLOAD =====

def upload_video_to_twitter(
    user_id: int,
    video_bytes: bytes,
    post_text: str,
    mime_type: str = "video/mp4"
) -> Tuple[bool, Optional[str]]:
    """
    Upload video to Twitter/X using chunked media upload.

    Twitter limits: 140 seconds, 512MB max, MP4 format.

    Args:
        user_id: User ID for OAuth tokens
        video_bytes: Video file bytes
        post_text: Tweet text
        mime_type: Video MIME type (default: video/mp4)

    Returns:
        Tuple of (success, error_message or tweet_id)
    """
    try:
        tokens = get_oauth_tokens(user_id, "twitter")
        if not tokens:
            return False, "Twitter not connected"

        consumer_key = os.getenv("X_API_KEY")
        consumer_secret = os.getenv("X_API_SECRET")
        access_token = tokens["access_token"]
        access_token_secret = tokens["refresh_token"]

        # Set up OAuth for v1.1 API
        auth = tweepy.OAuth1UserHandler(
            consumer_key=consumer_key,
            consumer_secret=consumer_secret
        )
        auth.set_access_token(access_token, access_token_secret)
        api = tweepy.API(auth)

        # Write video to temp file for chunked upload
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(video_bytes)
            temp_path = f.name

        try:
            # Chunked upload for video
            media = api.chunked_upload(
                filename=temp_path,
                media_category="tweet_video",
                wait_for_async_finalize=True
            )
            media_id = media.media_id
        finally:
            os.unlink(temp_path)

        # Create tweet with video
        client = tweepy.Client(
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            access_token=access_token,
            access_token_secret=access_token_secret
        )

        response = client.create_tweet(text=post_text, media_ids=[media_id])
        tweet_id = response.data['id']

        logger.info(f"Posted video to Twitter: {tweet_id}")
        return True, str(tweet_id)

    except Exception as e:
        logger.error(f"Error posting video to Twitter: {e}", exc_info=True)
        return False, str(e)


# ===== LINKEDIN VIDEO UPLOAD =====

def upload_video_to_linkedin(
    user_id: int,
    video_bytes: bytes,
    post_text: str,
    mime_type: str = "video/mp4"
) -> Tuple[bool, Optional[str]]:
    """
    Upload video to LinkedIn using the Video API.

    LinkedIn limits: 10 minutes, 5GB max, MP4/MOV format.

    Args:
        user_id: User ID for OAuth tokens
        video_bytes: Video file bytes
        post_text: Post text
        mime_type: Video MIME type

    Returns:
        Tuple of (success, error_message or post_id)
    """
    try:
        tokens = get_oauth_tokens(user_id, "linkedin")
        if not tokens:
            return False, "LinkedIn not connected"

        headers = {
            "Authorization": f"Bearer {tokens['access_token']}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0"
        }

        # Get author URN
        user_response = requests.get(
            "https://api.linkedin.com/v2/userinfo",
            headers=headers
        )
        user_response.raise_for_status()
        person_id = user_response.json()["sub"]
        author_urn = f"urn:li:person:{person_id}"

        # Step 1: Initialize video upload
        file_size = len(video_bytes)
        init_request = {
            "initializeUploadRequest": {
                "owner": author_urn,
                "fileSizeBytes": file_size,
                "uploadCaptions": False,
                "uploadThumbnail": False
            }
        }

        init_response = requests.post(
            "https://api.linkedin.com/rest/videos?action=initializeUpload",
            headers={
                "Authorization": f"Bearer {tokens['access_token']}",
                "Content-Type": "application/json",
                "LinkedIn-Version": "202511",
                "X-Restli-Protocol-Version": "2.0.0"
            },
            json=init_request
        )
        init_response.raise_for_status()
        init_data = init_response.json()

        video_urn = init_data["value"]["video"]
        upload_instructions = init_data["value"]["uploadInstructions"]

        # Step 2: Upload video chunks
        for instruction in upload_instructions:
            upload_url = instruction["uploadUrl"]
            first_byte = instruction["firstByte"]
            last_byte = instruction["lastByte"]

            chunk = video_bytes[first_byte:last_byte + 1]

            upload_response = requests.put(
                upload_url,
                headers={
                    "Authorization": f"Bearer {tokens['access_token']}",
                    "Content-Type": "application/octet-stream"
                },
                data=chunk
            )
            upload_response.raise_for_status()

        # Step 3: Finalize upload
        finalize_request = {
            "finalizeUploadRequest": {
                "video": video_urn,
                "uploadToken": "",
                "uploadedPartIds": []
            }
        }

        finalize_response = requests.post(
            "https://api.linkedin.com/rest/videos?action=finalizeUpload",
            headers={
                "Authorization": f"Bearer {tokens['access_token']}",
                "Content-Type": "application/json",
                "LinkedIn-Version": "202511",
                "X-Restli-Protocol-Version": "2.0.0"
            },
            json=finalize_request
        )
        finalize_response.raise_for_status()

        # Step 4: Wait for video processing (poll status)
        max_attempts = 60
        for attempt in range(max_attempts):
            status_response = requests.get(
                f"https://api.linkedin.com/rest/videos/{video_urn.split(':')[-1]}",
                headers={
                    "Authorization": f"Bearer {tokens['access_token']}",
                    "LinkedIn-Version": "202511",
                    "X-Restli-Protocol-Version": "2.0.0"
                }
            )

            if status_response.ok:
                status_data = status_response.json()
                if status_data.get("status") == "AVAILABLE":
                    break
                elif status_data.get("status") in ["FAILED", "CANCELLED"]:
                    return False, f"Video processing failed: {status_data.get('status')}"

            time.sleep(5)
        else:
            return False, "Video processing timed out"

        # Step 5: Create post with video
        post_data = {
            "author": author_urn,
            "commentary": post_text,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": []
            },
            "content": {
                "media": {
                    "title": "Video",
                    "id": video_urn
                }
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False
        }

        post_response = requests.post(
            "https://api.linkedin.com/rest/posts",
            headers={
                "Authorization": f"Bearer {tokens['access_token']}",
                "Content-Type": "application/json",
                "LinkedIn-Version": "202511",
                "X-Restli-Protocol-Version": "2.0.0"
            },
            json=post_data
        )
        post_response.raise_for_status()

        post_id = post_response.headers.get("x-restli-id", "unknown")
        logger.info(f"Posted video to LinkedIn: {post_id}")
        return True, post_id

    except Exception as e:
        logger.error(f"Error posting video to LinkedIn: {e}", exc_info=True)
        return False, str(e)


# ===== YOUTUBE VIDEO UPLOAD =====

def refresh_youtube_token(user_id: int) -> Optional[str]:
    """Refresh YouTube access token if expired."""
    from database import save_oauth_tokens

    tokens = get_oauth_tokens(user_id, "youtube")
    if not tokens:
        return None

    # Check if token is expired (with 5 min buffer)
    if tokens.get("expires_at", 0) > time.time() + 300:
        return tokens["access_token"]

    # Token expired, refresh it
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        logger.warning("No refresh token for YouTube")
        return None

    try:
        response = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                "client_secret": os.getenv("GOOGLE_CLIENT_SECRET")
            }
        )
        response.raise_for_status()
        new_tokens = response.json()

        # Save new access token
        save_oauth_tokens(
            user_id=user_id,
            service="youtube",
            access_token=new_tokens["access_token"],
            refresh_token=refresh_token,  # Keep existing refresh token
            platform_user_id=tokens.get("platform_user_id"),
            expires_at=int(time.time()) + new_tokens.get("expires_in", 3600)
        )

        return new_tokens["access_token"]

    except Exception as e:
        logger.error(f"Failed to refresh YouTube token: {e}")
        return None


def upload_video_to_youtube(
    user_id: int,
    video_bytes: bytes,
    title: str,
    description: str,
    privacy_status: str = "public",
    category_id: str = "22",  # People & Blogs
    tags: Optional[list] = None
) -> Tuple[bool, Optional[str]]:
    """
    Upload video to YouTube using the YouTube Data API v3.

    Args:
        user_id: User ID for OAuth tokens
        video_bytes: Video file bytes
        title: Video title (max 100 chars)
        description: Video description
        privacy_status: public, private, or unlisted
        category_id: YouTube category ID
        tags: Optional list of tags

    Returns:
        Tuple of (success, error_message or video_id)
    """
    try:
        access_token = refresh_youtube_token(user_id)
        if not access_token:
            return False, "YouTube not connected or token refresh failed"

        # Truncate title to 100 chars
        title = title[:100]

        # Step 1: Initialize resumable upload
        metadata = {
            "snippet": {
                "title": title,
                "description": description,
                "categoryId": category_id
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False
            }
        }

        if tags:
            metadata["snippet"]["tags"] = tags[:500]  # Max 500 tags

        init_response = requests.post(
            "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": "video/mp4",
                "X-Upload-Content-Length": str(len(video_bytes))
            },
            json=metadata
        )
        init_response.raise_for_status()

        upload_url = init_response.headers.get("Location")
        if not upload_url:
            return False, "Failed to get upload URL from YouTube"

        # Step 2: Upload video in chunks (5MB each for reliability)
        chunk_size = 5 * 1024 * 1024  # 5MB
        total_size = len(video_bytes)
        uploaded = 0

        while uploaded < total_size:
            chunk_end = min(uploaded + chunk_size, total_size)
            chunk = video_bytes[uploaded:chunk_end]

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "video/mp4",
                "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {uploaded}-{chunk_end - 1}/{total_size}"
            }

            upload_response = requests.put(upload_url, headers=headers, data=chunk)

            if upload_response.status_code == 200:
                # Upload complete
                result = upload_response.json()
                video_id = result.get("id")
                logger.info(f"Uploaded video to YouTube: {video_id}")
                return True, video_id
            elif upload_response.status_code == 308:
                # Resume incomplete, continue uploading
                range_header = upload_response.headers.get("Range", "")
                if range_header:
                    uploaded = int(range_header.split("-")[1]) + 1
                else:
                    uploaded = chunk_end
            else:
                return False, f"Upload failed: {upload_response.status_code} - {upload_response.text}"

        return False, "Upload completed but no video ID returned"

    except Exception as e:
        logger.error(f"Error uploading video to YouTube: {e}", exc_info=True)
        return False, str(e)


def post_video_to_platforms(
    user_id: int,
    video_bytes: bytes,
    x_post: Optional[str] = None,
    linkedin_post: Optional[str] = None,
    youtube_title: Optional[str] = None,
    youtube_description: Optional[str] = None,
    platforms: list = None
) -> dict:
    """
    Post video to multiple platforms.

    Args:
        user_id: User ID
        video_bytes: Video file bytes
        x_post: Text for X/Twitter post
        linkedin_post: Text for LinkedIn post
        youtube_title: Title for YouTube video
        youtube_description: Description for YouTube video
        platforms: List of platforms to post to ['twitter', 'linkedin', 'youtube']

    Returns:
        Dict with results for each platform
    """
    if platforms is None:
        platforms = []

    results = {
        "posted": [],
        "errors": {}
    }

    if "twitter" in platforms and x_post:
        success, result = upload_video_to_twitter(user_id, video_bytes, x_post)
        if success:
            results["posted"].append("twitter")
        else:
            results["errors"]["twitter"] = result

    if "linkedin" in platforms and linkedin_post:
        success, result = upload_video_to_linkedin(user_id, video_bytes, linkedin_post)
        if success:
            results["posted"].append("linkedin")
        else:
            results["errors"]["linkedin"] = result

    if "youtube" in platforms and youtube_title:
        success, result = upload_video_to_youtube(
            user_id,
            video_bytes,
            youtube_title,
            youtube_description or ""
        )
        if success:
            results["posted"].append("youtube")
        else:
            results["errors"]["youtube"] = result

    return results
