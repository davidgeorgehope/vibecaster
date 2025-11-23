import os
import sys
import time
from typing import Optional, Dict, Any, Tuple
from google import genai
from google.genai import types
import tweepy
import requests
from PIL import Image
from io import BytesIO
import base64
from dotenv import load_dotenv
from database import get_campaign, get_oauth_tokens, update_last_run, get_recent_topics, save_post_history
from logger_config import agent_logger as logger

load_dotenv()

# Initialize Google GenAI client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Model configurations
LLM_MODEL = "gemini-3-pro-preview"  # Primary model
LLM_FALLBACK = "gemini-1.5-pro-002"  # Fallback model
IMAGE_MODEL = "gemini-3-pro-image-preview"


def analyze_user_prompt(user_prompt: str) -> Tuple[str, str]:
    """
    Analyze user prompt to generate refined persona and visual style.

    Returns:
        Tuple of (refined_persona, visual_style)
    """
    try:
        analysis_prompt = f"""
Analyze this social media automation request and generate:

1. A REFINED PERSONA - A detailed system instruction describing the voice, tone, and personality this account should embody
2. A VISUAL STYLE - Art direction for image generation that matches the persona

User Request: "{user_prompt}"

Respond in this exact JSON format:
{{
    "refined_persona": "Your detailed persona description here",
    "visual_style": "Your visual style description here"
}}
"""

        response = client.models.generate_content(
            model=LLM_MODEL,
            contents=analysis_prompt,
            config={
                "temperature": 0.7,
                "response_mime_type": "application/json"
            }
        )

        result = response.text
        import json
        data = json.loads(result)

        return data.get("refined_persona", ""), data.get("visual_style", "")

    except Exception as e:
        logger.error(f"Error analyzing prompt: {e}", exc_info=True)
        # Fallback to simple defaults
        return (
            f"A social media account that posts about: {user_prompt}",
            "Modern, clean, professional visual style"
        )


def search_trending_topics(user_prompt: str, refined_persona: str, recent_topics: list = None) -> Tuple[str, list]:
    """
    Use Gemini with Google Search grounding to find trending topics.

    Args:
        user_prompt: The user's campaign prompt
        refined_persona: The refined persona description
        recent_topics: List of specific topics covered in the last 2 weeks to avoid

    Returns:
        Tuple of (search_context, urls_list) where urls_list contains source URLs
    """
    try:
        # Build avoidance instruction if we have recent topics
        avoidance_text = ""
        if recent_topics:
            topics_str = "\n- ".join(recent_topics)
            avoidance_text = f"""

IMPORTANT: We've recently covered these specific topics, so explore DIFFERENT aspects or angles:
- {topics_str}

Look for new angles, different sub-topics, or emerging developments we haven't discussed yet.
"""

        search_prompt = f"""
Find the latest trending news, discussions, or technical developments related to: {user_prompt}

Focus on recent (last 24-48 hours) content that would be interesting to someone with this persona:
{refined_persona}{avoidance_text}

Provide a brief summary of the most interesting findings.
"""

        # Use Google Search grounding with Gemini 3
        response = client.models.generate_content(
            model=LLM_MODEL,
            contents=search_prompt,
            config={
                "temperature": 0.7,
                "tools": [
                    {"google_search": {}}
                ]
            }
        )

        # Extract URLs from grounding metadata
        urls = []
        if hasattr(response, 'candidates') and len(response.candidates) > 0:
            candidate = response.candidates[0]
            if hasattr(candidate, 'grounding_metadata'):
                metadata = candidate.grounding_metadata
                if hasattr(metadata, 'grounding_chunks') and metadata.grounding_chunks:
                    for chunk in metadata.grounding_chunks:
                        if hasattr(chunk, 'web') and hasattr(chunk.web, 'uri'):
                            urls.append(chunk.web.uri)
                    logger.info(f"Extracted {len(urls)} URLs from search results")

        return response.text, urls

    except Exception as e:
        logger.error(f"Error searching topics: {e}", exc_info=True)
        return f"General discussion about {user_prompt}", []


