"""Content generation helpers for drafting, critiquing, and validating posts."""
import json
from typing import Tuple, Optional


from xai_client import chat, generate_image as xai_generate_image
from logger_config import agent_logger as logger


def generate_post_draft(search_context: str, refined_persona: str, user_prompt: str, source_url: Optional[str] = None, recent_topics: list = None) -> str:
    """
    Generate a social media post draft based on search context and persona.

    Args:
        search_context: Context from trending search results
        refined_persona: The persona description
        user_prompt: The user's campaign prompt
        source_url: Optional URL to include in the post
        recent_topics: List of specific topics covered in the last 2 weeks to avoid

    Returns:
        Post text (under 280 characters including URL)
    """
    try:
        # Account for URL in character count (Twitter counts URLs as ~23 chars)
        # Use 220 chars to be safe and leave room for the URL
        max_text_length = 220 if source_url else 280

        # Build avoidance instruction if we have recent topics
        avoidance_text = ""
        if recent_topics:
            topics_str = ", ".join(recent_topics[:5])  # Limit to first 5 for brevity
            avoidance_text = f"""
- Explore a FRESH angle - we recently covered: {topics_str}
"""

        draft_prompt = f"""
You are acting as this persona:
{refined_persona}

Based on this trending information:
{search_context}

Write a single social media post about {user_prompt}.

CRITICAL REQUIREMENTS:
- MAXIMUM {max_text_length} characters - this is STRICT, go shorter if needed
- Engaging and authentic to the persona
- Include relevant insights from the trending information
- Can include 1-2 relevant hashtags if appropriate
- Natural, conversational tone
- DO NOT include any URLs or links in your response
- Keep it concise and punchy{avoidance_text}

Write only the post text, nothing else.
"""

        response = chat(draft_prompt, temperature=0.8)

        post_text = response.text.strip()

        # Append URL if provided
        if source_url:
            post_text = f"{post_text} {source_url}"
            logger.info(f"Added source URL to post (total length: {len(post_text)} chars)")

        return post_text

    except Exception as e:
        logger.error(f"Error generating draft: {e}", exc_info=True)
        fallback = "Excited to share thoughts on this topic! #ai #automation"
        if source_url:
            fallback = f"{fallback} {source_url}"
        return fallback


def critique_and_refine_post(draft: str, refined_persona: str) -> str:
    """
    Critique the post draft and refine it if needed.

    Returns:
        Final refined post
    """
    try:
        critique_prompt = f"""
Review this social media post draft:
"{draft}"

Persona: {refined_persona}

Critique it for:
1. Engagement potential
2. Authenticity to persona
3. Safety (no controversial/harmful content)
4. Length (must be under 280 chars)

If the post has issues, rewrite it. Otherwise, return it unchanged.
Return only the final post text, nothing else.
"""

        response = chat(critique_prompt, temperature=0.7)

        return response.text.strip()

    except Exception as e:
        logger.error(f"Error critiquing post: {e}", exc_info=True)
        return draft


def validate_content_matches_vision(post_text: str, user_prompt: str, refined_persona: str) -> Tuple[bool, str]:
    """
    Validate that generated social media post text is appropriate.
    IMPORTANT: user_prompt describes the IMAGE format, not the post text format.

    Returns:
        Tuple of (is_valid, feedback) where feedback explains any issues
    """
    try:
        validation_prompt = f"""
You are a quality control agent validating SOCIAL MEDIA POST TEXT.

CRITICAL CONTEXT:
- User's Creative Vision: {user_prompt}
  This describes the IMAGE/VISUAL FORMAT that will accompany the post, NOT what the post text should look like.
- Persona: {refined_persona}
- Generated Post Text: "{post_text}"

Your task: Validate if this is GOOD SOCIAL MEDIA POST TEXT (not an image description).

CHECK FOR THESE ISSUES (mark as invalid if found):
1. Is it an image generation prompt? (e.g., "Anime sketch of...", "Drawing showing...", "Diagram with...")
2. Is it describing what's in the image instead of discussing the topic?
3. Is it boring/generic? (e.g., "Check out this post about...")

GOOD INDICATORS (mark as valid if present):
1. It's a normal social media post ABOUT a technical topic
2. It matches the persona's voice/tone
3. It's engaging and would work on social media
4. It can reference the visual format briefly, but focuses on the TOPIC

Respond in this exact JSON format:
{{
    "is_valid": true/false,
    "feedback": "Brief explanation"
}}
"""

        response = chat(validation_prompt, temperature=0.3, json_mode=True)

        result = json.loads(response.text)
        is_valid = result.get("is_valid", False)
        feedback = result.get("feedback", "No feedback provided")

        if is_valid:
            logger.debug(f"Content validation PASS: {feedback}")
        else:
            logger.warning(f"Content validation FAIL: {feedback}")

        return is_valid, feedback

    except Exception as e:
        logger.error(f"Error validating content: {e}", exc_info=True)
        return True, "Validation skipped due to error"


