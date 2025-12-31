"""URL validation, redirect resolution, and utility functions."""
import re
import html
from typing import Optional, Tuple
from urllib.parse import urlparse
import requests

from .config import TOPIC_STOPWORDS
from logger_config import agent_logger as logger


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


def clean_url_text(url: Optional[str]) -> Optional[str]:
    """Clean and normalize URL text, removing quotes and trailing punctuation."""
    if not url:
        return None
    cleaned = str(url).strip().strip('"\'' ).strip()
    cleaned = cleaned.rstrip(").,;")
    if not cleaned:
        return None
    if cleaned.lower() in {"null", "none"}:
        return None
    return cleaned


def is_youtube_url(url: str) -> bool:
    """Check if a URL is a YouTube URL."""
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


def extract_html_title(html_content: Optional[str]) -> str:
    """Extract the title from HTML content."""
    if not html_content:
        return ""
    match = re.search(r"<title[^>]*>(.*?)</title>", html_content, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    title = re.sub(r"\s+", " ", match.group(1)).strip()
    return html.unescape(title)


def url_seems_relevant_to_topic(selected_topic: str, final_url: str, html_content: Optional[str]) -> bool:
    """
    Lightweight sanity check to prevent obviously mismatched links being posted.
    """
    if not selected_topic:
        return True

    tokens = [
        t for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9\\-]{2,}", selected_topic.lower())
        if t not in TOPIC_STOPWORDS
    ]
    if not tokens:
        return True

    title = extract_html_title(html_content).lower()
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
