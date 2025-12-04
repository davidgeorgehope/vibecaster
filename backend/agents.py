import os
import sys
import time
import re
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


def strip_markdown_formatting(text: str) -> str:
    """
    Remove common markdown formatting that LinkedIn doesn't support.
    LinkedIn only supports plain text, so we strip **bold**, __italic__, etc.
    """
    # Remove bold: **text** or __text__
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)

    # Remove italic: *text* or _text_ (but be careful with underscores in URLs)
    text = re.sub(r'(?<!\w)\*(.+?)\*(?!\w)', r'\1', text)
    text = re.sub(r'(?<!\w)_(.+?)_(?!\w)', r'\1', text)

    # Remove strikethrough: ~~text~~
    text = re.sub(r'~~(.+?)~~', r'\1', text)

    # Remove code formatting: `text`
    text = re.sub(r'`(.+?)`', r'\1', text)

    return text


def resolve_redirect_url(url: str) -> str:
    """
    Follow redirects to get the actual destination URL.
    This handles Vertex AI Search grounding API redirect URLs and other redirects.

    Args:
        url: The URL to resolve (may be a redirect)

    Returns:
        The final destination URL after following all redirects
    """
    try:
        response = requests.head(url, allow_redirects=True, timeout=10)
        final_url = response.url
        logger.info(f"Resolved redirect: {url[:60]}... -> {final_url}")
        return final_url
    except Exception as e:
        logger.warning(f"Could not resolve redirect for {url[:60]}...: {e}")
        return url  # Return original URL if resolution fails


def analyze_user_prompt(user_prompt: str) -> Tuple[str, str, bool]:
    """
    Analyze user prompt to generate refined persona and visual style.
    CRITICAL: Preserves the user's exact creative vision and specific requirements.

    Returns:
        Tuple of (refined_persona, visual_style, include_links)
    """
    try:
        analysis_prompt = f"""
Analyze this social media automation request and generate:

1. A REFINED PERSONA - A detailed system instruction that STRICTLY PRESERVES the user's exact creative vision, voice, tone, and specific requirements
2. A VISUAL STYLE - Art direction that EXACTLY follows the user's specified visual requirements
3. INCLUDE_LINKS - Detect if the user wants source links/URLs included in posts

CRITICAL: If the user specifies a particular creative concept (e.g., "anime girl teaching", "stick figures explaining", "meme format"), you MUST preserve that exact concept in both outputs. DO NOT generalize or dilute their vision.

For include_links, look for phrases like:
- "include links", "add links", "with links", "share links"
- "include sources", "add sources", "with sources", "cite sources"
- "include URL", "add URL", "with URL"
- "link to article", "link to source"

If NO mention of links/sources/URLs is found, set include_links to false.

User Request: "{user_prompt}"

Respond in this exact JSON format:
{{
    "refined_persona": "Your detailed persona description that preserves ALL user requirements",
    "visual_style": "Your visual style description that EXACTLY matches user specifications",
    "include_links": true or false
}}
"""

        response = client.models.generate_content(
            model=LLM_MODEL,
            contents=analysis_prompt,
            config=types.GenerateContentConfig(
                temperature=0.5,  # Lower temp to stay faithful to user input
                response_mime_type="application/json",
                thinking_config=types.ThinkingConfig(
                    thinking_level="HIGH"
                )
            )
        )

        result = response.text
        import json
        data = json.loads(result)

        return data.get("refined_persona", ""), data.get("visual_style", ""), data.get("include_links", False)

    except Exception as e:
        logger.error(f"Error analyzing prompt: {e}", exc_info=True)
        # Fallback: preserve user's original prompt exactly and default to not including links
        return (
            f"IMPORTANT: Follow this exact creative direction: {user_prompt}",
            f"Visual style as specified: {user_prompt}",
            False
        )


