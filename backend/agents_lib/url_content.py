"""URL content generation - generate posts from a given URL."""
import json
import re as regex_module
import base64
import threading
import time
from typing import Dict, Any, Optional

from .url_utils import validate_url, extract_html_title
from .post_generator import generate_x_post, generate_linkedin_post
from .content_generator import generate_image
from .social_media import post_to_twitter, post_to_linkedin
from .content_filter import validate_post_content
from database import get_campaign, get_oauth_tokens, save_post_history
from logger_config import agent_logger as logger


class _KeepaliveTask:
    """
    Run a blocking function with keepalive events for SSE streaming.

    Usage:
        task = _KeepaliveTask(lambda: slow_function(), "Processing")
        for keepalive in task.run():
            yield keepalive
        result = task.result
    """
    def __init__(self, func, step_name: str, keepalive_interval: int = 15):
        self.func = func
        self.step_name = step_name
        self.keepalive_interval = keepalive_interval
        self.result = None
        self._error = None

    def run(self):
        done = threading.Event()

        def worker():
            try:
                self.result = self.func()
            except Exception as e:
                self._error = e
            finally:
                done.set()

        thread = threading.Thread(target=worker)
        thread.start()

        keepalive_count = 0
        while not done.wait(timeout=self.keepalive_interval):
            keepalive_count += 1
            yield json.dumps({
                "status": "keepalive",
                "step": self.step_name,
                "message": f"{self.step_name}... ({keepalive_count * self.keepalive_interval}s)",
                "timestamp": time.time()
            })

        if self._error:
            raise self._error


def generate_from_url(user_id: int, url: str) -> Dict[str, Any]:
    """
    Generate social media posts from a given URL.

    This function:
    1. Validates and fetches content from the URL
    2. Uses campaign persona/style if available, otherwise infers from content
    3. Generates X/Twitter post, LinkedIn post, and image
    4. Returns all generated content for preview (does NOT post automatically)

    Args:
        user_id: The user ID (for campaign config lookup)
        url: The URL to generate posts from

    Returns:
        Dict with keys: x_post, linkedin_post, image_base64, source_url, error
    """
    result = {
        "x_post": None,
        "linkedin_post": None,
        "image_base64": None,
        "source_url": url,
        "error": None
    }

    try:
        logger.info("=" * 60)
        logger.info(f"Generating posts from URL for user {user_id}")
        logger.info(f"URL: {url}")
        logger.info("=" * 60)

        # Step 1: Validate and fetch URL content
        logger.info("[1/5] Validating URL and fetching content...")
        is_valid, html_content, status_code, final_url = validate_url(url, fetch_content=True)

        if not is_valid:
            error_msg = f"Could not fetch content from URL (status: {status_code})"
            logger.warning(error_msg)
            result["error"] = error_msg
            return result

        result["source_url"] = final_url

        # Extract a summary from the HTML content for context
        # Use the page title and some body text
        title = extract_html_title(html_content)

        # Strip HTML tags to get plain text (basic extraction)
        body_text = regex_module.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=regex_module.DOTALL | regex_module.IGNORECASE)
        body_text = regex_module.sub(r'<style[^>]*>.*?</style>', '', body_text, flags=regex_module.DOTALL | regex_module.IGNORECASE)
        body_text = regex_module.sub(r'<[^>]+>', ' ', body_text)
        body_text = regex_module.sub(r'\s+', ' ', body_text).strip()
        body_text = body_text[:3000]  # Limit to prevent token overflow

        search_context = f"Title: {title}\n\nContent Summary:\n{body_text}\n\nSource URL: {final_url}"
        logger.info(f"Extracted context: {search_context[:200]}...")

        # Step 2: Get campaign config or use defaults
        logger.info("[2/5] Getting persona and style settings...")
        campaign = get_campaign(user_id)

        if campaign and campaign.get("refined_persona"):
            refined_persona = campaign["refined_persona"]
            visual_style = campaign.get("visual_style", "")
            user_prompt = campaign.get("user_prompt", "Create engaging social media content")
            logger.info("Using campaign persona and style")
        else:
            # Generate a simple persona based on the content
            refined_persona = "A knowledgeable content creator who shares interesting insights in an engaging, accessible way. Professional yet approachable tone."
            visual_style = "Clean, modern digital illustration style. Professional and eye-catching visuals that complement the content."
            user_prompt = "Create engaging social media content about this topic"
            logger.info("Using default persona (no campaign configured)")

        # Step 3: Generate X/Twitter post
        logger.info("[3/5] Generating X/Twitter post...")
        try:
            x_post, _ = generate_x_post(
                search_context=search_context,
                refined_persona=refined_persona,
                user_prompt=user_prompt,
                source_url=final_url,
                recent_topics=[]
            )
            result["x_post"] = x_post
            logger.info(f"X post generated ({len(x_post)} chars)")
        except Exception as e:
            logger.error(f"Failed to generate X post: {e}")

        # Step 4: Generate LinkedIn post
        logger.info("[4/5] Generating LinkedIn post...")
        try:
            linkedin_post = generate_linkedin_post(
                search_context=search_context,
                refined_persona=refined_persona,
                user_prompt=user_prompt,
                source_url=final_url,
                recent_topics=[]
            )
            result["linkedin_post"] = linkedin_post
            logger.info(f"LinkedIn post generated ({len(linkedin_post)} chars)")
        except Exception as e:
            logger.error(f"Failed to generate LinkedIn post: {e}")

        # Step 5: Generate image
        logger.info("[5/5] Generating image...")
        try:
            image_context_post = result["x_post"] or result["linkedin_post"]
            if image_context_post:
                image_bytes = generate_image(
                    post_text=image_context_post,
                    visual_style=visual_style,
                    user_prompt=user_prompt,
                    topic_context=search_context[:1000]  # Limit context for image
                )
                if image_bytes:
                    result["image_base64"] = base64.b64encode(image_bytes).decode('utf-8')
                    logger.info(f"Image generated ({len(image_bytes)} bytes)")
                else:
                    logger.warning("Image generation returned None")
        except Exception as e:
            logger.error(f"Failed to generate image: {e}")

        logger.info("=" * 60)
        logger.info("Generation complete")
        logger.info(f"  X post: {'✓' if result['x_post'] else '✗'}")
        logger.info(f"  LinkedIn post: {'✓' if result['linkedin_post'] else '✗'}")
        logger.info(f"  Image: {'✓' if result['image_base64'] else '✗'}")
        logger.info("=" * 60)

        return result

    except Exception as e:
        logger.error(f"Error generating from URL: {e}", exc_info=True)
        result["error"] = str(e)
        return result


