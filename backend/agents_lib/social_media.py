"""Social media posting functions for Twitter/X and LinkedIn."""
import os
from typing import Optional
from io import BytesIO
import tweepy
import requests

from database import get_oauth_tokens
from logger_config import agent_logger as logger


def post_to_twitter(user_id: int, post_text: str, image_bytes: Optional[bytes] = None) -> bool:
    """
    Post to Twitter/X with optional image using OAuth 1.0a.

    Args:
        user_id: The user's ID in the database
        post_text: The text content of the tweet
        image_bytes: Optional image bytes to attach

    Returns:
        True if successful, False otherwise
    """
    try:
        tokens = get_oauth_tokens(user_id, "twitter")
        if not tokens:
            logger.warning(f"No Twitter tokens found for user {user_id}")
            return False

        # Get OAuth 1.0a credentials
        access_token = tokens["access_token"]
        access_token_secret = tokens["refresh_token"]  # Stored in refresh_token field
        consumer_key = os.getenv("X_API_KEY")
        consumer_secret = os.getenv("X_API_SECRET")

        # Create Twitter client with OAuth 1.0a
        client = tweepy.Client(
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            access_token=access_token,
            access_token_secret=access_token_secret
        )

        # If image is provided, upload media using v1.1 API
        media_id = None
        if image_bytes:
            media_id = _upload_twitter_media(
                image_bytes,
                consumer_key,
                consumer_secret,
                access_token,
                access_token_secret
            )

        # Create tweet
        if media_id:
            response = client.create_tweet(text=post_text, media_ids=[media_id])
        else:
            response = client.create_tweet(text=post_text)

        logger.info(f"Posted to Twitter: {response.data['id']}")
        return True

    except Exception as e:
        logger.error(f"Error posting to Twitter: {e}", exc_info=True)
        return False


def _upload_twitter_media(
    image_bytes: bytes,
    consumer_key: str,
    consumer_secret: str,
    access_token: str,
    access_token_secret: str
) -> Optional[int]:
    """
    Upload media to Twitter using v1.1 API.

    Args:
        image_bytes: The image bytes to upload
        consumer_key: Twitter API consumer key
        consumer_secret: Twitter API consumer secret
        access_token: User's access token
        access_token_secret: User's access token secret

    Returns:
        Media ID if successful, None otherwise
    """
    try:
        auth = tweepy.OAuth1UserHandler(
            consumer_key=consumer_key,
            consumer_secret=consumer_secret
        )
        auth.set_access_token(access_token, access_token_secret)
        api = tweepy.API(auth)

        media = api.media_upload(filename="image.png", file=BytesIO(image_bytes))
        return media.media_id
    except Exception as e:
        logger.error(f"Error uploading media to Twitter: {e}")
        return None


def post_to_linkedin(user_id: int, post_text: str, image_bytes: Optional[bytes] = None) -> bool:
    """
    Post to LinkedIn with optional image.

    Args:
        user_id: The user's ID in the database
        post_text: The text content of the post
        image_bytes: Optional image bytes to attach

    Returns:
        True if successful, False otherwise
    """
    try:
        tokens = get_oauth_tokens(user_id, "linkedin")
        if not tokens:
            logger.warning(f"No LinkedIn tokens found for user {user_id}")
            return False

        headers = {
            "Authorization": f"Bearer {tokens['access_token']}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0"
        }

        # Get user URN
        author_urn = _get_linkedin_author_urn(headers)
        if not author_urn:
            return False

        # Handle image upload if provided
        image_urn = None
        if image_bytes:
            image_urn = _upload_linkedin_image(image_bytes, author_urn, headers, tokens)

        # Prepare and create post
        post_data = _build_linkedin_post_data(author_urn, post_text, image_urn)

        logger.info(f"Creating LinkedIn post with text length: {len(post_text)}")
        logger.info(f"LinkedIn post text preview: {post_text[:200]}...")

        response = requests.post(
            "https://api.linkedin.com/v2/ugcPosts",
            headers=headers,
            json=post_data
        )

        if not response.ok:
            logger.error(f"LinkedIn API error response: {response.status_code}")
            logger.error(f"Response body: {response.text}")
            logger.error(f"Post data sent: {post_data}")

        response.raise_for_status()

        logger.info(f"Posted to LinkedIn: {response.json()['id']}")
        return True

    except Exception as e:
        logger.error(f"Error posting to LinkedIn: {e}", exc_info=True)
        return False


def _get_linkedin_author_urn(headers: dict) -> Optional[str]:
    """
    Get the LinkedIn author URN for the authenticated user.

    Args:
        headers: Request headers with authorization

    Returns:
        Author URN string or None if failed
    """
    try:
        user_response = requests.get(
            "https://api.linkedin.com/v2/userinfo",
            headers=headers
        )
        user_response.raise_for_status()
        person_id = user_response.json()["sub"]
        return f"urn:li:person:{person_id}"
    except Exception as e:
        logger.error(f"Error getting LinkedIn author URN: {e}")
        return None


def _upload_linkedin_image(
    image_bytes: bytes,
    author_urn: str,
    headers: dict,
    tokens: dict
) -> Optional[str]:
    """
    Upload an image to LinkedIn.

    Args:
        image_bytes: The image bytes to upload
        author_urn: The author's LinkedIn URN
        headers: Request headers
        tokens: OAuth tokens

    Returns:
        Image URN if successful, None otherwise
    """
    try:
        logger.info("Uploading image to LinkedIn...")

        # Step 1: Register upload
        register_upload_request = {
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "owner": author_urn,
                "serviceRelationships": [
                    {
                        "relationshipType": "OWNER",
                        "identifier": "urn:li:userGeneratedContent"
                    }
                ]
            }
        }

        register_response = requests.post(
            "https://api.linkedin.com/v2/assets?action=registerUpload",
            headers=headers,
            json=register_upload_request
        )
        register_response.raise_for_status()
        register_data = register_response.json()

        upload_url = register_data["value"]["uploadMechanism"]["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]["uploadUrl"]
        asset_id = register_data["value"]["asset"]

        # Step 2: Upload the image binary
        upload_headers = {
            "Authorization": f"Bearer {tokens['access_token']}"
        }
        upload_response = requests.put(
            upload_url,
            headers=upload_headers,
            data=image_bytes
        )
        upload_response.raise_for_status()

        logger.info(f"Image uploaded to LinkedIn: {asset_id}")
        return asset_id

    except Exception as e:
        logger.error(f"Error uploading image to LinkedIn: {e}")
        return None


def _build_linkedin_post_data(author_urn: str, post_text: str, image_urn: Optional[str] = None) -> dict:
    """
    Build the LinkedIn post data structure.

    Args:
        author_urn: The author's LinkedIn URN
        post_text: The text content
        image_urn: Optional image URN

    Returns:
        Post data dictionary for LinkedIn API
    """
    if image_urn:
        return {
            "author": author_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {
                        "text": post_text
                    },
                    "shareMediaCategory": "IMAGE",
                    "media": [
                        {
                            "status": "READY",
                            "media": image_urn
                        }
                    ]
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            }
        }
    else:
        return {
            "author": author_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {
                        "text": post_text
                    },
                    "shareMediaCategory": "NONE"
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            }
        }