def search_trending_topics(user_prompt: str, refined_persona: str, recent_topics: list = None) -> Tuple[str, list]:
    """
    Search for relevant content that fits the user's creative vision.
    CRITICAL: Finds content that can be presented in the user's specified format,
    not just "trending news".

    Args:
        user_prompt: The user's campaign prompt with creative direction
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
CRITICAL CONTEXT: The user has a specific creative format/vision described here: {user_prompt}

Your task is to find content, concepts, or technical information that can be PRESENTED in this creative format.

For example:
- If they want "anime girl teaching OTEL tutorials", find interesting OTEL concepts/features to teach
- If they want "memes about kubernetes", find kubernetes pain points or funny scenarios
- If they want "explained with diagrams", find architecture/technical concepts worth diagramming

Search for:
1. Recent technical developments, concepts, or discussions (last 48 hours preferred, but up to 1 week if needed)
2. Content that FITS the user's creative presentation format
3. Topics that would be interesting to explain/present in the user's style

Persona for context: {refined_persona}{avoidance_text}

Provide:
1. A summary of interesting content found that fits the creative format
2. Key concepts, features, or topics that would work well in this format
3. Source URLs for credibility
"""

        # Use Google Search grounding with Gemini 3
        response = client.models.generate_content(
            model=LLM_MODEL,
            contents=search_prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,
                tools=[types.Tool(google_search=types.GoogleSearch())],
                thinking_config=types.ThinkingConfig(
                    thinking_level="HIGH"
                )
            )
        )

        # Extract URLs from grounding metadata and resolve redirects
        urls = []
        if hasattr(response, 'candidates') and len(response.candidates) > 0:
            candidate = response.candidates[0]
            if hasattr(candidate, 'grounding_metadata'):
                metadata = candidate.grounding_metadata
                if hasattr(metadata, 'grounding_chunks') and metadata.grounding_chunks:
                    for chunk in metadata.grounding_chunks:
                        if hasattr(chunk, 'web') and hasattr(chunk.web, 'uri'):
                            redirect_url = chunk.web.uri
                            # Resolve redirect to get actual URL
                            actual_url = resolve_redirect_url(redirect_url)
                            urls.append(actual_url)
                    logger.info(f"Extracted and resolved {len(urls)} URLs from search results")

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
            config=types.GenerateContentConfig(
                temperature=0.8,
                thinking_config=types.ThinkingConfig(
                    thinking_level="HIGH"
                )
            )
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
            config=types.GenerateContentConfig(
                temperature=0.7,
                thinking_config=types.ThinkingConfig(
                    thinking_level="HIGH"
                )
            )
        )

        return response.text.strip()

    except Exception as e:
        logger.error(f"Error critiquing post: {e}", exc_info=True)
        return draft


def validate_content_matches_vision(post_text: str, user_prompt: str, refined_persona: str) -> Tuple[bool, str]:
    """
    Validate that generated social media post text is appropriate.
    IMPORTANT: user_prompt describes the IMAGE format, not the post text format.

    Returns:
        Tuple of (is_valid, feedback) where feedback explains any issues
    """
    try:
        validation_prompt = f"""
You are a quality control agent validating SOCIAL MEDIA POST TEXT.

CRITICAL CONTEXT:
- User's Creative Vision: {user_prompt}
  This describes the IMAGE/VISUAL FORMAT that will accompany the post, NOT what the post text should look like.
- Persona: {refined_persona}
- Generated Post Text: "{post_text}"

Your task: Validate if this is GOOD SOCIAL MEDIA POST TEXT (not an image description).

CHECK FOR THESE ISSUES (mark as invalid if found):
1. Is it an image generation prompt? (e.g., "Anime sketch of...", "Drawing showing...", "Diagram with...")
2. Is it describing what's in the image instead of discussing the topic?
3. Is it boring/generic? (e.g., "Check out this post about...")

GOOD INDICATORS (mark as valid if present):
1. It's a normal social media post ABOUT a technical topic
2. It matches the persona's voice/tone
3. It's engaging and would work on social media
4. It can reference the visual format briefly, but focuses on the TOPIC

Respond in this exact JSON format:
{{
    "is_valid": true/false,
    "feedback": "Brief explanation"
}}
"""

        response = client.models.generate_content(
            model=LLM_MODEL,
            contents=validation_prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                response_mime_type="application/json",
                thinking_config=types.ThinkingConfig(
                    thinking_level="HIGH"
                )
            )
        )

        import json
        result = json.loads(response.text)
        is_valid = result.get("is_valid", False)
        feedback = result.get("feedback", "No feedback provided")

        if is_valid:
            logger.debug(f"Content validation PASS: {feedback}")
        else:
            logger.warning(f"Content validation FAIL: {feedback}")

        return is_valid, feedback

    except Exception as e:
        logger.error(f"Error validating content: {e}", exc_info=True)
        return True, "Validation skipped due to error"


