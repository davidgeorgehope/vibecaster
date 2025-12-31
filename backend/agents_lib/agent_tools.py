"""Agent tool functions for search, post generation, brainstorming, and campaigns."""
from google.genai import types

from .config import client, LLM_MODEL
from .utils import is_network_error
from .search import search_trending_topics, select_single_topic
from logger_config import agent_logger as logger


def agent_search(query: str, persona_context: str = None) -> dict:
    """
    Agent that performs grounded search with optimized query.
    Uses existing search_trending_topics but with the OPTIMIZED query.
    """
    try:
        logger.info(f"Search agent: searching for '{query}'")

        # Use existing search function with optimized query
        search_context, urls, html_content = search_trending_topics(
            user_prompt=query,  # Already optimized by intent parser
            refined_persona=persona_context or "informative content finder for social media posts",
            recent_topics=[],
            validate_urls=True
        )

        focused_context = search_context
        selected_url = urls[0] if urls else None

        # Try to focus on a single topic
        if urls:
            try:
                focused_context, selected_url, _ = select_single_topic(
                    search_context, urls, query
                )
            except Exception as e:
                logger.warning(f"select_single_topic failed: {e}")

        return {
            "content": focused_context,
            "urls": urls,
            "selected_url": selected_url,
            "success": True
        }
    except Exception as e:
        error_type = "network" if is_network_error(e) else "general"
        logger.error(f"Search agent error ({error_type}): {e}")
        return {
            "content": f"Topic: {query}",
            "urls": [],
            "selected_url": None,
            "success": False,
            "error": str(e),
            "error_type": error_type,
            "retryable": error_type == "network"
        }


def agent_post_generator(persona: str, topic: str, content: str, visual_style: str, source_url: str = None) -> dict:
    """
    Agent that generates posts using persona + real content.
    """
    POST_GEN_PROMPT = f"""Generate social media posts.

PERSONA (your voice/character): {persona}
TOPIC: {topic}
VISUAL STYLE FOR IMAGES: {visual_style}

REAL CONTENT TO USE (include these facts in your posts):
{content[:4000]}

SOURCE URL: {source_url or 'Not specified'}

Create posts that present the REAL facts above IN THE PERSONA'S VOICE.
- The persona is HOW you speak (character, tone, style)
- The content is WHAT you say (real facts, news, information)

Call generate_posts() with the posts you create."""

    try:
        response = client.models.generate_content(
            model=LLM_MODEL,
            contents=POST_GEN_PROMPT,
            config=types.GenerateContentConfig(
                temperature=0.9,
                tools=[POST_BUILDER_FUNCTION_TOOL]
            )
        )

        # Extract function call result
        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'function_call') and part.function_call:
                    args = dict(part.function_call.args) if part.function_call.args else {}
                    return {
                        "x_post": args.get("x_post", ""),
                        "linkedin_post": args.get("linkedin_post", ""),
                        "persona": args.get("persona", persona),
                        "visual_style": args.get("visual_style", visual_style),
                        "source_url": args.get("source_url", source_url or ""),
                        "success": True
                    }

        return {"success": False, "error": "No posts generated"}
    except Exception as e:
        logger.error(f"Post generator error: {e}")
        return {"success": False, "error": str(e)}


def agent_brainstorm(topic_area: str) -> dict:
    """
    Agent that explores topic ideas without generating posts.
    Uses Google Search grounding to find trends.
    """
    BRAINSTORM_PROMPT = f"""Explore content ideas about: {topic_area}

Search for:
- Trending topics and recent news
- Interesting angles and perspectives
- What people are discussing

Return a helpful list of potential post topics with brief descriptions.
Format as a bulleted list that's easy to read."""

    try:
        response = client.models.generate_content(
            model=LLM_MODEL,
            contents=BRAINSTORM_PROMPT,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.7
            )
        )

        return {
            "suggestions": response.text,
            "success": True
        }
    except Exception as e:
        logger.error(f"Brainstorm agent error: {e}")
        return {
            "suggestions": f"I encountered an issue exploring {topic_area}. Try being more specific.",
            "success": False
        }


