"""Persona analysis for user prompts."""
import json
from typing import Tuple
from google.genai import types

from .config import client, LLM_MODEL
from logger_config import agent_logger as logger


PERSONA_ANALYSIS_PROMPT = """
Analyze this social media automation request and generate:

1. A REFINED PERSONA - A detailed system instruction that STRICTLY PRESERVES the user's exact creative vision, voice, tone, and specific requirements
2. A VISUAL STYLE - Art direction that EXACTLY follows the user's specified visual requirements

CRITICAL: If the user specifies a particular creative concept (e.g., "anime girl teaching", "stick figures explaining", "meme format"), you MUST preserve that exact concept in both outputs. DO NOT generalize or dilute their vision.

User Request: "{user_prompt}"

Respond in this exact JSON format:
{{
    "refined_persona": "Your detailed persona description that preserves ALL user requirements",
    "visual_style": "Your visual style description that EXACTLY matches user specifications"
}}
"""


def analyze_user_prompt(user_prompt: str) -> Tuple[str, str]:
    """
    Analyze user prompt to generate refined persona and visual style.
    CRITICAL: Preserves the user's exact creative vision and specific requirements.

    Args:
        user_prompt: The user's creative direction or campaign prompt

    Returns:
        Tuple of (refined_persona, visual_style)
    """
    try:
        analysis_prompt = PERSONA_ANALYSIS_PROMPT.format(user_prompt=user_prompt)

        response = client.models.generate_content(
            model=LLM_MODEL,
            contents=analysis_prompt,
            config=types.GenerateContentConfig(
                temperature=0.5,  # Lower temp to stay faithful to user input
                response_mime_type="application/json",
                thinking_config=types.ThinkingConfig(
                    thinking_level="HIGH"
                )
            )
        )

        result = response.text
        data = json.loads(result)

        return data.get("refined_persona", ""), data.get("visual_style", "")

    except Exception as e:
        logger.error(f"Error analyzing prompt: {e}", exc_info=True)
        # Fallback: preserve user's original prompt exactly
        return create_fallback_persona(user_prompt)


def create_fallback_persona(user_prompt: str) -> Tuple[str, str]:
    """
    Create fallback persona and visual style when analysis fails.
    Preserves the user's original prompt exactly.

    Args:
        user_prompt: The user's original prompt

    Returns:
        Tuple of (refined_persona, visual_style)
    """
    return (
        f"IMPORTANT: Follow this exact creative direction: {user_prompt}",
        f"Visual style as specified: {user_prompt}"
    )
