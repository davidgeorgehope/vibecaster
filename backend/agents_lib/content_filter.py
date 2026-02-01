"""Content filtering for post validation.

Generic, per-user content filter.  Each user can configure an
`exclude_companies` list in their campaign settings.  Before a post
is published, it is checked against that list.

No company names are hardcoded — the list lives in the database.
"""
import re
from typing import List, Tuple

from logger_config import agent_logger as logger


def contains_excluded_company(text: str, exclude_list: List[str]) -> Tuple[bool, List[str]]:
    """
    Check whether *text* mentions any company in *exclude_list*.

    Uses word-boundary regex so "Grafana" won't false-positive on
    "grafanatic" (unlikely, but safe).

    Returns (found_any, list_of_matches).
    """
    if not text or not exclude_list:
        return False, []

    text_lower = text.lower()
    found: List[str] = []

    for company in exclude_list:
        company_clean = company.strip()
        if not company_clean:
            continue
        pattern = r"\b" + re.escape(company_clean.lower()) + r"\b"
        if re.search(pattern, text_lower):
            found.append(company_clean)

    return bool(found), found


def validate_post_content(
    post_text: str,
    exclude_companies: List[str],
    platform: str = "unknown",
) -> Tuple[bool, str]:
    """
    Validate post content before publishing.

    Args:
        post_text: The text to check.
        exclude_companies: List of company names to block.
        platform: Platform name for logging.

    Returns:
        (is_safe, reason_if_blocked)
    """
    if not post_text:
        return False, "Empty post text"

    if not exclude_companies:
        return True, ""  # nothing to check

    has_match, matches = contains_excluded_company(post_text, exclude_companies)
    if has_match:
        reason = f"Post mentions excluded companies: {', '.join(matches)}"
        logger.warning(f"\U0001f6ab BLOCKED {platform} post — {reason}")
        logger.warning(f"\U0001f6ab Post preview: {post_text[:200]}...")
        return False, reason

    return True, ""
