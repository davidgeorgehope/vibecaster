"""Intent parsing agent for analyzing user messages."""
import json
from typing import Optional
from google.genai import types

from .config import client, LLM_MODEL
from logger_config import agent_logger as logger


# Intent types
INTENT_GENERATE_POSTS = "generate_posts"
INTENT_BRAINSTORM = "brainstorm"
INTENT_GENERATE_CAMPAIGN = "generate_campaign_prompt"
INTENT_GREETING = "greeting"
INTENT_CLARIFY = "clarify"

# Default values
DEFAULT_PERSONA = "professional thought leader"
DEFAULT_VISUAL_STYLE = "professional, modern, clean design"

INTENT_PARSER_PROMPT = """Analyze this social media post request and extract structured information.

Return a JSON object with:
1. "intent": One of:
   - "generate_posts" - user wants to create social media posts
   - "brainstorm" - user wants to explore ideas without generating
   - "generate_campaign_prompt" - user wants to create a campaign prompt/brief based on the current conversation context
   - "greeting" - user is just saying hello
   - "clarify" - request is unclear, need more info

IMPORTANT: If user says things like "generate a campaign prompt", "create a campaign brief", "make a campaign for this",
"campaign prompt for this concept" - the intent is "generate_campaign_prompt". This is DIFFERENT from "generate_posts".

2. "persona": The creative voice/character if specified
   - Examples: "Mario and Luigi video game characters", "Gordon Ramsay chef", "anime teacher"
   - If no persona, use "professional thought leader"

3. "topic": The ACTUAL subject matter to search for
   - CRITICAL: Extract ONLY the topic, SEPARATE from persona
   - "mario and luigi explain kubernetes" → topic is "kubernetes"
   - "gordon ramsay talks about cloud computing" → topic is "cloud computing"

4. "search_query": Optimized Google search query
   - Should find recent, relevant content about the TOPIC
   - Do NOT include persona in search query
   - Add context like "2024", "best practices", "news" if appropriate
   - Example: "kubernetes container orchestration news 2024"

5. "visual_style": How to visualize the persona for image generation
   - Describe the visual aesthetic
   - Example: "Mario and Luigi cartoon characters in Nintendo pixel art style, colorful, standing at a whiteboard"

Return ONLY valid JSON, no explanation."""


def agent_intent_parser(message: str, history: list = None) -> dict:
    """
    Agent that extracts structured intent from user message.
    Separates persona from topic and creates optimized search query.
    Uses the LLM to understand the user's intent.

    Args:
        message: The user's message to parse
        history: Optional conversation history

    Returns:
        Dictionary with keys: intent, persona, topic, search_query, visual_style
    """
    try:
        # Build context including history
        context_parts = []
        if history:
            context_parts.append("Previous conversation:")
            for msg in history[-6:]:  # Last 3 exchanges
                role = msg.get("role", "user")
                content = msg.get("content", "")[:500]
                context_parts.append(f"  {role}: {content}")
            context_parts.append("")
        context_parts.append(f"Current user message: {message}")
        full_context = "\n".join(context_parts)

        response = client.models.generate_content(
            model=LLM_MODEL,
            contents=full_context,
            config=types.GenerateContentConfig(
                system_instruction=INTENT_PARSER_PROMPT,
                temperature=0.2,
                response_mime_type="application/json"
            )
        )
        result = json.loads(response.text)
        logger.info(f"Intent parser result: {result}")
        return result
    except Exception as e:
        logger.error(f"Intent parser error: {e}")
        # Fallback - treat as simple post request
        return {
            "intent": INTENT_GENERATE_POSTS,
            "persona": DEFAULT_PERSONA,
            "topic": message,
            "search_query": message,
            "visual_style": DEFAULT_VISUAL_STYLE
        }


def is_greeting_intent(intent_result: dict) -> bool:
    """Check if the parsed intent is a greeting."""
    return intent_result.get("intent") == INTENT_GREETING


def is_clarify_intent(intent_result: dict) -> bool:
    """Check if the parsed intent needs clarification."""
    return intent_result.get("intent") == INTENT_CLARIFY


def is_generate_posts_intent(intent_result: dict) -> bool:
    """Check if the parsed intent is to generate posts."""
    return intent_result.get("intent") == INTENT_GENERATE_POSTS


def is_brainstorm_intent(intent_result: dict) -> bool:
    """Check if the parsed intent is to brainstorm."""
    return intent_result.get("intent") == INTENT_BRAINSTORM


def is_campaign_intent(intent_result: dict) -> bool:
    """Check if the parsed intent is to generate a campaign prompt."""
    return intent_result.get("intent") == INTENT_GENERATE_CAMPAIGN
