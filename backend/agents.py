import os
import sys
import time
import re
import html
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urlparse
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
    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; Vibecaster/1.0; +https://vibecaster.app)',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }

    # HEAD is cheapest, but some redirectors (and some CDNs) don't support it well.
    try:
        response = requests.head(url, allow_redirects=True, timeout=10, headers=headers)
        if response.url and response.url != url:
            logger.info(f"Resolved redirect (HEAD): {url[:60]}... -> {response.url}")
            return response.url
    except Exception as e:
        logger.debug(f"HEAD redirect resolution failed for {url[:60]}...: {e}")

    # Fallback: GET with streaming (do not download full body).
    try:
        response = requests.get(url, allow_redirects=True, timeout=10, headers=headers, stream=True)
        final_url = response.url or url
        response.close()
        if final_url != url:
            logger.info(f"Resolved redirect (GET): {url[:60]}... -> {final_url}")
        return final_url
    except Exception as e:
        logger.warning(f"Could not resolve redirect for {url[:60]}...: {e}")
        return url  # Return original URL if resolution fails


def _clean_url_text(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    cleaned = str(url).strip().strip('"\'' ).strip()
    cleaned = cleaned.rstrip(").,;")
    if not cleaned:
        return None
    if cleaned.lower() in {"null", "none"}:
        return None
    return cleaned


def _is_youtube_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


def _extract_html_title(html_content: Optional[str]) -> str:
    if not html_content:
        return ""
    match = re.search(r"<title[^>]*>(.*?)</title>", html_content, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    title = re.sub(r"\s+", " ", match.group(1)).strip()
    return html.unescape(title)


_TOPIC_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how", "in", "into",
    "is", "it", "its", "of", "on", "or", "our", "that", "the", "this", "to", "via", "we", "with",
}


def _url_seems_relevant_to_topic(selected_topic: str, final_url: str, html_content: Optional[str]) -> bool:
    """
    Lightweight sanity check to prevent obviously mismatched links being posted.
    """
    if not selected_topic:
        return True

    tokens = [
        t for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9\\-]{2,}", selected_topic.lower())
        if t not in _TOPIC_STOPWORDS
    ]
    if not tokens:
        return True

    title = _extract_html_title(html_content).lower()
    haystack = f"{final_url.lower()} {title}"
    # If NONE of the meaningful topic tokens appear in the URL or <title>, it's very likely unrelated.
    return any(token in haystack for token in tokens[:8])


def is_soft_404(html_content: str, url: str) -> bool:
    """
    Detect "soft 404" pages - pages that return HTTP 200 but display 404/error content.
    Many sites (including Elastic) handle 404s at the application layer, not web server.

    Args:
        html_content: The HTML content of the page
        url: The URL (for logging)

    Returns:
        True if this appears to be a soft 404 page
    """
    if not html_content:
        return False

    # Lowercase for case-insensitive matching
    content_lower = html_content.lower()

    # Common soft 404 indicators in page content
    soft_404_patterns = [
        # Generic 404 phrases
        'page not found',
        'page could not be found',
        'page doesn\'t exist',
        'page does not exist',
        'not found</title>',
        '404</title>',
        'error 404',
        '404 error',
        # Elastic-specific patterns
        'this page doesn\'t exist',
        'we couldn\'t find',
        'the page you\'re looking for',
        'this content has moved',
        'content not available',
        'something\'s amiss',
        'hmmm… something\'s amiss',
        'we\'re really good at search but can\'t seem to find',
        # Common CMS 404 patterns
        'oops! that page',
        'sorry, we can\'t find',
        'nothing found',
        'no results found',
        # Meta indicators
        '<meta name="robots" content="noindex',
    ]

    for pattern in soft_404_patterns:
        if pattern in content_lower:
            logger.warning(f"Soft 404 detected for {url[:60]}... (matched: '{pattern}')")
            return True

    # Check for very short content (often a sign of error pages)
    # But only if it also lacks typical article indicators
    content_length = len(html_content)
    has_article_content = any(indicator in content_lower for indicator in [
        '<article', 'class="article', 'class="post', 'class="content',
        'class="blog', '<main', 'class="documentation'
    ])

    if content_length < 5000 and not has_article_content:
        # Very short page without article markers - suspicious
        logger.warning(f"Suspicious short page ({content_length} chars) without article content: {url[:60]}...")
        return True

    return False