def generate_post_draft(search_context: str, refined_persona: str, user_prompt: str, source_url: Optional[str] = None, recent_topics: list = None) -> str:
    """
    Generate a social media post draft based on search context and persona.

    Args:
        search_context: Context from trending search results
        refined_persona: The persona description
        user_prompt: The user's campaign prompt
        source_url: Optional URL to include in the post
        recent_topics: List of specific topics covered in the last 2 weeks to avoid

    Returns:
        Post text (under 280 characters including URL)
    """
    try:
        # Account for URL in character count (Twitter counts URLs as ~23 chars)
        # Use 220 chars to be safe and leave room for the URL
        max_text_length = 220 if source_url else 280

        # Build avoidance instruction if we have recent topics
        avoidance_text = ""
        if recent_topics:
            topics_str = ", ".join(recent_topics[:5])  # Limit to first 5 for brevity
            avoidance_text = f"""
- Explore a FRESH angle - we recently covered: {topics_str}
"""

        draft_prompt = f"""
You are acting as this persona:
{refined_persona}

Based on this trending information:
{search_context}

Write a single social media post about {user_prompt}.

CRITICAL REQUIREMENTS:
- MAXIMUM {max_text_length} characters - this is STRICT, go shorter if needed
- Engaging and authentic to the persona
- Include relevant insights from the trending information
- Can include 1-2 relevant hashtags if appropriate
- Natural, conversational tone
- DO NOT include any URLs or links in your response
- Keep it concise and punchy{avoidance_text}

Write only the post text, nothing else.
"""

        response = client.models.generate_content(
            model=LLM_MODEL,
            contents=draft_prompt,
            config={
                "temperature": 0.8
            }
        )

        post_text = response.text.strip()

        # Append URL if provided
        if source_url:
            post_text = f"{post_text} {source_url}"
            logger.info(f"Added source URL to post (total length: {len(post_text)} chars)")

        return post_text

    except Exception as e:
        logger.error(f"Error generating draft: {e}", exc_info=True)
        fallback = "Excited to share thoughts on this topic! #ai #automation"
        if source_url:
            fallback = f"{fallback} {source_url}"
        return fallback


def critique_and_refine_post(draft: str, refined_persona: str) -> str:
    """
    Critique the post draft and refine it if needed.

    Returns:
        Final refined post
    """
    try:
        critique_prompt = f"""
Review this social media post draft:
"{draft}"

Persona: {refined_persona}

Critique it for:
1. Engagement potential
2. Authenticity to persona
3. Safety (no controversial/harmful content)
4. Length (must be under 280 chars)

If the post has issues, rewrite it. Otherwise, return it unchanged.
Return only the final post text, nothing else.
"""

        response = client.models.generate_content(
            model=LLM_MODEL,
            contents=critique_prompt,
            config={
                "temperature": 0.7
            }
        )

        return response.text.strip()

    except Exception as e:
        logger.error(f"Error critiquing post: {e}", exc_info=True)
        return draft


def extract_topics_from_post(post_text: str) -> list:
    """
    Extract specific, granular topics covered in the post.

    Returns:
        List of 3-5 specific topic strings (e.g., ["OpenTelemetry distributed tracing", "Kubernetes HPA configuration"])
    """
    try:
        extraction_prompt = f"""
Analyze this social media post and extract 3-5 SPECIFIC, GRANULAR topics or concepts it covers.

Post: "{post_text}"

Be SPECIFIC - not broad categories. Examples:
- Good: "OpenTelemetry distributed tracing", "Kubernetes horizontal pod autoscaling", "React useEffect cleanup functions"
- Bad: "OpenTelemetry", "Kubernetes", "React"

Respond in this exact JSON format:
{{
    "topics": ["specific topic 1", "specific topic 2", "specific topic 3"]
}}
"""

        response = client.models.generate_content(
            model=LLM_MODEL,
            contents=extraction_prompt,
            config={
                "temperature": 0.3,
                "response_mime_type": "application/json"
            }
        )

        import json
        result = json.loads(response.text)
        topics = result.get("topics", [])
        logger.info(f"Extracted {len(topics)} topics: {topics}")
        return topics

    except Exception as e:
        logger.error(f"Error extracting topics: {e}", exc_info=True)
        return []