def extract_topics_from_post(post_text: str, user_prompt: str = "") -> list:
    """
    Extract specific, granular topics covered in the post.
    Topics are extracted in the context of the user's creative vision to maintain thematic consistency.

    Returns:
        List of 3-5 specific topic strings (e.g., ["OpenTelemetry distributed tracing", "Kubernetes HPA configuration"])
    """
    try:
        context_text = f"\n\nUser's Creative Vision: {user_prompt}" if user_prompt else ""

        extraction_prompt = f"""
Analyze this social media post and extract 3-5 SPECIFIC, GRANULAR topics or concepts it covers.

Post: "{post_text}"{context_text}

Be SPECIFIC - not broad categories. Examples:
- Good: "OpenTelemetry distributed tracing", "Kubernetes horizontal pod autoscaling", "React useEffect cleanup functions"
- Bad: "OpenTelemetry", "Kubernetes", "React"

Extract topics that are:
1. Specific technical concepts, features, or implementations mentioned
2. Consistent with the user's creative vision/format (don't extract the format itself, extract the technical content)
3. Granular enough to avoid repetition in future posts

Respond in this exact JSON format:
{{
    "topics": ["specific topic 1", "specific topic 2", "specific topic 3"]
}}
"""

        response = client.models.generate_content(
            model=LLM_MODEL,
            contents=extraction_prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                response_mime_type="application/json",
                thinking_config=types.ThinkingConfig(
                    thinking_level="HIGH"
                )
            )
        )

        import json
        result = json.loads(response.text)
        topics = result.get("topics", [])
        logger.info(f"Extracted {len(topics)} topics: {topics}")
        return topics

    except Exception as e:
        logger.error(f"Error extracting topics: {e}", exc_info=True)
        return []


