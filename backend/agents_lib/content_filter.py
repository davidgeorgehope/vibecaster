"""Content filtering for post validation.

Prevents automated posts from mentioning competitors of Elastic
(David's employer). This is a safety net for automated posting only.
"""
import re
from typing import Tuple, List

from logger_config import agent_logger as logger

# Elastic competitors - case-insensitive matching
ELASTIC_COMPETITORS = [
    "sumo logic",
    "sumologic",
    "datadog",
    "splunk",
    "dynatrace",
    "new relic",
    "newrelic",
    "grafana labs",
    "grafana",
    "cribl",
    "logz.io",
    "coralogix",
]


def contains_competitor_mention(text: str) -> Tuple[bool, List[str]]:
    """
    Check if text mentions any Elastic competitors.

    Args:
        text: Post text to check

    Returns:
        Tuple of (has_competitors, list_of_found_competitors)
    """
    if not text:
        return False, []

    text_lower = text.lower()
    found = []

    for competitor in ELASTIC_COMPETITORS:
        # Use word boundary matching to avoid false positives
        # e.g., "grafana" shouldn't match "grafanatic" (unlikely but safe)
        pattern = r'\b' + re.escape(competitor) + r'\b'
        if re.search(pattern, text_lower):
            found.append(competitor)

    return bool(found), found


def validate_post_content(post_text: str, platform: str = "unknown") -> Tuple[bool, str]:
    """
    Validate post content before publishing.
    Returns (is_safe, reason) - if not safe, reason explains why.

    Args:
        post_text: The post text to validate
        platform: Platform name for logging (e.g., "twitter", "linkedin")

    Returns:
        Tuple of (is_safe, reason_if_blocked)
    """
    if not post_text:
        return False, "Empty post text"

    has_competitors, competitors = contains_competitor_mention(post_text)
    if has_competitors:
        reason = f"Post mentions Elastic competitors: {', '.join(competitors)}"
        logger.warning(f"🚫 BLOCKED {platform} post - {reason}")
        logger.warning(f"🚫 Post preview: {post_text[:200]}...")
        return False, reason

    return True, ""