def generate_image(post_text: str, visual_style: str) -> Optional[bytes]:
    """
    Generate an image using Imagen based on the post and visual style.

    Returns:
        Image bytes or None if generation fails
    """
    try:
        image_prompt = f"""
Create a visually appealing image for this social media post:
"{post_text}"

Art Style: {visual_style}

The image should be eye-catching, professional, and complement the post content.
"""

        response = client.models.generate_content(
            model=IMAGE_MODEL,
            contents=image_prompt,
            config=types.GenerateContentConfig(
                response_modalities=['IMAGE']
            )
        )

        # Debug logging
        logger.info(f"Image API response type: {type(response)}")
        logger.info(f"Has candidates: {hasattr(response, 'candidates')}")
        if hasattr(response, 'candidates'):
            logger.info(f"Number of candidates: {len(response.candidates)}")
            for i, candidate in enumerate(response.candidates):
                logger.info(f"Candidate {i} type: {type(candidate)}")
                if hasattr(candidate, 'content'):
                    logger.info(f"  Has content: True")
                    if hasattr(candidate.content, 'parts'):
                        logger.info(f"  Number of parts: {len(candidate.content.parts)}")
                        for j, part in enumerate(candidate.content.parts):
                            logger.info(f"    Part {j} type: {type(part)}")
                            logger.info(f"    Part {j} has as_image: {hasattr(part, 'as_image')}")
                            logger.info(f"    Part {j} has inline_data: {hasattr(part, 'inline_data')}")
                            logger.info(f"    Part {j} attributes: {dir(part)}")

        # Extract image from response candidates
        if hasattr(response, 'candidates'):
            for candidate in response.candidates:
                if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                    for part in candidate.content.parts:
                        # Try as_image method first
                        if hasattr(part, 'as_image'):
                            image = part.as_image()
                            if image:
                                img_byte_arr = BytesIO()
                                image.save(img_byte_arr, format='PNG')
                                logger.info(f"Image generated successfully via as_image() ({len(img_byte_arr.getvalue())} bytes)")
                                return img_byte_arr.getvalue()

                        # Try inline_data if available
                        if hasattr(part, 'inline_data') and part.inline_data:
                            logger.info(f"Found inline_data: {type(part.inline_data)}")
                            if hasattr(part.inline_data, 'data'):
                                logger.info(f"Image generated successfully via inline_data ({len(part.inline_data.data)} bytes)")
                                return part.inline_data.data
                            elif hasattr(part.inline_data, 'mime_type'):
                                logger.info(f"Inline data mime_type: {part.inline_data.mime_type}")

        logger.warning("No image found in response candidates")
        return None

    except Exception as e:
        logger.error(f"Error generating image: {e}", exc_info=True)
        return None


