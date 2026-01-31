"""Shared utility functions for agents."""
import re
import json
import time

from .config import QUIC_ERROR_PATTERNS


def is_network_error(error: Exception) -> bool:
    """Check if an error is a network/QUIC related error that should be retried."""
    error_str = str(error).lower()
    return any(pattern in error_str for pattern in QUIC_ERROR_PATTERNS)


def emit_agent_event(event_type: str, **kwargs) -> str:
    """
    Create a JSON event string for SSE streaming.

    Event types:
    - thinking: Agent is reasoning
    - tool_call: Agent is calling a tool
    - tool_result: Tool returned results
    - searching: Agent is searching
    - search_results: Search results found
    - generating: Agent is generating content
    - error: An error occurred
    - complete: Task completed
    """
    event = {
        "type": event_type,
        "timestamp": time.time(),
        **kwargs
    }
    return json.dumps(event) + "\n"


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


def sanitize_for_linkedin(text: str) -> str:
    """
    Sanitize text for LinkedIn Posts API to prevent truncation.

    Known truncation triggers:
    1. ASCII pipe '|' (U+007C) - swapped to Unicode VERTICAL LINE EXTENSION
    2. Parentheses '()' outside @[Name](urn:...) mention syntax - the Posts API
       parses parens as mention URNs, causing truncation on malformed patterns.
       We swap standalone parens to Unicode fullwidth equivalents.
    """
    # Fix 1: Replace pipe characters
    text = text.replace("|", "\u23d0")

    # Fix 2: Replace parentheses that are NOT part of @[Name](urn:...) mentions
    # Temporarily protect mention patterns
    mentions = []
    def protect_mention(m):
        mentions.append(m.group(0))
        return f"__MENTION_{len(mentions)-1}__"

    text = re.sub(r'@\[([^\]]+)\]\(([^)]+)\)', protect_mention, text)

    # Now replace remaining parens with fullwidth versions
    text = text.replace("(", "\uff08")
    text = text.replace(")", "\uff09")

    # Restore mentions
    for i, mention in enumerate(mentions):
        text = text.replace(f"__MENTION_{i}__", mention)

    return text
