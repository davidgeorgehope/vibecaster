"""Persona analysis for user prompts."""
import json
import re
from typing import Tuple, List
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


COMPETITOR_INFERENCE_PROMPT = """You are analyzing a social media campaign to identify companies that should NOT be mentioned in automated posts.

Campaign prompt: "{prompt}"

Author bio: "{bio}"

Based on the campaign topic and the author's affiliation, identify companies that are competitors or that should be excluded from automated posts. Consider:
- Direct competitors in the same space
- Companies the author's employer competes with
- Companies that would be inappropriate to promote given the author's affiliation

Return ONLY a JSON array of company names. If no competitors can be identified, return an empty array.
Example: ["Datadog", "Splunk", "New Relic"]
"""


SCHEDULE_INFERENCE_PROMPT = """Analyze this campaign prompt for any scheduling preferences.

Prompt: "{prompt}"

Look for phrases like:
- "daily", "every day" -> "0 9 * * *"
- "twice a day", "twice daily" -> "0 9,17 * * *" 
- "weekly", "once a week" -> "0 9 * * 1"
- "three times a week" -> "0 9 * * 1,3,5"
- "every morning" -> "0 8 * * *"
- "every evening" -> "0 18 * * *"
- Any specific time mentions

Return ONLY a JSON object:
{{
    "cron": "the cron expression",
    "description": "human readable description like 'Daily at 9 AM'"
}}

If no scheduling preference is detected, return:
{{
    "cron": "0 9 * * *",
    "description": "Daily at 9 AM"
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


def infer_excluded_companies(prompt: str, author_bio: str = "") -> List[str]:
    """
    Use Gemini to infer which companies should be excluded from posts
    based on the campaign prompt and author bio.
    
    Args:
        prompt: The campaign prompt
        author_bio: The author's bio/description
        
    Returns:
        List of company names to exclude
    """
    try:
        inference_prompt = COMPETITOR_INFERENCE_PROMPT.format(
            prompt=prompt,
            bio=author_bio or "No bio provided"
        )

        response = client.models.generate_content(
            model=LLM_MODEL,
            contents=inference_prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                response_mime_type="application/json",
            )
        )

        result = json.loads(response.text)
        
        # Handle both array and object responses
        if isinstance(result, list):
            return [str(c).strip() for c in result if c and str(c).strip()]
        elif isinstance(result, dict) and "companies" in result:
            return [str(c).strip() for c in result["companies"] if c and str(c).strip()]
        
        return []

    except Exception as e:
        logger.error(f"Error inferring excluded companies: {e}", exc_info=True)
        return []


def infer_schedule_from_prompt(prompt: str) -> Tuple[str, str]:
    """
    Parse natural language scheduling hints from the campaign prompt.
    
    Args:
        prompt: The campaign prompt
        
    Returns:
        Tuple of (cron_expression, human_readable_description)
    """
    # Quick regex checks for common patterns before hitting LLM
    prompt_lower = prompt.lower()
    
    # Fast path: common patterns
    if re.search(r'\btwice\s+(a\s+)?day\b|\btwice\s+daily\b', prompt_lower):
        return ("0 9,17 * * *", "Twice daily at 9 AM and 5 PM")
    if re.search(r'\bthree\s+times\s+(a\s+)?day\b', prompt_lower):
        return ("0 8,13,18 * * *", "Three times daily")
    if re.search(r'\bweekly\b|\bonce\s+(a\s+)?week\b', prompt_lower):
        return ("0 9 * * 1", "Weekly on Monday at 9 AM")
    if re.search(r'\bthree\s+times\s+(a\s+)?week\b', prompt_lower):
        return ("0 9 * * 1,3,5", "Three times a week")
    if re.search(r'\bevery\s+(other\s+)?day\b|\bdaily\b', prompt_lower):
        return ("0 9 * * *", "Daily at 9 AM")

    # If no obvious pattern, try LLM for complex cases
    try:
        # Only call LLM if there seem to be time-related words
        time_words = ['morning', 'evening', 'afternoon', 'night', 'noon',
                      'hourly', 'hour', 'times', 'schedule', 'post at',
                      'every', 'weekday', 'weekend', 'monday', 'tuesday',
                      'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        
        has_time_hint = any(word in prompt_lower for word in time_words)
        
        if not has_time_hint:
            return ("0 9 * * *", "Daily at 9 AM")

        inference_prompt = SCHEDULE_INFERENCE_PROMPT.format(prompt=prompt)
        
        response = client.models.generate_content(
            model=LLM_MODEL,
            contents=inference_prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
            )
        )

        result = json.loads(response.text)
        cron = result.get("cron", "0 9 * * *")
        description = result.get("description", "Daily at 9 AM")
        
        # Validate cron format (5 fields)
        parts = cron.split()
        if len(parts) != 5:
            return ("0 9 * * *", "Daily at 9 AM")
        
        return (cron, description)

    except Exception as e:
        logger.error(f"Error inferring schedule: {e}", exc_info=True)
        return ("0 9 * * *", "Daily at 9 AM")
