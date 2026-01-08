"""LinkedIn company mention detection and substitution."""
import re
from typing import List, Set
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_active_linkedin_mentions
from logger_config import agent_logger as logger


def apply_linkedin_mentions(post_text: str) -> str:
    """
    Detect and apply LinkedIn company mentions to post text.

    Uses case-insensitive matching for company names and aliases.
    Each company is mentioned at most ONCE per post (first occurrence only).

    Args:
        post_text: The LinkedIn post text

    Returns:
        Post text with mentions applied in format @[Company Name](urn:li:organization:ID)
    """
    if not post_text:
        return post_text

    mentions = get_active_linkedin_mentions()
    if not mentions:
        return post_text

    applied_urns: Set[str] = set()  # Track which companies we've already mentioned

    for mention in mentions:
        if mention['organization_urn'] in applied_urns:
            continue

        # Build list of names to search for (primary + aliases)
        search_terms = [mention['company_name']]
        if mention.get('aliases'):
            search_terms.extend(mention['aliases'])

        # Try to find and replace first occurrence
        for term in search_terms:
            # Case-insensitive word boundary match
            # Use negative lookbehind/lookahead to avoid matching inside existing mentions
            pattern = r'(?<!\[)(?<!\()' + r'\b' + re.escape(term) + r'\b' + r'(?!\])(?!\))'
            match = re.search(pattern, post_text, re.IGNORECASE)

            if match:
                # Replace first occurrence with mention format
                mention_text = f"@[{mention['company_name']}]({mention['organization_urn']})"
                post_text = post_text[:match.start()] + mention_text + post_text[match.end():]
                applied_urns.add(mention['organization_urn'])
                logger.info(f"Applied LinkedIn mention: '{term}' -> @[{mention['company_name']}]")
                break  # Only replace first occurrence, move to next company

    return post_text


def get_mention_context_for_ai() -> str:
    """
    Generate context string for AI about available company mentions.
    This can be injected into post generation prompts if needed.

    Returns:
        Context string describing available mentions, or empty string if none
    """
    mentions = get_active_linkedin_mentions()
    if not mentions:
        return ""

    lines = ["Available LinkedIn company mentions (use company names naturally in the post):"]
    for m in mentions:
        aliases_str = f" (aliases: {', '.join(m['aliases'])})" if m.get('aliases') else ""
        lines.append(f"  - {m['company_name']}{aliases_str}")

    return "\n".join(lines)