def refine_image_prompt(post_text: str, visual_style: str, user_prompt: str, search_context: str = "") -> str:
    """
    STEP 1 (The Brain): Use the text reasoning model to deeply think about
    the best way to visualize the content and generate a refined, detailed prompt.

    This enables "thinking" before image generation since the image model
    doesn't support thinking_config.

    Args:
        post_text: The generated social media post content
        visual_style: The extracted visual style specification
        user_prompt: The original user prompt - provides crucial context about intent and purpose
        search_context: The detailed topic/content from search - provides specific technical details to visualize

    Returns:
        A refined, detailed image generation prompt
    """
    try:
        # Build search context section if available
        search_context_section = ""
        if search_context:
            search_context_section = f"""
TOPIC DETAILS (use this to understand WHAT specific concept/feature to visualize):
{search_context[:1500]}

"""

        refining_prompt = f"""
You are an expert art director specializing in social media visuals.

ORIGINAL USER INTENT (important context for understanding the purpose): {user_prompt}

VISUAL STYLE SPECIFICATION (MUST FOLLOW EXACTLY): {visual_style}
{search_context_section}
SOCIAL MEDIA POST CONTENT: "{post_text}"

Your task:
1. Think deeply about the best way to visualize this post while STRICTLY adhering to the visual style specification
2. Consider the ORIGINAL USER INTENT - this tells you the PURPOSE of the content (e.g., educational, promotional, entertainment)
3. Use the TOPIC DETAILS to understand the specific technical concept being discussed - the image should clearly relate to THIS topic
4. Consider lighting, composition, color palette, mood, and focal points
5. If the style specifies specific elements (e.g., "anime girl", "simple drawn style", "kawaii aesthetic"), these are NON-NEGOTIABLE
6. Plan how to make the image eye-catching and shareable on social media
7. Consider aspect ratio (1:1 works well for most social platforms)

OUTPUT: Write ONLY the final, detailed prompt for the image generator.
- Be specific about visual elements, positioning, colors, and mood
- Include technical art direction (lighting, perspective, style)
- Make sure the image clearly relates to the specific topic from TOPIC DETAILS
- Keep the prompt focused and actionable for image generation
- DO NOT include any explanations or meta-commentary, just the prompt itself
"""

        logger.info("🧠 Thinking about image composition...")

        response = client.models.generate_content(
            model=LLM_MODEL,  # Use text/reasoning model with thinking
            contents=refining_prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,
                thinking_config=types.ThinkingConfig(
                    thinking_level="HIGH"
                )
            )
        )

        refined_prompt = response.text.strip()
        logger.info(f"📝 Refined image prompt: {refined_prompt[:200]}...")

        return refined_prompt

    except Exception as e:
        logger.error(f"Error refining image prompt: {e}", exc_info=True)
        # Fallback to basic prompt if reasoning fails
        return f"Create an image in this style: {visual_style}. Content: {post_text}"