def agent_generate_campaign_prompt(persona: str, topic: str, visual_style: str, history: list = None) -> dict:
    """
    Agent that generates a structured campaign prompt/brief based on
    conversation context. This can be used to populate the Campaign tab.
    """
    CAMPAIGN_PROMPT_GENERATOR = """Generate a detailed campaign prompt/brief for a social media content campaign.

Based on the conversation context, create a structured campaign document that includes:

1. CAMPAIGN CONCEPT: A one-sentence summary of the campaign concept
2. PERSONA/VOICE: Who will be "teaching" or presenting the content
3. VISUAL STYLE: Detailed description of how content should be visualized
4. CONTENT FOCUS: What topics to cover, what to avoid
5. EXAMPLE PROMPT: A ready-to-use prompt for the Campaign tab

Format the output as a campaign brief that could be directly pasted into a campaign configuration.
Make it detailed and actionable. Include specifics about tone, style, and content guidelines.

The campaign prompt should be in a format like this example:
---
"I want to talk about [TOPIC] concepts and teach them with [PERSONA]:
Week commencing date: [suggest a date]
Create [VISUAL_STYLE] tutorials on [TOPIC] topics taught by [PERSONA].
CONTENT FOCUS: Teach concepts and best practices, not release announcements. Explain HOW things work and WHY they matter.
Include links to relevant documentation where appropriate."
---

Return ONLY the campaign brief text, formatted nicely with clear sections."""

    try:
        # Build context from history
        context_summary = ""
        if history:
            context_summary = "Recent conversation:\n"
            for msg in history[-10:]:
                role = msg.get("role", "user")
                content = msg.get("content", "")[:300]
                context_summary += f"  {role}: {content}\n"

        prompt = f"""{context_summary}

Current context:
- Persona: {persona}
- Topic: {topic}
- Visual Style: {visual_style}

Generate a detailed campaign prompt for this concept."""

        response = client.models.generate_content(
            model=LLM_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=CAMPAIGN_PROMPT_GENERATOR,
                temperature=0.7
            )
        )

        return {
            "campaign_prompt": response.text,
            "persona": persona,
            "topic": topic,
            "visual_style": visual_style,
            "success": True
        }
    except Exception as e:
        logger.error(f"Campaign prompt generator error: {e}")
        return {
            "campaign_prompt": f"I had trouble generating a campaign prompt. The concept is: {persona} explaining {topic}.",
            "success": False
        }


# ===== POST BUILDER CONSTANTS =====

POST_BUILDER_SYSTEM_PROMPT = """You are a social media campaign assistant. Generate engaging posts based on REAL content that has been searched for you.

UNDERSTAND CREATIVE PERSONAS:
When users describe a creative format like "mario and luigi explain X" or "anime girl teaching Y", this is their PERSONA/VOICE.
- The persona defines HOW to present content (characters, style, tone, voice)
- Preserve the persona EXACTLY in the posts you generate

YOUR TASK:
You will receive:
1. The user's original request (with their persona/topic idea)
2. REAL searched content about the topic (already fetched for you)

You must:
1. Call generate_posts() to create posts that present the REAL content IN THE PERSONA'S VOICE
2. Include a visual_style that describes how to visualize the persona for image generation

Example:
- User says: "mario and luigi explain kubernetes"
- Content: [Real article about Kubernetes 1.32 release...]
- You call generate_posts with:
  - persona: "Mario and Luigi characters, playful Italian-American voice"
  - x_post: "Mama mia! 🍄 Kubernetes 1.32 just dropped..." (using REAL facts from content)
  - linkedin_post: "It's-a me, Mario! Let me and my brother Luigi tell you about..." (using REAL facts)
  - visual_style: "Mario and Luigi cartoon characters in Nintendo pixel art style, standing at a whiteboard, explaining Kubernetes concepts, video game aesthetic"
  - source_url: The URL from the content

IMPORTANT: Use ONLY facts from the provided content. The visual_style should capture how to DRAW the persona."""

# Tool definitions for post builder - just function declarations
# Google Search grounding is added separately when needed
POST_BUILDER_FUNCTION_TOOL = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="search_and_fetch",
            description="Search for current content about a topic and fetch article content. Call this FIRST before generating posts to get real, timely information.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "topic": types.Schema(
                        type="STRING",
                        description="The topic to search for (e.g., 'kubernetes best practices', 'observability trends', 'AI automation')"
                    ),
                    "persona_context": types.Schema(
                        type="STRING",
                        description="Brief description of the creative persona/voice to help find relevant content"
                    )
                },
                required=["topic"]
            )
        ),
        types.FunctionDeclaration(
            name="generate_posts",
            description="Generate social media posts combining the persona with fetched content. Call this AFTER search_and_fetch.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "persona": types.Schema(
                        type="STRING",
                        description="The creative persona/voice (e.g., 'Mario and Luigi characters with Italian-American flair')"
                    ),
                    "x_post": types.Schema(
                        type="STRING",
                        description="The X/Twitter post (under 250 chars, in the persona's voice)"
                    ),
                    "linkedin_post": types.Schema(
                        type="STRING",
                        description="The LinkedIn post (1-3 paragraphs, in the persona's voice)"
                    ),
                    "source_url": types.Schema(
                        type="STRING",
                        description="The source URL for the content"
                    ),
                    "visual_style": types.Schema(
                        type="STRING",
                        description="Visual style for image generation that captures the persona (e.g., 'Mario and Luigi cartoon characters in Nintendo pixel art style, video game aesthetic, standing at whiteboard')"
                    )
                },
                required=["persona", "x_post", "linkedin_post", "visual_style"]
            )
        ),
        types.FunctionDeclaration(
            name="create_campaign_prompt",
            description="Generate a campaign configuration that can be used to set up automated posting. Call this when user wants to create a campaign.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "campaign_prompt": types.Schema(
                        type="STRING",
                        description="The full campaign prompt describing persona, topics, and style"
                    ),
                    "refined_persona": types.Schema(
                        type="STRING",
                        description="Detailed persona description for post generation"
                    ),
                    "visual_style": types.Schema(
                        type="STRING",
                        description="Visual/image style description"
                    )
                },
                required=["campaign_prompt", "refined_persona", "visual_style"]
            )
        )
    ]
)