def validate_url(url: str, fetch_content: bool = True) -> Tuple[bool, Optional[str], Optional[int], str]:
    """
    Validate a URL by fetching it and checking for 404 or other errors.
    Also detects "soft 404s" - pages that return 200 but show error content.
    Optionally returns raw HTML content for additional context.

    Args:
        url: The URL to validate
        fetch_content: If True, fetches and returns raw HTML content

    Returns:
        Tuple of (is_valid, html_content, status_code, final_url)
        - is_valid: True if URL returns 2xx status AND is not a soft 404
        - html_content: Raw HTML if fetch_content=True and URL is valid, else None
        - status_code: HTTP status code or None if request failed
        - final_url: Final URL after following redirects (best effort)
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; Vibecaster/1.0; +https://vibecaster.app)',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }

        if fetch_content:
            response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        else:
            response = requests.head(url, headers=headers, timeout=10, allow_redirects=True)

        status_code = response.status_code
        final_url = response.url or url
        is_valid = 200 <= status_code < 300

        if is_valid and fetch_content:
            html_content = response.text
            # Check for soft 404 (200 status but 404-like content)
            if is_soft_404(html_content, url):
                logger.warning(f"URL is soft 404: {url[:60]}... (status: {status_code})")
                return False, None, 404, final_url  # Treat as 404
            logger.info(f"URL validated successfully: {url[:60]}... (status: {status_code})")
            return True, html_content, status_code, final_url
        elif is_valid:
            # HEAD request - can't check for soft 404
            logger.info(f"URL validated successfully (HEAD): {url[:60]}... (status: {status_code})")
            return True, None, status_code, final_url
        else:
            logger.warning(f"URL validation failed: {url[:60]}... (status: {status_code})")
            return False, None, status_code, final_url

    except requests.exceptions.Timeout:
        logger.warning(f"URL validation timeout: {url[:60]}...")
        return False, None, None, url
    except requests.exceptions.RequestException as e:
        logger.warning(f"URL validation error for {url[:60]}...: {e}")
        return False, None, None, url


def validate_and_select_url(urls: list, fetch_content: bool = True) -> Tuple[Optional[str], Optional[str]]:
    """
    Validate a list of URLs and return the first valid one with its content.

    Args:
        urls: List of URLs to validate
        fetch_content: If True, fetches and returns raw HTML content

    Returns:
        Tuple of (valid_url, html_content) or (None, None) if all URLs are invalid
    """
    for url in urls:
        is_valid, html_content, status_code, final_url = validate_url(url, fetch_content)
        if is_valid:
            return final_url, html_content
        elif status_code == 404:
            logger.info(f"Skipping 404 URL, trying next: {url[:60]}...")
        else:
            logger.info(f"Skipping invalid URL (status {status_code}), trying next: {url[:60]}...")

    logger.warning(f"All {len(urls)} URLs failed validation")
    return None, None


def analyze_user_prompt(user_prompt: str) -> Tuple[str, str]:
    """
    Analyze user prompt to generate refined persona and visual style.
    CRITICAL: Preserves the user's exact creative vision and specific requirements.

    Returns:
        Tuple of (refined_persona, visual_style)
    """
    try:
        analysis_prompt = f"""
Analyze this social media automation request and generate:

1. A REFINED PERSONA - A detailed system instruction that STRICTLY PRESERVES the user's exact creative vision, voice, tone, and specific requirements
2. A VISUAL STYLE - Art direction that EXACTLY follows the user's specified visual requirements

CRITICAL: If the user specifies a particular creative concept (e.g., "anime girl teaching", "stick figures explaining", "meme format"), you MUST preserve that exact concept in both outputs. DO NOT generalize or dilute their vision.

User Request: "{user_prompt}"

