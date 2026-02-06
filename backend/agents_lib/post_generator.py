"""Post generation for X/Twitter and LinkedIn platforms."""
import time
from typing import Tuple, Optional
from google.genai import types

from .config import client, LLM_MODEL
from .utils import strip_markdown_formatting, sanitize_for_linkedin
from .linkedin_mentions import apply_linkedin_mentions
from logger_config import agent_logger as logger


def generate_x_post(
    search_context: str,
    refined_persona: str,
    user_prompt: str,
    source_url: Optional[str],
    recent_topics: list,
    max_retries: int = 3
) -> Tuple[str, str]:
    """
    Generate X/Twitter-specific post (280 char limit, casual, punchy).
    CRITICAL: Must follow user's exact creative format/vision.

    URLs are always included when available (grounded search provides credible sources).

    Args:
        search_context: Context from search results
        refined_persona: The persona to write as
        user_prompt: User's original creative direction
        source_url: Source URL to include
        recent_topics: List of recently covered topics to avoid
        max_retries: Number of retry attempts before failing (default: 3)

    Returns:
        Tuple of (post_text, source_url)

    Raises:
        Exception: If all retries fail - caller should handle by skipping post
    """
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                logger.info(f"Retry attempt {attempt + 1}/{max_retries} for X post generation")
                time.sleep(2 ** attempt)  # Exponential backoff: 2s, 4s, 8s

            post_text = _generate_x_post_text(
                search_context,
                refined_persona,
                user_prompt,
                source_url,
                recent_topics
            )

            # Always add URL if provided and not already in post
            if source_url and source_url not in post_text:
                post_text = f"{post_text}\n\n{source_url}"
                logger.info(f"X post with URL (total: {len(post_text)} chars)")

            return post_text, source_url

        except Exception as e:
            logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for X post: {e}")
            if attempt == max_retries - 1:
                logger.error(f"All {max_retries} attempts failed for X post generation", exc_info=True)
                raise


def _generate_x_post_text(
    search_context: str,
    refined_persona: str,
    user_prompt: str,
    source_url: Optional[str],
    recent_topics: list
) -> str:
    """Generate the X post text using LLM."""
    max_text_length = 230 if source_url else 280

    avoidance_text = ""
    if recent_topics:
        topics_str = ", ".join(recent_topics[:5])
        avoidance_text = f"\n- Explore a FRESH angle - we recently covered: {topics_str}"

    prompt = f"""
USER'S CREATIVE VISION: {user_prompt}
This describes the IMAGE/VISUAL FORMAT that will accompany the post.

TOPIC CONTEXT (pick ONE specific concept to focus on):
{search_context}

YOUR TASK: Write ONE polished, publication-ready X/Twitter post about a SINGLE topic from the context above.

STRUCTURE YOUR POST (bullet format preferred for higher engagement):
1. Hook line - grabs attention (question or bold statement)
2. 2-3 bullet points with key insights (use • or - symbols)
3. Call-to-action or hashtags

FORMATTING RULES (data shows bullets get 79% higher impressions):
- PREFER bullet points over prose paragraphs
- Keep sentences SHORT (under 12 words each)
- Front-load the value - put the hook FIRST
- Each bullet = one clear insight

CRITICAL RULES:
- Pick ONE specific topic/concept - do NOT list multiple options
- Write FROM the persona's voice/tone: {refined_persona}
- DO NOT describe the image - the image will accompany this text
- DO NOT write an image generation prompt
- DO NOT write "Option 1/2/3" or multiple alternatives

HOOK PATTERNS THAT WORK:
- "Ever wondered why...?"
- "Here's what most people get wrong about..."
- "X just changed everything. Here's why:"
- Direct statement + supporting bullets

QUALITY CHECK (self-review before outputting):
- Does it use bullet points for scannability?
- Is each sentence under 12 words?
- Does it have a clear hook FIRST?
- Is it under {max_text_length} characters?
- Does it match the persona's voice?

X/TWITTER REQUIREMENTS:
- MAXIMUM {max_text_length} characters - this is STRICT
- Engaging, punchy tone with a clear hook
- Can use 1-2 relevant hashtags or emojis
- DO NOT include URLs - we'll add that separately{avoidance_text}

Write ONLY the final post text, nothing else.
"""

    response = client.models.generate_content(
        model=LLM_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.8,
            thinking_config=types.ThinkingConfig(
                thinking_level="HIGH"
            )
        )
    )

    return response.text.strip()


