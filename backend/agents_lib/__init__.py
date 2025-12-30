"""
Agents module for Vibecaster.

This module provides agent functionality for post generation.
The main implementation is still in agents.py at the backend root.
These sub-modules provide shared utilities and configuration.
"""
from .config import client, LLM_MODEL, LLM_FALLBACK, IMAGE_MODEL, QUIC_ERROR_PATTERNS
from .utils import is_network_error, emit_agent_event, strip_markdown_formatting
from .exceptions import AgentError, SearchError, NetworkError, URLValidationError, GenerationError

__all__ = [
    # Config
    'client',
    'LLM_MODEL',
    'LLM_FALLBACK',
    'IMAGE_MODEL',
    'QUIC_ERROR_PATTERNS',
    # Utils
    'is_network_error',
    'emit_agent_event',
    'strip_markdown_formatting',
    # Exceptions
    'AgentError',
    'SearchError',
    'NetworkError',
    'URLValidationError',
    'GenerationError',
]
