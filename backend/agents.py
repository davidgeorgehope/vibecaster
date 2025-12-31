import os
import sys
import time
import re
import html
import json
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urlparse
from google.genai import types
import tweepy
import requests
from PIL import Image
from io import BytesIO
import base64
from database import get_campaign, get_oauth_tokens, update_last_run, get_recent_topics, save_post_history
from logger_config import agent_logger as logger

# Import shared utilities from agents_lib
from agents_lib import (
    client,
    LLM_MODEL,
    LLM_FALLBACK,
    IMAGE_MODEL,
    QUIC_ERROR_PATTERNS,
    TOPIC_STOPWORDS,
    is_network_error,
    emit_agent_event,
    strip_markdown_formatting,
    # URL utilities
    resolve_redirect_url,
    clean_url_text,
    is_youtube_url,
    extract_html_title,
    url_seems_relevant_to_topic,
    is_soft_404,
    validate_url,
    validate_and_select_url,
    # Intent parser
    agent_intent_parser,
    # Persona
    analyze_user_prompt,
    # Social media
    post_to_twitter,
    post_to_linkedin,
    # Post generator
    generate_x_post,
    generate_linkedin_post,
    # Search
    search_trending_topics,
    select_single_topic,
    # Content generator
    generate_post_draft,
    critique_and_refine_post,
    validate_content_matches_vision,
    extract_topics_from_post,
    refine_image_prompt,
    generate_image,
    # Agent tools
    agent_search,
    agent_post_generator,
    agent_brainstorm,
    agent_generate_campaign_prompt,
    POST_BUILDER_SYSTEM_PROMPT,
    POST_BUILDER_FUNCTION_TOOL,
    # URL content
    generate_from_url,
    generate_from_url_stream,
    post_url_content,
    # Chat stream
    chat_post_builder_stream,
    parse_generated_posts,
    generate_image_for_post_builder,
    generate_video_for_post,
    generate_media_for_post_builder,
    ORCHESTRATOR_SYSTEM_PROMPT,
    ORCHESTRATOR_TOOLS,
)

# Alias private function names for backward compatibility within this file
_clean_url_text = clean_url_text
_is_youtube_url = is_youtube_url
_extract_html_title = extract_html_title
_url_seems_relevant_to_topic = url_seems_relevant_to_topic

# search, content_generator functions are now imported from agents_lib