def generate_image(post_text: str, visual_style: str, user_prompt: str, search_context: str = "") -> Optional[bytes]:
    """
    Generate an image using a two-step "Think then Draw" workflow:

    STEP 1 (Brain/Reasoning): Uses LLM_MODEL with thinking to analyze the request
    and generate a highly detailed, refined image prompt.

    STEP 2 (Artist/Generation): Uses IMAGE_MODEL to execute the refined prompt.
    Note: IMAGE_MODEL does NOT support thinking_config.

    Args:
        post_text: The generated social media post content
        visual_style: The extracted visual style specification
        user_prompt: The original user prompt - provides crucial context about intent and purpose
        search_context: The detailed topic/content from search - provides specific technical details to visualize

    Returns:
        Image bytes or None if generation fails
    """
    try:
        # STEP 1: The Brain (Reasoning Phase)
        # Use text model with thinking to create a refined, detailed prompt
        refined_prompt = refine_image_prompt(post_text, visual_style, user_prompt, search_context)

        # STEP 2: The Artist (Generation Phase)
        # Pass the refined prompt to the image model WITHOUT thinking_config
        logger.info("🎨 Generating image with refined prompt...")

        response = client.models.generate_content(
            model=IMAGE_MODEL,  # Image model - NO thinking_config support
            contents=refined_prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"]
                # CRITICAL: Do NOT pass thinking_config here - image model doesn't support it
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
                        # Try inline_data first (raw bytes - most reliable)
                        if hasattr(part, 'inline_data') and part.inline_data:
                            logger.info(f"Found inline_data: {type(part.inline_data)}")
                            if hasattr(part.inline_data, 'data') and part.inline_data.data:
                                logger.info(f"Image generated successfully via inline_data ({len(part.inline_data.data)} bytes)")
                                return part.inline_data.data

                        # Try as_image method as fallback
                        if hasattr(part, 'as_image'):
                            try:
                                image = part.as_image()
                                if image:
                                    img_byte_arr = BytesIO()
                                    # Check if it's a PIL Image with save method that takes format
                                    if hasattr(image, 'save'):
                                        image.save(img_byte_arr, format='PNG')
                                        logger.info(f"Image generated successfully via as_image() ({len(img_byte_arr.getvalue())} bytes)")
                                        return img_byte_arr.getvalue()
                            except Exception as e:
                                logger.warning(f"as_image() method failed: {e}")

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


def generate_x_post(search_context: str, refined_persona: str, user_prompt: str, source_url: Optional[str], recent_topics: list, include_links: bool = False, max_retries: int = 3) -> Tuple[str, str]:
    """
    Generate X/Twitter-specific post (280 char limit, casual, punchy).
    CRITICAL: Must follow user's exact creative format/vision.

    Args:
        include_links: If True, append source URL to the post
        max_retries: Number of retry attempts before failing (default: 3)

    Returns:
        Tuple of (post_text, shortened_url)

    Raises:
        Exception: If all retries fail - caller should handle by skipping post
    """
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                logger.info(f"Retry attempt {attempt + 1}/{max_retries} for X post generation")
                time.sleep(2 ** attempt)  # Exponential backoff: 2s, 4s, 8s

            # X counts URLs as ~23 chars, but we'll use 230 chars for text to be safe
            # Only adjust max length if we're actually including the link
            max_text_length = 230 if (source_url and include_links) else 280

            avoidance_text = ""
            if recent_topics:
                topics_str = ", ".join(recent_topics[:5])
                avoidance_text = f"\n- Explore a FRESH angle - we recently covered: {topics_str}"

            draft_prompt = f"""
CONTEXT: The user's creative vision is: {user_prompt}
This describes the IMAGE/VISUAL FORMAT that will accompany the post.

Your task: Write the SOCIAL MEDIA POST TEXT (not an image description) about this topic: {search_context}

CRITICAL INSTRUCTIONS:
- DO NOT write an image generation prompt
- DO NOT describe what's in the image
- DO write a normal, engaging X/Twitter post ABOUT the technical topic
- Write FROM the persona's voice/tone: {refined_persona}
- You can reference that there's a cool visual/tutorial, but focus on the TOPIC itself

EXAMPLES OF WHAT TO DO:
✓ "When your traces get ugly and the collector starts smoking 😱 Pay attention or face detention! #OpenTelemetry #Observability"
✓ "KYAAA! Someone's sending bad traces to the collector again! Time for a lesson in proper instrumentation 📊 #OTEL"

EXAMPLES OF WHAT NOT TO DO:
✗ "(Anime sketch) Girl points at whiteboard with diagram showing..."
✗ "Drawing of anime character teaching about..."

X/TWITTER REQUIREMENTS:
- MAXIMUM {max_text_length} characters - this is STRICT
- Engaging, conversational tone
- Hook readers immediately
- Can use 1-2 relevant hashtags or emojis
- DO NOT include URLs - we'll add that separately{avoidance_text}

Write only the post text, nothing else.
"""

            response = client.models.generate_content(
                model=LLM_MODEL,
                contents=draft_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.8,  # Balanced for creativity + accuracy
                    thinking_config=types.ThinkingConfig(
                        thinking_level="HIGH"
                    )
                )
            )

            post_text = response.text.strip()

            # Critique specifically for X
            critique_prompt = f"""
Review this X/Twitter post:
"{post_text}"

Context: This post will be paired with an image that shows: {user_prompt}
Persona: {refined_persona}

Critique for:
1. Is this a SOCIAL MEDIA POST (not an image description)? If it describes the image instead of discussing the topic, REWRITE IT.
2. Character count (must be under {max_text_length} chars)
3. Does it match the persona's voice/tone?
4. Engagement potential on X/Twitter

CRITICAL: If the post reads like an image generation prompt (e.g., "Anime sketch of..." or "Drawing showing..."), you MUST rewrite it as a normal social media post about the technical topic.

If issues found, rewrite. Otherwise return unchanged.
Return only the final post text.
"""

            critique_response = client.models.generate_content(
                model=LLM_MODEL,
                contents=critique_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    thinking_config=types.ThinkingConfig(
                        thinking_level="HIGH"
                    )
                )
            )

            final_post = critique_response.text.strip()

            # Add URL if provided and user wants links included (X will auto-shorten)
            if source_url and include_links:
                final_post = f"{final_post}\n\n{source_url}"
                logger.info(f"X post with URL (total: {len(final_post)} chars)")

            return final_post, source_url if include_links else None

        except Exception as e:
            logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for X post: {e}")
            if attempt == max_retries - 1:
                # Final attempt failed - raise exception to skip posting
                logger.error(f"All {max_retries} attempts failed for X post generation", exc_info=True)
                raise
            # Continue to next retry


