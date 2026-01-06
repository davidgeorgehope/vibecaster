"""
Agents module for Vibecaster.

This module provides agent functionality for post generation.
The main implementation is still in agents.py at the backend root.
These sub-modules provide shared utilities and configuration.
"""
from .config import client, LLM_MODEL, LLM_FALLBACK, IMAGE_MODEL, QUIC_ERROR_PATTERNS, TOPIC_STOPWORDS
from .utils import is_network_error, emit_agent_event, strip_markdown_formatting
from .exceptions import AgentError, SearchError, NetworkError, URLValidationError, GenerationError
from .url_utils import (
    resolve_redirect_url,
    clean_url_text,
    is_youtube_url,
    extract_html_title,
    url_seems_relevant_to_topic,
    is_soft_404,
    validate_url,
    validate_and_select_url,
)
from .intent_parser import (
    agent_intent_parser,
    INTENT_GENERATE_POSTS,
    INTENT_BRAINSTORM,
    INTENT_GENERATE_CAMPAIGN,
    INTENT_GREETING,
    INTENT_CLARIFY,
    DEFAULT_PERSONA,
    DEFAULT_VISUAL_STYLE,
    is_greeting_intent,
    is_clarify_intent,
    is_generate_posts_intent,
    is_brainstorm_intent,
    is_campaign_intent,
)
from .persona import (
    analyze_user_prompt,
    create_fallback_persona,
)
from .social_media import (
    post_to_twitter,
    post_to_linkedin,
)
from .post_generator import (
    generate_x_post,
    generate_linkedin_post,
)
from .search import (
    search_trending_topics,
    select_single_topic,
)
from .content_generator import (
    generate_post_draft,
    critique_and_refine_post,
    validate_content_matches_vision,
    extract_topics_from_post,
    refine_image_prompt,
    generate_image,
)
from .agent_tools import (
    agent_search,
    agent_post_generator,
    agent_brainstorm,
    agent_generate_campaign_prompt,
    POST_BUILDER_SYSTEM_PROMPT,
    POST_BUILDER_FUNCTION_TOOL,
)
from .url_content import (
    generate_from_url,
    generate_from_url_stream,
    post_url_content,
)
from .chat_stream import (
    chat_post_builder_stream,
    parse_generated_posts,
    generate_image_for_post_builder,
    generate_video_for_post,
    generate_media_for_post_builder,
    ORCHESTRATOR_SYSTEM_PROMPT,
    ORCHESTRATOR_TOOLS,
)
from .video_posting import (
    upload_video_to_twitter,
    upload_video_to_linkedin,
    upload_video_to_youtube,
    post_video_to_platforms,
    refresh_youtube_token,
)

__all__ = [
    # Config
    'client',
    'LLM_MODEL',
    'LLM_FALLBACK',
    'IMAGE_MODEL',
    'QUIC_ERROR_PATTERNS',
    'TOPIC_STOPWORDS',
    # Utils
    'is_network_error',
    'emit_agent_event',
    'strip_markdown_formatting',
    # URL Utils
    'resolve_redirect_url',
    'clean_url_text',
    'is_youtube_url',
    'extract_html_title',
    'url_seems_relevant_to_topic',
    'is_soft_404',
    'validate_url',
    'validate_and_select_url',
    # Exceptions
    'AgentError',
    'SearchError',
    'NetworkError',
    'URLValidationError',
    'GenerationError',
    # Intent Parser
    'agent_intent_parser',
    'INTENT_GENERATE_POSTS',
    'INTENT_BRAINSTORM',
    'INTENT_GENERATE_CAMPAIGN',
    'INTENT_GREETING',
    'INTENT_CLARIFY',
    'DEFAULT_PERSONA',
    'DEFAULT_VISUAL_STYLE',
    'is_greeting_intent',
    'is_clarify_intent',
    'is_generate_posts_intent',
    'is_brainstorm_intent',
    'is_campaign_intent',
    # Persona
    'analyze_user_prompt',
    'create_fallback_persona',
    # Social Media
    'post_to_twitter',
    'post_to_linkedin',
    # Post Generator
    'generate_x_post',
    'generate_linkedin_post',
    # Search
    'search_trending_topics',
    'select_single_topic',
    # Content Generator
    'generate_post_draft',
    'critique_and_refine_post',
    'validate_content_matches_vision',
    'extract_topics_from_post',
    'refine_image_prompt',
    'generate_image',
    # Agent Tools
    'agent_search',
    'agent_post_generator',
    'agent_brainstorm',
    'agent_generate_campaign_prompt',
    'POST_BUILDER_SYSTEM_PROMPT',
    'POST_BUILDER_FUNCTION_TOOL',
    # URL Content
    'generate_from_url',
    'generate_from_url_stream',
    'post_url_content',
    # Chat Stream
    'chat_post_builder_stream',
    'parse_generated_posts',
    'generate_image_for_post_builder',
    'generate_video_for_post',
    'generate_media_for_post_builder',
    'ORCHESTRATOR_SYSTEM_PROMPT',
    'ORCHESTRATOR_TOOLS',
    # Video Posting
    'upload_video_to_twitter',
    'upload_video_to_linkedin',
    'upload_video_to_youtube',
    'post_video_to_platforms',
    'refresh_youtube_token',
]