def post_to_twitter(user_id: int, post_text: str, image_bytes: Optional[bytes] = None) -> bool:
    """
    Post to Twitter/X with optional image using OAuth 1.0a.

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
            # Create API v1.1 client for media upload
            auth = tweepy.OAuth1UserHandler(
                consumer_key=consumer_key,
                consumer_secret=consumer_secret
            )
            auth.set_access_token(access_token, access_token_secret)
            api = tweepy.API(auth)

            # Upload media
            media = api.media_upload(filename="image.png", file=BytesIO(image_bytes))
            media_id = media.media_id

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


def post_to_linkedin(user_id: int, post_text: str, image_bytes: Optional[bytes] = None) -> bool:
    """
    Post to LinkedIn with optional image.

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
        user_response = requests.get(
            "https://api.linkedin.com/v2/userinfo",
            headers=headers
        )
        user_response.raise_for_status()
        person_id = user_response.json()["sub"]
        author_urn = f"urn:li:person:{person_id}"

        # Handle image upload if provided
        image_urn = None
        if image_bytes:
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

            image_urn = asset_id
            logger.info(f"Image uploaded to LinkedIn: {image_urn}")

        # Prepare post data
        if image_urn:
            post_data = {
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
            post_data = {
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

        # Create post
        response = requests.post(
            "https://api.linkedin.com/v2/ugcPosts",
            headers=headers,
            json=post_data
        )
        response.raise_for_status()

        logger.info(f"Posted to LinkedIn: {response.json()['id']}")
        return True

    except Exception as e:
        logger.error(f"Error posting to LinkedIn: {e}", exc_info=True)
        return False


def run_agent_cycle(user_id: int):
    """
    Main agent cycle that runs the complete workflow:
    1. Fetch campaign configuration
    2. Get recent topics to avoid repetition
    3. Search for trending topics
    4. Generate post draft
    5. Critique and refine
    6. Generate image
    7. Post to connected platforms
    8. Extract and save topics for future avoidance
    """
    try:
        logger.info("=" * 60)
        logger.info(f"Starting agent cycle for user {user_id} at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 60)

        # Get campaign configuration
        campaign = get_campaign(user_id)
        if not campaign or not campaign.get("user_prompt"):
            logger.warning(f"No campaign configured for user {user_id}. Skipping cycle.")
            return

        user_prompt = campaign["user_prompt"]
        refined_persona = campaign.get("refined_persona", "")
        visual_style = campaign.get("visual_style", "")

        logger.info(f"Campaign: {user_prompt}")
        logger.info(f"Persona: {refined_persona[:100]}...")

        # Get recent topics to avoid repetition
        recent_topics = get_recent_topics(user_id, days=14)
        if recent_topics:
            logger.info(f"Found {len(recent_topics)} recent topics to avoid")
            logger.info(f"Recent topics: {recent_topics[:3]}...")  # Show first 3

        # Step 1: Search for trending topics
        logger.info("[1/6] Searching for trending topics...")
        search_context, source_urls = search_trending_topics(user_prompt, refined_persona, recent_topics)
        logger.info(f"Found context: {search_context[:200]}...")

        # Select first URL if available
        source_url = source_urls[0] if source_urls else None
        if source_url:
            logger.info(f"Using source URL: {source_url[:80]}...")

        # Step 2: Generate draft
        logger.info("[2/6] Generating post draft...")
        draft = generate_post_draft(search_context, refined_persona, user_prompt, source_url, recent_topics)
        logger.info(f"Draft: {draft}")

        # Step 3: Critique and refine
        logger.info("[3/6] Critiquing and refining...")
        final_post = critique_and_refine_post(draft, refined_persona)
        logger.info(f"Final post: {final_post}")

        # Step 4: Generate image
        logger.info("[4/6] Generating image...")
        image_bytes = generate_image(final_post, visual_style)
        if image_bytes:
            logger.info(f"Image generated ({len(image_bytes)} bytes)")
        else:
            logger.warning("No image generated - skipping post")
            logger.info("=" * 60)
            return

        # Step 5: Post to platforms
        logger.info("[5/6] Posting to platforms...")
        twitter_success = post_to_twitter(user_id, final_post, image_bytes)
        linkedin_success = post_to_linkedin(user_id, final_post, image_bytes)

        # Step 6: Extract topics and save post history
        logger.info("[6/6] Extracting topics and saving history...")
        extracted_topics = extract_topics_from_post(final_post)

        # Track which platforms were posted to
        posted_platforms = []
        if twitter_success:
            posted_platforms.append("twitter")
        if linkedin_success:
            posted_platforms.append("linkedin")

        # Save to history if posted to any platform
        if posted_platforms:
            save_post_history(user_id, final_post, extracted_topics, posted_platforms)
            logger.info(f"Saved to history with {len(extracted_topics)} topics")

        # Update last run timestamp
        update_last_run(user_id, int(time.time()))

        logger.info("Results:")
        logger.info(f"  Twitter: {'✓' if twitter_success else '✗'}")
        logger.info(f"  LinkedIn: {'✓' if linkedin_success else '✗'}")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Error in agent cycle for user {user_id}: {e}", exc_info=True)
