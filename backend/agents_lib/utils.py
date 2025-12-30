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