Respond in this exact JSON format:
{{
    "refined_persona": "Your detailed persona description that preserves ALL user requirements",
    "visual_style": "Your visual style description that EXACTLY matches user specifications"
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

        return data.get("refined_persona", ""), data.get("visual_style", "")

    except Exception as e:
        logger.error(f"Error analyzing prompt: {e}", exc_info=True)
        # Fallback: preserve user's original prompt exactly
        return (
            f"IMPORTANT: Follow this exact creative direction: {user_prompt}",
            f"Visual style as specified: {user_prompt}"
        )


def search_trending_topics(user_prompt: str, refined_persona: str, recent_topics: list = None, max_search_retries: int = 3, validate_urls: bool = True) -> Tuple[str, list, Optional[str]]:
    """
    Search for relevant content that fits the user's creative vision.
    CRITICAL: Finds content that can be presented in the user's specified format,
    not just "trending news".

    Includes URL validation - will retry the Google search if all URLs return 404.

    Args:
        user_prompt: The user's campaign prompt with creative direction
        refined_persona: The refined persona description
        recent_topics: List of specific topics covered in the last 2 weeks to avoid
        max_search_retries: Number of times to retry search if all URLs are 404 (default: 3)
        validate_urls: If True, validates URLs and fetches content (default: True)

    Returns:
        Tuple of (search_context, urls_list, html_content) where:
        - search_context: The search results text
        - urls_list: List of source URLs (validated if validate_urls=True)
        - html_content: Raw HTML from the first valid URL (for additional context)
    """
    # Retry loop for URL validation
    for search_attempt in range(max_search_retries):
        try:
            if search_attempt > 0:
                logger.info(f"Search retry attempt {search_attempt + 1}/{max_search_retries} - previous URLs were invalid")
                time.sleep(2 ** search_attempt)  # Exponential backoff

            # Build avoidance instruction if we have recent topics
            avoidance_text = ""
            if recent_topics:
                topics_str = "\n- ".join(recent_topics)
                avoidance_text = f"""

IMPORTANT: We've recently covered these specific topics, so explore DIFFERENT aspects or angles:
- {topics_str}

Look for new angles, different sub-topics, or emerging developments we haven't discussed yet.
"""

            # Add retry context to get different results
            retry_context = ""
            if search_attempt > 0:
                retry_context = f"\n\nNOTE: Previous search returned outdated/broken links. Please find DIFFERENT, more recent sources (attempt {search_attempt + 1})."

            search_prompt = f"""
USER'S FULL INSTRUCTIONS (READ CAREFULLY - includes source restrictions, topics, and format):
{user_prompt}

YOUR TASK: Find content that FITS this creative format while STRICTLY RESPECTING any source restrictions above.

CRITICAL RULES:
1. If the user specifies source restrictions (e.g., "only from X", "no competitors", "stick to X material"), you MUST only return content from those allowed sources
2. If the user names specific topics/products, search for content about THOSE topics from the allowed sources
3. Find recent developments, best practices, or educational content (preference: last 48 hours to 1 week)
4. Content should be suitable for the user's creative presentation format

Persona for context: {refined_persona}{avoidance_text}{retry_context}

Provide:
1. A summary of content found that fits the creative format AND respects source restrictions
2. Key concepts or topics that work well in this format
3. Source URLs (ONLY from allowed sources if restrictions were specified)
"""

            # Use Google Search grounding with Gemini 3
            response = client.models.generate_content(
                model=LLM_MODEL,
                contents=search_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.7 + (search_attempt * 0.1),  # Slightly increase temperature on retries for variety
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    thinking_config=types.ThinkingConfig(
                        thinking_level="HIGH"
                    )
                )
            )

            # Debug: Log the full response structure when text is None
            if not response.text:
                logger.warning(f"Response text is None/empty. Full response: {response}")
                if hasattr(response, 'candidates') and response.candidates:
                    for i, candidate in enumerate(response.candidates):
                        logger.warning(f"Candidate {i}: finish_reason={getattr(candidate, 'finish_reason', 'N/A')}")
                        if hasattr(candidate, 'safety_ratings'):
                            logger.warning(f"Safety ratings: {candidate.safety_ratings}")
                        if hasattr(candidate, 'content'):
                            logger.warning(f"Content: {candidate.content}")
                else:
                    logger.warning("No candidates in response")

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

            # Get response text, handling None case
            response_text = response.text if response.text else f"General discussion about {user_prompt}"

            # Validate URLs if enabled
            if validate_urls and urls:
                valid_url, html_content = validate_and_select_url(urls, fetch_content=True)
                if valid_url:
                    logger.info(f"Found valid URL: {valid_url[:60]}...")
                    if html_content:
                        logger.info(f"Fetched {len(html_content)} bytes of HTML content for additional context")
                    return response_text, [valid_url] + [u for u in urls if u != valid_url], html_content
                else:
                    # All URLs failed validation - retry search
                    logger.warning(f"All {len(urls)} URLs failed validation on search attempt {search_attempt + 1}")
                    if search_attempt < max_search_retries - 1:
                        continue  # Retry the search
                    else:
                        logger.error("All search retries exhausted with no valid URLs")
                        return response_text, urls, None  # Return anyway with unvalidated URLs
            else:
                # No validation requested or no URLs found
                return response_text, urls, None

        except Exception as e:
            logger.error(f"Error in search attempt {search_attempt + 1}: {e}", exc_info=True)
            if search_attempt == max_search_retries - 1:
                return f"General discussion about {user_prompt}", [], None

    return f"General discussion about {user_prompt}", [], None


def select_single_topic(search_context: str, source_urls: list, user_prompt: str, recent_topics: list = None, max_selection_attempts: int = 3) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Select ONE specific topic from search results to focus the post on.
    This prevents the post from mixing multiple concepts together.

    Args:
        search_context: Raw search results (may contain multiple topics)
        source_urls: List of URLs from search results
        user_prompt: User's campaign prompt for context
        recent_topics: Topics to avoid (recently covered)
        max_selection_attempts: Number of times to retry if URL is truly broken (404)

    Returns:
        Tuple of (focused_context, selected_url, html_content) where:
        - focused_context: Context about ONE specific topic only
        - selected_url: The URL selected by the LLM (validated for 404s only)
        - html_content: The HTML content from the URL (for additional context)
    """
    broken_urls = []  # Only track URLs that are actually broken (404, etc.)

    for attempt in range(max_selection_attempts):
        try:
            if attempt > 0:
                logger.info(f"Topic selection retry {attempt + 1}/{max_selection_attempts} - previous URL was broken")

            avoidance_text = ""
            if recent_topics:
                topics_str = ", ".join(recent_topics[:5])
                avoidance_text = f"""

AVOID these recently covered topics - pick something DIFFERENT:
- {topics_str}
"""

            # Filter out URLs that are actually broken
            available_urls = [url for url in source_urls if url not in broken_urls]
            if not available_urls:
                logger.warning("No more URLs available to try")
                return search_context, None, None

            # Prefer non-video sources when we have them (prevents random YouTube links).
            non_video_urls = [url for url in available_urls if not _is_youtube_url(url)]
            urls_for_selection = non_video_urls or available_urls

            # Keep the prompt compact but include enough URLs to find the right match.
            max_urls_in_prompt = 20
            max_chars_in_prompt = 2500
            urls_in_prompt = []
            current_chars = 0
            for url in urls_for_selection:
                if len(urls_in_prompt) >= max_urls_in_prompt:
                    break
                # +6 to account for numbering and formatting
                if current_chars + len(url) + 6 > max_chars_in_prompt:
                    break
                urls_in_prompt.append(url)
                current_chars += len(url) + 6

            urls_text = "\n".join([f"{i}. {url}" for i, url in enumerate(urls_in_prompt, start=1)])

            # Add context about broken URLs if we're retrying
            broken_text = ""
            if broken_urls:
                broken_text = f"""

DO NOT select these URLs (they are broken/unavailable):
{chr(10).join([f'- {url}' for url in broken_urls])}
"""

            selection_prompt = f"""
You are a content curator. Your task is to select ONE specific topic from these search results.

USER'S CREATIVE VISION: {user_prompt}

SEARCH RESULTS (contains multiple topics/articles):
{search_context}

AVAILABLE SOURCE URLs:
{urls_text}
{avoidance_text}{broken_text}

YOUR TASK:
1. Identify all the distinct topics/concepts in the search results
2. Select the SINGLE most compelling, recent, or interesting one
3. Extract ONLY the information about that one topic
4. Match it with the most relevant URL from the AVAILABLE list

URL SELECTION RULES (IMPORTANT):
- STRONGLY prefer specific, deep-linked URLs over generic ones
- AVOID generic URLs like: /blog, /news, /articles, /resources (these are index pages)
- PREFER URLs with specific paths like: /blog/specific-article-title, /docs/feature-name, /announcements/release-v2
- The URL should link to the SPECIFIC article/page about your selected topic, not a landing page
- Only use a generic URL as a last resort if no specific URLs are available

RESPOND IN THIS EXACT JSON FORMAT:
{{
    "selected_topic": "Brief name of the topic (e.g., 'OpenTelemetry Collector filtering')",
    "focused_context": "All relevant details about THIS ONE topic only. Include specific facts, features, benefits, or insights. 2-4 sentences.",
    "selected_url_index": "The NUMBER of the URL above most relevant to this topic (1-based), or null if none match",
    "selected_url": "OPTIONAL: the exact URL string from the list above, or null if none match",
    "reasoning": "Why this topic is the best choice for a social media post"
}}
"""

            response = client.models.generate_content(
                model=LLM_MODEL,
                contents=selection_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.5 + (attempt * 0.1),  # Slightly increase temp on retries
                    response_mime_type="application/json",
                    thinking_config=types.ThinkingConfig(
                        thinking_level="HIGH"
                    )
                )
            )

            import json
            result = json.loads(response.text)

            selected_topic = result.get("selected_topic", "")
            focused_context = result.get("focused_context", search_context)
            selected_url_index = result.get("selected_url_index")
            selected_url_raw = result.get("selected_url")
            reasoning = result.get("reasoning", "")

            logger.info(f"🎯 Selected single topic: {selected_topic}")
            logger.info(f"📝 Reasoning: {reasoning}")
            logger.info(f"🔢 Selected URL index: {selected_url_index}")
            logger.info(f"🔗 Selected URL (raw): {selected_url_raw}")

            # Get URL from index first (most reliable), fall back to raw URL ONLY if it's in our list
            # This prevents hallucinated URLs - we only accept URLs from the grounded search results
            selected_url: Optional[str] = None
            if isinstance(selected_url_index, int) and 1 <= selected_url_index <= len(urls_in_prompt):
                selected_url = urls_in_prompt[selected_url_index - 1]
                logger.info(f"✅ URL selected by index {selected_url_index}")
            else:
                # Only accept raw URL if it exactly matches one in our list (prevents hallucination)
                cleaned_raw = _clean_url_text(selected_url_raw)
                if cleaned_raw and cleaned_raw in urls_in_prompt:
                    selected_url = cleaned_raw
                    logger.info(f"✅ URL selected by exact match in list")
                elif cleaned_raw:
                    logger.warning(f"❌ LLM returned URL not in provided list (potential hallucination): {cleaned_raw[:80]}...")
                    logger.info("Will retry with different topic selection")

            # No URL selected by LLM - retry to get a different topic with valid URL
            # (URLs are now required, so we don't return without one)
            if not selected_url:
                logger.warning("No valid URL selected - retrying topic selection")
                continue

            # Validate the URL - only reject if it's actually broken (404, soft-404)
            logger.info(f"🔍 Validating selected URL: {selected_url[:60]}...")
            is_valid, html_content, status_code, final_url = validate_url(selected_url, fetch_content=True)

            if is_valid:
                # Use the final resolved URL (handles redirects)
                chosen_url = final_url or selected_url
                logger.info(f"✅ URL validated successfully -> {chosen_url}")
                return focused_context, chosen_url, html_content
            else:
                # URL is actually broken - mark it and retry with a different topic
                logger.warning(f"❌ URL is broken (status: {status_code}) - will retry with different topic")
                broken_urls.append(selected_url)
                if final_url and final_url != selected_url:
                    broken_urls.append(final_url)
                continue

        except Exception as e:
            logger.error(f"Error in topic selection attempt {attempt + 1}: {e}", exc_info=True)
            if attempt == max_selection_attempts - 1:
                break

    # All attempts exhausted - return context without URL
    logger.warning(f"All {max_selection_attempts} topic selection attempts failed to find working URL")
    return search_context, None, None


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


def refine_image_prompt(post_text: str, visual_style: str, user_prompt: str, topic_context: str = "") -> str:
    """
    STEP 1 (The Brain): Use the text reasoning model to deeply think about
    the best way to visualize the content and generate a refined, detailed prompt.

    This enables "thinking" before image generation since the image model
    doesn't support thinking_config.

    Args:
        post_text: The generated social media post content
        visual_style: The extracted visual style specification
        user_prompt: The original user prompt - provides crucial context about intent and purpose
        topic_context: The focused single-topic context - provides specific technical details to visualize
                      (This is the OUTPUT of select_single_topic, NOT raw search results)

    Returns:
        A refined, detailed image generation prompt
    """
    try:
        # Build topic context section if available
        topic_context_section = ""
        if topic_context:
            topic_context_section = f"""
TOPIC DETAILS (use this to understand WHAT specific concept/feature to visualize):
{topic_context[:1500]}

"""

        refining_prompt = f"""
You are an expert art director specializing in social media visuals.

ORIGINAL USER INTENT (important context for understanding the purpose): {user_prompt}

VISUAL STYLE SPECIFICATION (MUST FOLLOW EXACTLY): {visual_style}
{topic_context_section}
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


def generate_image(post_text: str, visual_style: str, user_prompt: str, topic_context: str = "") -> Optional[bytes]:
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
        topic_context: The focused single-topic context - provides specific technical details to visualize
                      (This is the OUTPUT of select_single_topic, NOT raw search results)

    Returns:
        Image bytes or None if generation fails
    """
    try:
        # STEP 1: The Brain (Reasoning Phase)
        # Use text model with thinking to create a refined, detailed prompt
        refined_prompt = refine_image_prompt(post_text, visual_style, user_prompt, topic_context)

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


def generate_x_post(search_context: str, refined_persona: str, user_prompt: str, source_url: Optional[str], recent_topics: list, max_retries: int = 3) -> Tuple[str, str]:
    """
    Generate X/Twitter-specific post (280 char limit, casual, punchy).
    CRITICAL: Must follow user's exact creative format/vision.

    URLs are always included when available (grounded search provides credible sources).

    Args:
        max_retries: Number of retry attempts before failing (default: 3)

    Returns:
        Tuple of (post_text, source_url)

    Raises:
        Exception: If all retries fail - caller should handle by skipping post
    """
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                logger.info(f"Retry attempt {attempt + 1}/{max_retries} for X post generation")
                time.sleep(2 ** attempt)  # Exponential backoff: 2s, 4s, 8s

            # X counts URLs as ~23 chars, but we'll use 230 chars for text to be safe
            # Always reserve space for URL since we always include it
            max_text_length = 230 if source_url else 280

            avoidance_text = ""
            if recent_topics:
                topics_str = ", ".join(recent_topics[:5])
                avoidance_text = f"\n- Explore a FRESH angle - we recently covered: {topics_str}"

            prompt = f"""
USER'S CREATIVE VISION: {user_prompt}
This describes the IMAGE/VISUAL FORMAT that will accompany the post.

TOPIC CONTEXT (pick ONE specific concept to focus on):
{search_context}

YOUR TASK: Write ONE polished, publication-ready X/Twitter post about a SINGLE topic from the context above.

STRUCTURE YOUR POST:
1. Start with a hook that introduces the topic (what problem/concept?)
2. Add the insight/lesson (what's the takeaway?)
3. End with engagement (question, call-to-action, or hashtags)

CRITICAL RULES:
- Pick ONE specific topic/concept - do NOT list multiple options
- Write a SINGLE cohesive post, not bullet points or fragments
- Write FROM the persona's voice/tone: {refined_persona}
- DO NOT describe the image - the image will accompany this text
- DO NOT write an image generation prompt
- DO NOT write "Option 1/2/3" or multiple alternatives

QUALITY CHECK (self-review before outputting):
- Is it ONE flowing post (not fragmented/bullet points)?
- Does it have a clear hook that introduces the topic?
- Is it under {max_text_length} characters?
- Does it match the persona's voice?

X/TWITTER REQUIREMENTS:
- MAXIMUM {max_text_length} characters - this is STRICT
- Engaging, conversational tone with a clear hook
- Can use 1-2 relevant hashtags or emojis
- DO NOT include URLs - we'll add that separately{avoidance_text}

Write ONLY the final post text, nothing else.
"""

            response = client.models.generate_content(
                model=LLM_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.8,
                    thinking_config=types.ThinkingConfig(
                        thinking_level="HIGH"
                    )
                )
            )

            final_post = response.text.strip()

            # Always add URL if provided and not already in post
            if source_url and source_url not in final_post:
                final_post = f"{final_post}\n\n{source_url}"
                logger.info(f"X post with URL (total: {len(final_post)} chars)")

            return final_post, source_url

        except Exception as e:
            logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for X post: {e}")
            if attempt == max_retries - 1:
                # Final attempt failed - raise exception to skip posting
                logger.error(f"All {max_retries} attempts failed for X post generation", exc_info=True)
                raise
            # Continue to next retry


def generate_linkedin_post(search_context: str, refined_persona: str, user_prompt: str, source_url: Optional[str], recent_topics: list, max_retries: int = 3) -> str:
    """
    Generate LinkedIn-specific post (longer form, professional, detailed).
    CRITICAL: Must follow user's exact creative format/vision adapted for professional audience.

    URLs are always included when available (grounded search provides credible sources).

    Args:
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

            prompt = f"""
CONTEXT: The user's creative vision is: {user_prompt}
This describes the IMAGE/VISUAL FORMAT that will accompany the post.

Your task: Write a polished, publication-ready PROFESSIONAL LINKEDIN POST about this topic: {search_context}

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

QUALITY CHECK (self-review before outputting):
- Is this a professional post about the TOPIC (not an image description)?
- Does it provide real value/insights to readers?
- Is the tone professional and appropriate for LinkedIn?
- Is it free of markdown formatting (no **bold**, __italics__, etc.)?

LINKEDIN REQUIREMENTS:
- 1-3 paragraphs (no strict character limit)
- Professional, insightful tone
- Provide VALUE to readers - what will they learn?
- Engage the professional community
- Can use relevant hashtags (2-3 max)
- Use plain text only with emojis if appropriate - NO markdown formatting
- DO NOT include URLs - we'll add that separately{avoidance_text}

Write ONLY the final post text in plain text format, nothing else.
"""

            response = client.models.generate_content(
                model=LLM_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    thinking_config=types.ThinkingConfig(
                        thinking_level="HIGH"
                    )
                )
            )

            final_post = response.text.strip()

            # Strip any markdown formatting (LinkedIn doesn't support it)
            final_post = strip_markdown_formatting(final_post)

            # Always add URL if provided and not already in post
            if source_url and source_url not in final_post:
                final_post = f"{final_post}\n\n{source_url}"
                logger.info(f"Added source URL to LinkedIn post")

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

        # Step 4: Generate ONE shared image (used for both platforms)
        shared_image = None
        if x_post or linkedin_post:
            # Use whichever post is available for image context (prefer X as it's more concise)
            image_context_post = x_post or linkedin_post
            logger.info("[5/6] Generating shared image for all platforms...")
            shared_image = generate_image(image_context_post, visual_style, user_prompt, enhanced_context)
            if shared_image:
                logger.info(f"Shared image generated ({len(shared_image)} bytes)")
            else:
                logger.warning("No image generated")

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
        title = _extract_html_title(html_content)

        # Strip HTML tags to get plain text (basic extraction)
        import re as regex_module
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
            twitter_tokens = get_oauth_tokens(user_id, "twitter")
            if not twitter_tokens:
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
            linkedin_tokens = get_oauth_tokens(user_id, "linkedin")
            if not linkedin_tokens:
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