def generate_from_url_stream(user_id: int, url: str):
    """
    Stream social media post generation from a URL with progress updates.

    Yields JSON strings with status updates and generated content.
    This avoids timeout issues by streaming progress as content is generated.

    Args:
        user_id: The user ID (for campaign config lookup)
        url: The URL to generate posts from

    Yields:
        JSON strings with status/content updates
    """
    try:
        logger.info("=" * 60)
        logger.info(f"[STREAMING] Generating posts from URL for user {user_id}")
        logger.info(f"URL: {url}")
        logger.info("=" * 60)

        # Step 1: Validate and fetch URL content with keepalives
        yield json.dumps({"status": "fetching", "message": "Fetching URL content..."})

        fetch_task = _KeepaliveTask(
            lambda: validate_url(url, fetch_content=True),
            "Fetching URL"
        )
        for keepalive in fetch_task.run():
            yield keepalive
        is_valid, html_content, status_code, final_url = fetch_task.result

        if not is_valid:
            error_msg = f"Could not fetch content from URL (status: {status_code})"
            logger.warning(error_msg)
            yield json.dumps({"status": "error", "error": error_msg})
            return

        # Extract title and content
        title = extract_html_title(html_content)

        body_text = regex_module.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=regex_module.DOTALL | regex_module.IGNORECASE)
        body_text = regex_module.sub(r'<style[^>]*>.*?</style>', '', body_text, flags=regex_module.DOTALL | regex_module.IGNORECASE)
        body_text = regex_module.sub(r'<[^>]+>', ' ', body_text)
        body_text = regex_module.sub(r'\s+', ' ', body_text).strip()
        body_text = body_text[:3000]

        search_context = f"Title: {title}\n\nContent Summary:\n{body_text}\n\nSource URL: {final_url}"

        yield json.dumps({"status": "content", "title": title, "source_url": final_url})

        # Step 2: Get campaign config or use defaults
        campaign = get_campaign(user_id)

        if campaign and campaign.get("refined_persona"):
            refined_persona = campaign["refined_persona"]
            visual_style = campaign.get("visual_style", "")
            user_prompt = campaign.get("user_prompt", "Create engaging social media content")
        else:
            refined_persona = "A knowledgeable content creator who shares interesting insights in an engaging, accessible way. Professional yet approachable tone."
            visual_style = "Clean, modern digital illustration style. Professional and eye-catching visuals that complement the content."
            user_prompt = "Create engaging social media content about this topic"

        # Step 3: Generate X/Twitter post with keepalives
        yield json.dumps({"status": "generating_x", "message": "Generating X post..."})

        x_post = None
        try:
            x_task = _KeepaliveTask(
                lambda: generate_x_post(
                    search_context=search_context,
                    refined_persona=refined_persona,
                    user_prompt=user_prompt,
                    source_url=final_url,
                    recent_topics=[]
                ),
                "Generating X post"
            )
            for keepalive in x_task.run():
                yield keepalive
            x_post, _ = x_task.result
            yield json.dumps({"status": "x_post", "x_post": x_post})
            logger.info(f"X post generated ({len(x_post)} chars)")
        except Exception as e:
            logger.error(f"Failed to generate X post: {e}")
            yield json.dumps({"status": "x_post_error", "error": str(e)})

        # Step 4: Generate LinkedIn post with keepalives
        yield json.dumps({"status": "generating_linkedin", "message": "Generating LinkedIn post..."})

        linkedin_post = None
        try:
            linkedin_task = _KeepaliveTask(
                lambda: generate_linkedin_post(
                    search_context=search_context,
                    refined_persona=refined_persona,
                    user_prompt=user_prompt,
                    source_url=final_url,
                    recent_topics=[]
                ),
                "Generating LinkedIn post"
            )
            for keepalive in linkedin_task.run():
                yield keepalive
            linkedin_post = linkedin_task.result
            yield json.dumps({"status": "linkedin_post", "linkedin_post": linkedin_post})
            logger.info(f"LinkedIn post generated ({len(linkedin_post)} chars)")
        except Exception as e:
            logger.error(f"Failed to generate LinkedIn post: {e}")
            yield json.dumps({"status": "linkedin_post_error", "error": str(e)})

        # Step 5: Generate image with keepalives
        yield json.dumps({"status": "generating_image", "message": "Generating image..."})

        try:
            image_context_post = x_post or linkedin_post
            if image_context_post:
                image_task = _KeepaliveTask(
                    lambda: generate_image(
                        post_text=image_context_post,
                        visual_style=visual_style,
                        user_prompt=user_prompt,
                        topic_context=search_context[:1000]
                    ),
                    "Generating image"
                )
                for keepalive in image_task.run():
                    yield keepalive
                image_bytes = image_task.result
                if image_bytes:
                    image_b64 = base64.b64encode(image_bytes).decode('utf-8')
                    yield json.dumps({"status": "image", "image_base64": image_b64})
                    logger.info(f"Image generated ({len(image_bytes)} bytes)")
                else:
                    yield json.dumps({"status": "image_error", "error": "Image generation returned None"})
        except Exception as e:
            logger.error(f"Failed to generate image: {e}")
            yield json.dumps({"status": "image_error", "error": str(e)})

        # Complete
        yield json.dumps({"status": "complete", "source_url": final_url})

        logger.info("=" * 60)
        logger.info("[STREAMING] Generation complete")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Error in generate_from_url_stream: {e}", exc_info=True)
        yield json.dumps({"status": "error", "error": str(e)})