def run_agent_cycle(user_id: int):
    """
    Main agent cycle with PLATFORM-SPECIFIC content generation:
    1. Fetch campaign configuration
    2. Get recent topics to avoid repetition
    3. Search for trending topics (returns multiple results, no URL validation yet)
    4. SELECT ONE TOPIC to focus on + VALIDATE its URL (prevents mixing concepts & dead links)
    5. Generate SEPARATE posts for X and LinkedIn (different lengths, tones)
    6. Generate platform-specific images
    7. Post to connected platforms
    8. Extract and save topics for future avoidance

    URL validation (including soft 404 detection) happens in step 4, ensuring we only
    include links that actually work. If a selected URL fails validation, we try
    selecting a different topic up to 3 times.
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

        logger.info(f"Campaign: {user_prompt}")
        logger.info(f"Persona: {refined_persona[:100]}...")

        # Get recent topics to avoid repetition
        recent_topics = get_recent_topics(user_id, days=14)
        if recent_topics:
            logger.info(f"Found {len(recent_topics)} recent topics to avoid")
            logger.info(f"Recent topics: {recent_topics[:3]}...")

        # Step 1: Search for trending topics (shared between platforms)
        # Returns raw search results - URL validation happens in topic selection
        logger.info("[1/8] Searching for trending topics...")
        search_context, source_urls, _ = search_trending_topics(user_prompt, refined_persona, recent_topics, validate_urls=False)
        if search_context:
            logger.info(f"Found context: {search_context[:200]}...")
        else:
            logger.warning("No search context found - search may have failed")
            return []  # Can't continue without search context
        logger.info(f"Found {len(source_urls)} source URLs")

        # Step 2: Select ONE topic from search results to focus on
        # This prevents mixing multiple concepts in a single post
        # IMPORTANT: Also validates the selected URL (including soft 404 detection)
        logger.info("[2/8] Selecting single topic to focus on (with URL validation)...")
        focused_context, source_url, html_content = select_single_topic(search_context, source_urls, user_prompt, recent_topics)
        if focused_context:
            logger.info(f"Focused context: {focused_context[:200]}...")
        else:
            logger.warning("No focused context returned - topic selection may have failed")
            return []  # Can't continue without focused context
        if source_url:
            logger.info(f"✅ Selected & validated source URL: {source_url[:80]}...")
        else:
            logger.warning("⚠️ No valid URL found - post will not include a link")

        # Extract topics ONCE from the focused context (used for both platforms)
        # This is more accurate than extracting from posts, and avoids duplicate LLM calls
        topics = extract_topics_from_post(focused_context, user_prompt)
        logger.info(f"Extracted topics for history: {topics}")

        # Enhance focused context with HTML content if available (from validated URL)
        enhanced_context = focused_context
        if html_content:
            # Extract useful text from HTML (limit to avoid token overload)
            # Strip HTML tags for a cleaner context
            # Remove script and style elements
            clean_html = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
            clean_html = re.sub(r'<style[^>]*>.*?</style>', '', clean_html, flags=re.DOTALL | re.IGNORECASE)
            # Remove HTML tags
            text_content = re.sub(r'<[^>]+>', ' ', clean_html)
            # Clean up whitespace
            text_content = re.sub(r'\s+', ' ', text_content).strip()
            # Limit to first 2000 chars of meaningful content
            if len(text_content) > 2000:
                text_content = text_content[:2000] + "..."
            if text_content:
                enhanced_context = f"{focused_context}\n\nADDITIONAL CONTEXT FROM SOURCE:\n{text_content}"
                logger.info(f"Enhanced focused context with {len(text_content)} chars from HTML")

        # Check which platforms are connected
        twitter_tokens = get_oauth_tokens(user_id, "twitter")
        linkedin_tokens = get_oauth_tokens(user_id, "linkedin")

        twitter_success = False
        linkedin_success = False
        posted_platforms = []

        # Step 3: Generate platform-specific posts
        x_post = None
        linkedin_post = None

        if twitter_tokens:
            try:
                logger.info("[3/6] Generating X-specific post...")
                x_post, x_url = generate_x_post(enhanced_context, refined_persona, user_prompt, source_url, recent_topics)
                logger.info(f"X post: {x_post}")
            except Exception as e:
                logger.error(f"Failed to generate X post: {e}")
                logger.info("Skipping X for this cycle")
        else:
            logger.info("[3/6] Skipping X post generation (not connected)")

        if linkedin_tokens:
            try:
                logger.info("[4/6] Generating LinkedIn-specific post...")
                linkedin_post = generate_linkedin_post(enhanced_context, refined_persona, user_prompt, source_url, recent_topics)
                logger.info(f"LinkedIn post: {linkedin_post[:150]}...")
            except Exception as e:
                logger.error(f"Failed to generate LinkedIn post: {e}")
                logger.info("Skipping LinkedIn for this cycle")
        else:
            logger.info("[4/6] Skipping LinkedIn post generation (not connected)")

        # Step 4: Generate ONE shared media (image or video, used for both platforms)
        shared_media = None
        media_type = campaign.get("media_type", "image")  # Default to image

        if x_post or linkedin_post:
            # Use whichever post is available for image context (prefer X as it's more concise)
            image_context_post = x_post or linkedin_post

            if media_type == "video":
                logger.info("[5/6] Generating shared VIDEO for all platforms...")
                shared_media = generate_video_for_post(image_context_post, visual_style, user_id)
                if shared_media:
                    logger.info(f"Shared video generated ({len(shared_media)} bytes)")
                else:
                    logger.warning("No video generated - falling back to image")
                    # Fallback to image if video generation fails
                    shared_media = generate_image(image_context_post, visual_style, user_prompt, enhanced_context)
            else:
                logger.info("[5/6] Generating shared image for all platforms...")
                shared_media = generate_image(image_context_post, visual_style, user_prompt, enhanced_context)

            if shared_media:
                logger.info(f"Shared media generated ({len(shared_media)} bytes)")
            else:
                logger.warning("No media generated")

        # Alias for backward compatibility with posting functions
        shared_image = shared_media

        # Step 5: Post to platforms (using shared topics extracted earlier)
        if twitter_tokens and x_post and shared_image:
            try:
                logger.info("[6/6] Posting to X...")
                twitter_success = post_to_twitter(user_id, x_post, shared_image)
                if twitter_success:
                    posted_platforms.append("twitter")
                    save_post_history(user_id, x_post, topics, ["twitter"])
            except Exception as e:
                logger.error(f"Failed to post to X: {e}")

        if linkedin_tokens and linkedin_post and shared_image:
            try:
                logger.info("[6/6] Posting to LinkedIn...")
                linkedin_success = post_to_linkedin(user_id, linkedin_post, shared_image)
                if linkedin_success:
                    posted_platforms.append("linkedin")
                    save_post_history(user_id, linkedin_post, topics, ["linkedin"])
            except Exception as e:
                logger.error(f"Failed to post to LinkedIn: {e}")

        # Update last run timestamp
        if posted_platforms:
            update_last_run(user_id, int(time.time()))

        logger.info("Results:")
        logger.info(f"  X/Twitter: {'✓' if twitter_success else '✗ (not connected)' if not twitter_tokens else '✗'}")
        logger.info(f"  LinkedIn: {'✓' if linkedin_success else '✗ (not connected)' if not linkedin_tokens else '✗'}")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Error in agent cycle for user {user_id}: {e}", exc_info=True)


# generate_from_url, generate_from_url_stream, post_url_content are now imported from agents_lib.url_content
# chat_post_builder_stream, parse_generated_posts, generate_image_for_post_builder,
# generate_video_for_post, generate_media_for_post_builder, ORCHESTRATOR_SYSTEM_PROMPT,
# ORCHESTRATOR_TOOLS are now imported from agents_lib.chat_stream