def generate_linkedin_post(search_context: str, refined_persona: str, user_prompt: str, source_url: Optional[str], recent_topics: list, include_links: bool = False, max_retries: int = 3) -> str:
    """
    Generate LinkedIn-specific post (longer form, professional, detailed).
    CRITICAL: Must follow user's exact creative format/vision adapted for professional audience.

    Args:
        include_links: If True, append source URL to the post
        max_retries: Number of retry attempts before failing (default: 3)

    Returns:
        Complete LinkedIn post text with context and insights

    Raises:
        Exception: If all retries fail - caller should handle by skipping post
    """
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                logger.info(f"Retry attempt {attempt + 1}/{max_retries} for LinkedIn post generation")
                time.sleep(2 ** attempt)  # Exponential backoff: 2s, 4s, 8s

            avoidance_text = ""
            if recent_topics:
                topics_str = ", ".join(recent_topics[:5])
                avoidance_text = f"\n- Explore a FRESH angle - we recently covered: {topics_str}"

            draft_prompt = f"""
CONTEXT: The user's creative vision is: {user_prompt}
This describes the IMAGE/VISUAL FORMAT that will accompany the post.

Your task: Write a PROFESSIONAL LINKEDIN POST about this topic: {search_context}

CRITICAL INSTRUCTIONS:
- DO NOT write an image generation prompt or detailed description of the visual
- DO write a thoughtful LinkedIn post ABOUT the technical topic
- Write FROM the persona's voice: {refined_persona}
- You CAN mention that there's a unique visual/tutorial format, but keep it brief and focus on the VALUE/INSIGHTS

EXAMPLES OF WHAT TO DO:
✓ "Ever dealt with messy traces clogging your OTEL collector? Here's why proper trace management matters (explained in a fun, visual way that makes complex concepts stick). Key takeaway: configure your BadTrace filters early! #OpenTelemetry"
✓ "Teaching observability concepts doesn't have to be dry. This visual breakdown of OTEL trace flow shows exactly why your collector configuration matters. The analogy? Think of it like detention for bad data 📊 #ObservabilityEngineering"

EXAMPLES OF WHAT NOT TO DO:
✗ "Check out this anime sketch showing a girl pointing at a whiteboard..."
✗ "New diagram series featuring a character teaching..."

LINKEDIN REQUIREMENTS:
- 1-3 paragraphs (no strict character limit)
- Professional, insightful tone
- Provide VALUE to readers - what will they learn?
- Engage the professional community
- Can use relevant hashtags (2-3 max)
- DO NOT use markdown formatting (no **bold**, __italics__, etc.) - LinkedIn doesn't support it
- Use plain text only with emojis if appropriate
- IMPORTANT: If there's a source URL, include it at the end on a new line: {source_url if source_url else ''}{avoidance_text}

Write the complete post in plain text format.
"""

            response = client.models.generate_content(
                model=LLM_MODEL,
                contents=draft_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.7,  # Moderate temp for professionalism
                    thinking_config=types.ThinkingConfig(
                        thinking_level="HIGH"
                    )
                )
            )

            post_text = response.text.strip()

            # Critique specifically for LinkedIn
            critique_prompt = f"""
Review this LinkedIn post:
"{post_text}"

Context: This post will be paired with an image that shows: {user_prompt}
Persona: {refined_persona}

Critique for:
1. Is this a PROFESSIONAL LINKEDIN POST (not an image description)? If it describes the image instead of discussing the topic's value, REWRITE IT.
2. Does it use markdown formatting (**bold**, __italics__, etc.)? LinkedIn doesn't support markdown - remove all markdown syntax and use plain text.
3. Professional tone appropriate for LinkedIn
4. Does it provide value/insights to readers?
5. Engagement potential and thought leadership

CRITICAL FIXES NEEDED:
- If the post reads like an image generation prompt (e.g., "Sketch showing..."), rewrite as a professional post
- If it contains markdown syntax like **text** or __text__, remove the formatting symbols
- Source URL should be at the end if present: {source_url if source_url else ''}

If issues found, rewrite. Otherwise return unchanged.
Return only the final post text in plain text format (no markdown).
"""

            critique_response = client.models.generate_content(
                model=LLM_MODEL,
                contents=critique_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.6,  # Lower temp for consistency
                    thinking_config=types.ThinkingConfig(
                        thinking_level="HIGH"
                    )
                )
            )

            final_post = critique_response.text.strip()

            # Strip any markdown formatting (LinkedIn doesn't support it)
            final_post = strip_markdown_formatting(final_post)

            # Ensure URL is included if provided, user wants links, and not already in post
            if source_url and include_links and source_url not in final_post:
                final_post = f"{final_post}\n\n{source_url}"
                logger.info(f"Added missing source URL to LinkedIn post")

            logger.info(f"LinkedIn post ({len(final_post)} chars)")

            return final_post

        except Exception as e:
            logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for LinkedIn post: {e}")
            if attempt == max_retries - 1:
                # Final attempt failed - raise exception to skip posting
                logger.error(f"All {max_retries} attempts failed for LinkedIn post generation", exc_info=True)
                raise
            # Continue to next retry