def post_url_content(user_id: int, x_post: Optional[str], linkedin_post: Optional[str],
                     image_base64: Optional[str], platforms: list) -> Dict[str, Any]:
    """
    Post pre-generated content to specified platforms.

    Args:
        user_id: The user ID
        x_post: The X/Twitter post text (or None to skip)
        linkedin_post: The LinkedIn post text (or None to skip)
        image_base64: Base64-encoded image (or None for no image)
        platforms: List of platforms to post to ['twitter', 'linkedin']

    Returns:
        Dict with keys: posted (list), errors (dict)
    """
    result = {
        "posted": [],
        "errors": {}
    }

    # Decode image if provided
    image_bytes = None
    if image_base64:
        try:
            image_bytes = base64.b64decode(image_base64)
        except Exception as e:
            logger.error(f"Failed to decode image: {e}")

    # Post to Twitter
    if 'twitter' in platforms and x_post:
        try:
            # Validate post content (competitor filtering)
            is_safe, block_reason = validate_post_content(x_post, "twitter")
            if not is_safe:
                result["errors"]["twitter"] = f"Blocked: {block_reason}"
            elif not get_oauth_tokens(user_id, "twitter"):
                result["errors"]["twitter"] = "Not connected to Twitter"
            else:
                success = post_to_twitter(user_id, x_post, image_bytes)
                if success:
                    result["posted"].append("twitter")
                    # Extract simple topic for history
                    topics = [x_post[:50].split('\n')[0]]
                    save_post_history(user_id, x_post, topics, ["twitter"])
                else:
                    result["errors"]["twitter"] = "Failed to post"
        except Exception as e:
            logger.error(f"Error posting to Twitter: {e}")
            result["errors"]["twitter"] = str(e)

    # Post to LinkedIn
    if 'linkedin' in platforms and linkedin_post:
        try:
            # Validate post content (competitor filtering)
            is_safe, block_reason = validate_post_content(linkedin_post, "linkedin")
            if not is_safe:
                result["errors"]["linkedin"] = f"Blocked: {block_reason}"
            elif not get_oauth_tokens(user_id, "linkedin"):
                result["errors"]["linkedin"] = "Not connected to LinkedIn"
            else:
                success = post_to_linkedin(user_id, linkedin_post, image_bytes)
                if success:
                    result["posted"].append("linkedin")
                    topics = [linkedin_post[:50].split('\n')[0]]
                    save_post_history(user_id, linkedin_post, topics, ["linkedin"])
                else:
                    result["errors"]["linkedin"] = "Failed to post"
        except Exception as e:
            logger.error(f"Error posting to LinkedIn: {e}")
            result["errors"]["linkedin"] = str(e)

    return result
