"""Search and topic selection for content generation."""
import json
import time
from typing import Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from google.genai import types

from .config import client, LLM_MODEL
from .utils import is_network_error
from .url_utils import (
    resolve_redirect_url,
    clean_url_text,
    is_youtube_url,
    validate_url,
    validate_and_select_url,
)
from logger_config import agent_logger as logger

# Safety limits
MAX_SEARCH_CONTEXT_FOR_LLM = 50_000   # 50KB max for search context passed to LLM
LLM_CALL_TIMEOUT = 300                  # seconds per LLM call (generous for thinking models)


def _llm_call_with_timeout(func, timeout=LLM_CALL_TIMEOUT):
    """Run an LLM call with a timeout to prevent infinite hangs."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func)
        return future.result(timeout=timeout)


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
            _search_temp = 0.7 + (search_attempt * 0.1)
            try:
                response = _llm_call_with_timeout(
                    lambda: client.models.generate_content(
                        model=LLM_MODEL,
                        contents=search_prompt,
                        config=types.GenerateContentConfig(
                            temperature=_search_temp,  # Slightly increase temperature on retries for variety
                            tools=[types.Tool(google_search=types.GoogleSearch())],
                            thinking_config=types.ThinkingConfig(
                                thinking_level="HIGH"
                            )
                        )
                    )
                )
            except FuturesTimeoutError:
                logger.error(f"LLM call timed out after {LLM_CALL_TIMEOUT}s in search_trending_topics (attempt {search_attempt + 1})")
                if search_attempt < max_search_retries - 1:
                    continue
                return f"General discussion about {user_prompt}", [], None

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
            if is_network_error(e):
                logger.warning(f"Network/QUIC error in search attempt {search_attempt + 1}: {e}")
                if search_attempt < max_search_retries - 1:
                    # Exponential backoff for network errors
                    wait_time = 2 ** search_attempt
                    logger.info(f"Retrying after {wait_time}s backoff...")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"All retries exhausted due to network errors: {e}")
                    return f"General discussion about {user_prompt}", [], None
            else:
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
    # Truncate search_context to prevent LLM hangs on massive content
    if len(search_context) > MAX_SEARCH_CONTEXT_FOR_LLM:
        logger.warning(f"Truncating search_context from {len(search_context)} to {MAX_SEARCH_CONTEXT_FOR_LLM} chars")
        search_context = search_context[:MAX_SEARCH_CONTEXT_FOR_LLM] + "\n...[truncated]"

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
            non_video_urls = [url for url in available_urls if not is_youtube_url(url)]
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

            _select_temp = 0.5 + (attempt * 0.1)
            try:
                response = _llm_call_with_timeout(
                    lambda: client.models.generate_content(
                        model=LLM_MODEL,
                        contents=selection_prompt,
                        config=types.GenerateContentConfig(
                            temperature=_select_temp,  # Slightly increase temp on retries
                            response_mime_type="application/json",
                            thinking_config=types.ThinkingConfig(
                                thinking_level="HIGH"
                            )
                        )
                    )
                )
            except FuturesTimeoutError:
                logger.error(f"LLM call timed out after {LLM_CALL_TIMEOUT}s in select_single_topic (attempt {attempt + 1})")
                if attempt < max_selection_attempts - 1:
                    continue
                return search_context, None, None

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
                cleaned_raw = clean_url_text(selected_url_raw)
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