def generate_linkedin_post(
    search_context: str,
    refined_persona: str,
    user_prompt: str,
    source_url: Optional[str],
    recent_topics: list,
    max_retries: int = 3
) -> str:
    """
    Generate LinkedIn-specific post (longer form, professional, detailed).
    CRITICAL: Must follow user's exact creative format/vision adapted for professional audience.

    URLs are always included when available (grounded search provides credible sources).

    Args:
        search_context: Context from search results
        refined_persona: The persona to write as
        user_prompt: User's original creative direction
        source_url: Source URL to include
        recent_topics: List of recently covered topics to avoid
        max_retries: Number of retry attempts before failing (default: 3)

    Returns:
        Complete LinkedIn post text with context and insights

    Raises:
        Exception: If all retries fail - caller should handle by skipping post
    """
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                logger.info(f"Retry attempt {attempt + 1}/{max_retries} for LinkedIn post generation")
                time.sleep(2 ** attempt)  # Exponential backoff: 2s, 4s, 8s

            post_text = _generate_linkedin_post_text(
                search_context,
                refined_persona,
                user_prompt,
                recent_topics
            )

            # Strip any markdown formatting (LinkedIn doesn't support it)
            post_text = strip_markdown_formatting(post_text)

            # Replace pipe characters that cause LinkedIn truncation
            post_text = sanitize_for_linkedin(post_text)

            # Apply LinkedIn company mentions (converts company names to mention format)
            post_text = apply_linkedin_mentions(post_text)

            # Always add URL if provided and not already in post
            if source_url and source_url not in post_text:
                post_text = f"{post_text}\n\n{source_url}"
                logger.info(f"Added source URL to LinkedIn post")

            logger.info(f"LinkedIn post ({len(post_text)} chars)")

            return post_text

        except Exception as e:
            logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for LinkedIn post: {e}")
            if attempt == max_retries - 1:
                logger.error(f"All {max_retries} attempts failed for LinkedIn post generation", exc_info=True)
                raise


def _generate_linkedin_post_text(
    search_context: str,
    refined_persona: str,
    user_prompt: str,
    recent_topics: list
) -> str:
    """Generate the LinkedIn post text using LLM."""
    avoidance_text = ""
    if recent_topics:
        topics_str = ", ".join(recent_topics[:5])
        avoidance_text = f"\n- Explore a FRESH angle - we recently covered: {topics_str}"

    prompt = f"""
CONTEXT: The user's creative vision is: {user_prompt}
This describes the IMAGE/VISUAL FORMAT that will accompany the post.

Your task: Write a polished, publication-ready PROFESSIONAL LINKEDIN POST about this topic: {search_context}

CRITICAL INSTRUCTIONS:
- DO NOT write an image generation prompt or detailed description of the visual
- DO write a thoughtful LinkedIn post ABOUT the technical topic
- Write FROM the persona's voice: {refined_persona}
- You CAN mention that there's a unique visual/tutorial format, but keep it brief and focus on the VALUE/INSIGHTS

STRUCTURE FOR ENGAGEMENT:
1. Opening hook (1-2 sentences max) - pose a question or bold statement
2. Key insights - use bullet points or short paragraphs
3. Takeaway - what should the reader do or think differently?
4. Hashtags (2-3 max)

FORMATTING GUIDANCE:
- Keep sentences SHORT and punchy (under 15 words ideal)
- Use line breaks between ideas for scannability
- Bullet points work well for listing insights
- Front-load the value - hook FIRST, context SECOND

HOOK PATTERNS THAT WORK:
- "Ever wondered why...?"
- "Here's what most engineers miss about..."
- "I used to think X. Then I learned Y."
- Problem statement + "Here's how to fix it:"

EXAMPLES OF WHAT TO DO:
✓ "Ever dealt with messy traces clogging your OTEL collector?

Here's why proper trace management matters:
• Bad traces waste storage and compute
• They obscure real issues in your data
• Early filtering saves 40%+ on costs

Key takeaway: configure your BadTrace filters early! #OpenTelemetry"

EXAMPLES OF WHAT NOT TO DO:
✗ "Check out this anime sketch showing a girl pointing at a whiteboard..."
✗ "New diagram series featuring a character teaching..."
✗ Long, dense paragraphs without breaks

QUALITY CHECK (self-review before outputting):
- Is this a professional post about the TOPIC (not an image description)?
- Does it have a clear hook in the first 1-2 sentences?
- Is it scannable (short sentences, line breaks, bullets)?
- Is it free of markdown formatting (no **bold**, __italics__, etc.)?

LINKEDIN REQUIREMENTS:
- 1-3 short paragraphs or hook + bullets
- Professional, insightful tone
- Provide VALUE to readers - what will they learn?
- Engage the professional community
- Can use relevant hashtags (2-3 max)
- Use plain text only with emojis if appropriate - NO markdown formatting
- DO NOT include URLs - we'll add that separately{avoidance_text}

Write ONLY the final post text in plain text format, nothing else.
"""

    response = client.models.generate_content(
        model=LLM_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.7,
            thinking_config=types.ThinkingConfig(
                thinking_level="HIGH"
            )
        )
    )

    return response.text.strip()