def run_agent_cycle(user_id: int):
    """
    Main agent cycle with PLATFORM-SPECIFIC content generation:
    1. Fetch campaign configuration
    2. Get recent topics to avoid repetition
    3. Search for trending topics
    4. Generate SEPARATE posts for X and LinkedIn (different lengths, tones)
    5. Generate platform-specific images
    6. Post to connected platforms
    7. Extract and save topics for future avoidance
    """
    try:
        logger.info("=" * 60)
        logger.info(f"Starting PLATFORM-SPECIFIC agent cycle for user {user_id} at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 60)

        # Get campaign configuration
        campaign = get_campaign(user_id)
        if not campaign or not campaign.get("user_prompt"):
            logger.warning(f"No campaign configured for user {user_id}. Skipping cycle.")
            return

        user_prompt = campaign["user_prompt"]
        refined_persona = campaign.get("refined_persona", "")
        visual_style = campaign.get("visual_style", "")
        include_links = campaign.get("include_links", False)

        logger.info(f"Campaign: {user_prompt}")
        logger.info(f"Persona: {refined_persona[:100]}...")
        logger.info(f"Include links: {include_links}")

        # Get recent topics to avoid repetition
        recent_topics = get_recent_topics(user_id, days=14)
        if recent_topics:
            logger.info(f"Found {len(recent_topics)} recent topics to avoid")
            logger.info(f"Recent topics: {recent_topics[:3]}...")

        # Step 1: Search for trending topics (shared between platforms)
        logger.info("[1/7] Searching for trending topics...")
        search_context, source_urls = search_trending_topics(user_prompt, refined_persona, recent_topics)
        logger.info(f"Found context: {search_context[:200]}...")

        source_url = source_urls[0] if source_urls else None
        if source_url:
            logger.info(f"Using source URL: {source_url[:80]}...")

        # Check which platforms are connected
        twitter_tokens = get_oauth_tokens(user_id, "twitter")
        linkedin_tokens = get_oauth_tokens(user_id, "linkedin")

        twitter_success = False
        linkedin_success = False
        posted_platforms = []

        # Step 2: Generate and post to X/Twitter if connected
        if twitter_tokens:
            try:
                logger.info("[2/7] Generating X-specific post...")
                x_post, x_url = generate_x_post(search_context, refined_persona, user_prompt, source_url, recent_topics, include_links)
                logger.info(f"X post: {x_post}")

                # Validate X post matches user's creative vision
                is_valid, validation_feedback = validate_content_matches_vision(x_post, user_prompt, refined_persona)
                if not is_valid:
                    logger.warning(f"X post validation failed: {validation_feedback}")
                    # Continue anyway but log the issue

                logger.info("[3/7] Generating X-optimized image...")
                x_image = generate_image(x_post, f"{visual_style} - optimized for social media, eye-catching, viral potential", user_prompt, search_context)

                if x_image:
                    logger.info(f"X image generated ({len(x_image)} bytes)")
                    logger.info("[4/7] Posting to X...")
                    twitter_success = post_to_twitter(user_id, x_post, x_image)
                    if twitter_success:
                        posted_platforms.append("twitter")
                        # Extract topics from X post with user prompt context
                        x_topics = extract_topics_from_post(x_post, user_prompt)
                        save_post_history(user_id, x_post, x_topics, ["twitter"])
                else:
                    logger.warning("No X image generated")
            except Exception as e:
                logger.error(f"Failed to generate/post X content after retries: {e}")
                logger.info("Skipping X for this cycle - no fallback post will be created")
        else:
            logger.info("[2-4/7] Skipping X (not connected)")

        # Step 3: Generate and post to LinkedIn if connected
        if linkedin_tokens:
            try:
                logger.info("[5/7] Generating LinkedIn-specific post...")
                linkedin_post = generate_linkedin_post(search_context, refined_persona, user_prompt, source_url, recent_topics, include_links)
                logger.info(f"LinkedIn post: {linkedin_post[:150]}...")

                # Validate LinkedIn post matches user's creative vision
                is_valid, validation_feedback = validate_content_matches_vision(linkedin_post, user_prompt, refined_persona)
                if not is_valid:
                    logger.warning(f"LinkedIn post validation failed: {validation_feedback}")
                    # Continue anyway but log the issue

                logger.info("[6/7] Generating LinkedIn-optimized image...")
                linkedin_image = generate_image(linkedin_post, f"{visual_style} - professional, polished, suitable for business context", user_prompt, search_context)

                if linkedin_image:
                    logger.info(f"LinkedIn image generated ({len(linkedin_image)} bytes)")
                    logger.info("[7/7] Posting to LinkedIn...")
                    linkedin_success = post_to_linkedin(user_id, linkedin_post, linkedin_image)
                    if linkedin_success:
                        posted_platforms.append("linkedin")
                        # Extract topics from LinkedIn post with user prompt context
                        linkedin_topics = extract_topics_from_post(linkedin_post, user_prompt)
                        save_post_history(user_id, linkedin_post, linkedin_topics, ["linkedin"])
                else:
                    logger.warning("No LinkedIn image generated")
            except Exception as e:
                logger.error(f"Failed to generate/post LinkedIn content after retries: {e}")
                logger.info("Skipping LinkedIn for this cycle - no fallback post will be created")
        else:
            logger.info("[5-7/7] Skipping LinkedIn (not connected)")

        # Update last run timestamp
        if posted_platforms:
            update_last_run(user_id, int(time.time()))

        logger.info("Results:")
        logger.info(f"  X/Twitter: {'✓' if twitter_success else '✗ (not connected)' if not twitter_tokens else '✗'}")
        logger.info(f"  LinkedIn: {'✓' if linkedin_success else '✗ (not connected)' if not linkedin_tokens else '✗'}")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Error in agent cycle for user {user_id}: {e}", exc_info=True)