def extract_topics_from_post(post_text: str, user_prompt: str = "") -> list:
    """
    Extract specific, granular topics covered in the post.
    Topics are extracted in the context of the user's creative vision to maintain thematic consistency.

    Returns:
        List of 3-5 specific topic strings (e.g., ["OpenTelemetry distributed tracing", "Kubernetes HPA configuration"])
    """
    try:
        context_text = f"\n\nUser's Creative Vision: {user_prompt}" if user_prompt else ""

        extraction_prompt = f"""
Analyze this social media post and extract 3-5 SPECIFIC, GRANULAR topics or concepts it covers.

Post: "{post_text}"{context_text}

Be SPECIFIC - not broad categories. Examples:
- Good: "OpenTelemetry distributed tracing", "Kubernetes horizontal pod autoscaling", "React useEffect cleanup functions"
- Bad: "OpenTelemetry", "Kubernetes", "React"

Extract topics that are:
1. Specific technical concepts, features, or implementations mentioned
2. Consistent with the user's creative vision/format (don't extract the format itself, extract the technical content)
3. Granular enough to avoid repetition in future posts

Respond in this exact JSON format:
{{
    "topics": ["specific topic 1", "specific topic 2", "specific topic 3"]
}}
"""

        response = chat(extraction_prompt, temperature=0.3, json_mode=True)

        result = json.loads(response.text)
        topics = result.get("topics", [])
        logger.info(f"Extracted {len(topics)} topics: {topics}")
        return topics

    except Exception as e:
        logger.error(f"Error extracting topics: {e}", exc_info=True)
        return []


def refine_image_prompt(post_text: str, visual_style: str, user_prompt: str, topic_context: str = "") -> str:
    """
    STEP 1 (The Brain): Use the text reasoning model to deeply think about
    the best way to visualize the content and generate a refined, detailed prompt.

    This enables "thinking" before image generation since the image model
    doesn't support thinking_config.

    Args:
        post_text: The generated social media post content
        visual_style: The extracted visual style specification
        user_prompt: The original user prompt - provides crucial context about intent and purpose
        topic_context: The focused single-topic context - provides specific technical details to visualize
                      (This is the OUTPUT of select_single_topic, NOT raw search results)

    Returns:
        A refined, detailed image generation prompt
    """
    try:
        # Build topic context section if available
        topic_context_section = ""
        if topic_context:
            topic_context_section = f"""
TOPIC DETAILS (use this to understand WHAT specific concept/feature to visualize):
{topic_context[:1500]}

"""

        refining_prompt = f"""
You are an expert art director specializing in social media visuals.

ORIGINAL USER INTENT (important context for understanding the purpose): {user_prompt}

VISUAL STYLE SPECIFICATION (MUST FOLLOW EXACTLY): {visual_style}
{topic_context_section}
SOCIAL MEDIA POST CONTENT: "{post_text}"

Your task:
1. Think deeply about the best way to visualize this post while STRICTLY adhering to the visual style specification
2. Consider the ORIGINAL USER INTENT - this tells you the PURPOSE of the content (e.g., educational, promotional, entertainment)
3. Use the TOPIC DETAILS to understand the specific technical concept being discussed - the image should clearly relate to THIS topic
4. Consider lighting, composition, color palette, mood, and focal points
5. If the style specifies specific elements (e.g., "anime girl", "simple drawn style", "kawaii aesthetic"), these are NON-NEGOTIABLE
6. Plan how to make the image eye-catching and shareable on social media
7. Consider aspect ratio (1:1 works well for most social platforms)

OUTPUT: Write ONLY the final, detailed prompt for the image generator.
- Be specific about visual elements, positioning, colors, and mood
- Include technical art direction (lighting, perspective, style)
- Make sure the image clearly relates to the specific topic from TOPIC DETAILS
- Keep the prompt focused and actionable for image generation
- DO NOT include any explanations or meta-commentary, just the prompt itself
"""

        logger.info("🧠 Thinking about image composition...")

        response = chat(refining_prompt, temperature=0.7)

        refined_prompt = response.text.strip()
        logger.info(f"📝 Refined image prompt: {refined_prompt[:200]}...")

        return refined_prompt

    except Exception as e:
        logger.error(f"Error refining image prompt: {e}", exc_info=True)
        # Fallback to basic prompt if reasoning fails
        return f"Create an image in this style: {visual_style}. Content: {post_text}"


def generate_image(post_text: str, visual_style: str, user_prompt: str, topic_context: str = "") -> Optional[bytes]:
    """
    Generate an image using a two-step "Think then Draw" workflow:

    STEP 1 (Brain/Reasoning): Uses grok-4.7 to analyze the request
    and generate a highly detailed, refined image prompt.

    STEP 2 (Artist/Generation): Uses grok-imagine-image-2.0 to execute the refined prompt.

    Args:
        post_text: The generated social media post content
        visual_style: The extracted visual style specification
        user_prompt: The original user prompt - provides crucial context about intent and purpose
        topic_context: The focused single-topic context - provides specific technical details to visualize
                      (This is the OUTPUT of select_single_topic, NOT raw search results)

    Returns:
        Image bytes or None if generation fails
    """
    try:
        # STEP 1: The Brain (Reasoning Phase)
        # Use text model with thinking to create a refined, detailed prompt
        refined_prompt = refine_image_prompt(post_text, visual_style, user_prompt, topic_context)

        # STEP 2: The Artist (Generation Phase)
        logger.info("🎨 Generating image with refined prompt...")

        image_bytes = xai_generate_image(refined_prompt)
        logger.info(f"Image generated successfully ({len(image_bytes)} bytes)")
        return image_bytes

    except Exception as e:
        logger.error(f"Error generating image: {e}", exc_info=True)
        return None
