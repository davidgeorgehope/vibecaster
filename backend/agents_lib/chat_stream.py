"""Chat streaming functionality for Post Builder multi-agent system."""
import re
import json
import base64
from typing import Optional

from google.genai import types

from .config import client, LLM_MODEL
from .utils import is_network_error, emit_agent_event, strip_markdown_formatting
from .intent_parser import agent_intent_parser
from .agent_tools import agent_search, agent_post_generator, agent_brainstorm, agent_generate_campaign_prompt
from .content_generator import generate_image
from database import get_campaign
from logger_config import agent_logger as logger


# ===== POST BUILDER MULTI-AGENT SYSTEM =====

# Orchestrator system prompt - decides which agents to call
ORCHESTRATOR_SYSTEM_PROMPT = """You are a conversation orchestrator for a social media post builder.

Your job is to analyze the user's message and call the appropriate agents in the right order.

AVAILABLE AGENTS (call as tools):
1. call_intent_parser - ALWAYS call this first to understand the user's request
2. call_search_agent - Search for content about a topic (use OPTIMIZED query from intent parser)
3. call_post_generator - Generate X and LinkedIn posts using persona + content
4. call_brainstorm_agent - Explore topic ideas without generating posts
5. respond_to_user - Send a direct response (for greetings, clarifications)

WORKFLOW FOR POST GENERATION:
When user says something like "mario and luigi explain kubernetes":
1. Call call_intent_parser with the message
   - This extracts: persona="Mario and Luigi", topic="kubernetes", search_query="kubernetes best practices 2024"
2. Call call_search_agent with the OPTIMIZED search_query (NOT the raw message!)
3. Call call_post_generator with persona, topic, content, and visual_style

CRITICAL RULES:
- ALWAYS call call_intent_parser FIRST to understand the request
- When searching, use the search_query from intent parser, NOT the raw user message
- "mario and luigi explain observability" should search for "observability" not "mario luigi observability"
- The persona is HOW to present content, the topic is WHAT to search for
- If intent is "greeting", just call respond_to_user
- If intent is "brainstorm", call brainstorm_agent instead of search+generate

EXAMPLES:
- "mario and luigi explain kubernetes" → intent_parser → search("kubernetes best practices") → post_generator(persona="Mario/Luigi")
- "what's trending in AI?" → intent_parser → brainstorm_agent("AI trends")
- "hello" → intent_parser → respond_to_user("Hello! I can help...")
"""

# Orchestrator tools - the agents it can call
ORCHESTRATOR_TOOLS = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="call_intent_parser",
            description="ALWAYS call this FIRST. Analyzes user message to extract intent, persona, topic, and optimized search query.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "message": types.Schema(type="STRING", description="The user's message to analyze")
                },
                required=["message"]
            )
        ),
        types.FunctionDeclaration(
            name="call_search_agent",
            description="Search for content using an OPTIMIZED query (from intent parser). Do NOT pass the raw user message.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "query": types.Schema(type="STRING", description="Optimized search query from intent parser (e.g., 'kubernetes best practices 2024')"),
                    "persona_context": types.Schema(type="STRING", description="Brief persona description for context")
                },
                required=["query"]
            )
        ),
        types.FunctionDeclaration(
            name="call_post_generator",
            description="Generate social media posts using persona + searched content",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "persona": types.Schema(type="STRING", description="Creative persona/voice (e.g., 'Mario and Luigi characters')"),
                    "topic": types.Schema(type="STRING", description="The topic being discussed"),
                    "content": types.Schema(type="STRING", description="Real content from search to use in posts"),
                    "visual_style": types.Schema(type="STRING", description="How to visualize the persona for images"),
                    "source_url": types.Schema(type="STRING", description="Source URL for attribution")
                },
                required=["persona", "topic", "content", "visual_style"]
            )
        ),
        types.FunctionDeclaration(
            name="call_brainstorm_agent",
            description="Explore and suggest topic ideas without generating posts",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "topic_area": types.Schema(type="STRING", description="Area to brainstorm about")
                },
                required=["topic_area"]
            )
        ),
        types.FunctionDeclaration(
            name="respond_to_user",
            description="Send a direct response to user (for greetings, clarifications, errors)",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "message": types.Schema(type="STRING", description="Message to send to user")
                },
                required=["message"]
            )
        )
    ]
)


def chat_post_builder_stream(message: str, history: list[dict], user_id: int = None):
    """
    Stream a chat response using the multi-agent orchestrator pattern.

    Flow:
    1. Intent Parser - understand persona, topic, intent
    2. Route based on intent:
       - greeting → respond directly
       - brainstorm → brainstorm agent
       - generate_posts → search agent (optimized query) → post generator

    Args:
        message: The user's current message
        history: List of previous messages [{"role": "user"|"model", "content": "..."}]
        user_id: Optional user ID to load campaign persona

    Yields:
        Text chunks or JSON with tool results
    """
    try:
        # STEP 1: Parse intent to understand the request
        yield emit_agent_event("thinking", message="Analyzing your request...", step="intent_parsing")

        intent_data = agent_intent_parser(message, history)
        intent = intent_data.get("intent", "generate_posts")
        persona = intent_data.get("persona", "professional thought leader")
        topic = intent_data.get("topic", message)
        search_query = intent_data.get("search_query", topic)
        visual_style = intent_data.get("visual_style", "professional, modern design")

        logger.info(f"Intent: {intent}, Persona: {persona}, Topic: {topic}, Query: {search_query}")

        # Emit intent parsing result
        yield emit_agent_event("tool_result", tool="intent_parser", result={
            "intent": intent,
            "persona": persona,
            "topic": topic,
            "search_query": search_query,
            "visual_style": visual_style
        })

        # STEP 2: Route based on intent
        if intent == "greeting":
            yield emit_agent_event("text", content="Hello! I'm your Post Builder assistant. Tell me what you'd like to post about and I'll help create engaging content.\n\nFor example, try:\n- 'mario and luigi explain observability'\n- 'create a post about kubernetes best practices'\n- 'what's trending in AI?'")
            return

        if intent == "clarify":
            yield emit_agent_event("text", content="I'd love to help! Could you tell me more about what you'd like to post about?\n\nYou can specify:\n- A topic (e.g., 'kubernetes', 'observability', 'AI')\n- A creative persona (e.g., 'mario and luigi explain...')\n- Or ask 'what's trending in [topic]?' to brainstorm ideas")
            return

        if intent == "brainstorm":
            yield emit_agent_event("thinking", message=f"Exploring ideas about {topic}...", step="brainstorming")
            brainstorm_result = agent_brainstorm(topic)
            suggestions = brainstorm_result.get("suggestions", "No suggestions found.")
            yield emit_agent_event("tool_result", tool="brainstorm", result={"suggestions": suggestions})
            yield emit_agent_event("text", content=f"{suggestions}\n\nWant me to create posts about any of these? Just say which one!")
            return

        if intent == "generate_campaign_prompt":
            yield emit_agent_event("thinking", message="Generating campaign prompt from our conversation...", step="campaign_prompt")

            # Use context from conversation history to get the actual persona/topic
            # If current message triggered this intent, we need to look at history for context
            context_persona = persona
            context_topic = topic
            context_visual_style = visual_style

            # Look through history to find the most relevant persona/topic
            if history:
                for msg in reversed(history):
                    content = msg.get("content", "").lower()
                    # Look for messages that had actual content generation
                    if "mario" in content or "luigi" in content:
                        context_persona = "Mario and Luigi video game characters"
                    if "observability" in content:
                        context_topic = "observability"
                    # More sophisticated extraction from history
                    if msg.get("role") == "assistant" and "Persona:" in msg.get("content", ""):
                        # Try to parse persona from previous responses
                        lines = msg.get("content", "").split("\n")
                        for line in lines:
                            if "Persona:" in line:
                                parts = line.split("Persona:")
                                if len(parts) > 1:
                                    persona_part = parts[1].split("|")[0].strip()
                                    if persona_part and persona_part != "professional thought leader":
                                        context_persona = persona_part
                                        break

            campaign_result = agent_generate_campaign_prompt(
                persona=context_persona,
                topic=context_topic,
                visual_style=context_visual_style,
                history=history
            )

            if campaign_result.get("success"):
                yield emit_agent_event("tool_result", tool="campaign_prompt_generator", result={
                    "persona": context_persona,
                    "topic": context_topic
                })

                campaign_prompt = campaign_result.get("campaign_prompt", "")
                yield emit_agent_event("text", content=f"Here's a campaign prompt based on our conversation:\n\n---\n\n{campaign_prompt}\n\n---\n\nYou can copy this into your **Campaign** tab, or tell me to adjust anything!")
                yield emit_agent_event("complete", success=True, message="Campaign prompt generated!")
            else:
                yield emit_agent_event("error", message="Had trouble generating the campaign prompt.", retryable=True)
            return

        # STEP 3: For generate_posts intent - search with OPTIMIZED query
        yield emit_agent_event("searching", query=search_query, message=f"Searching for content about: {topic}")

        search_result = agent_search(search_query, persona)

        if search_result.get("success") and search_result.get("content"):
            selected_url = search_result.get("selected_url")
            urls = search_result.get("urls", [])
            yield emit_agent_event("search_results",
                success=True,
                selected_url=selected_url,
                urls=urls[:3],  # Limit for display
                content_preview=search_result.get("content", "")[:200]
            )
        else:
            # Provide specific feedback for different error types
            error_type = search_result.get("error_type", "unknown")
            yield emit_agent_event("search_results",
                success=False,
                error_type=error_type,
                message="Network issue during search" if error_type == "network" else "Search had issues"
            )

        # STEP 4: Generate posts using persona + searched content
        yield emit_agent_event("generating", message=f"Generating posts as {persona}...", step="post_generation")

        # Get campaign persona for additional context
        campaign_visual_style = None
        if user_id:
            campaign_data = get_campaign(user_id)
            if campaign_data and campaign_data.get("visual_style"):
                campaign_visual_style = campaign_data.get("visual_style")

        # Use visual_style from intent parser, or fallback to campaign style
        final_visual_style = visual_style
        if campaign_visual_style and visual_style == "professional, modern design":
            final_visual_style = campaign_visual_style

        post_result = agent_post_generator(
            persona=persona,
            topic=topic,
            content=search_result.get("content", f"Topic: {topic}"),
            visual_style=final_visual_style,
            source_url=search_result.get("selected_url")
        )

        if post_result.get("success"):
            # Return posts in the format frontend expects (keep base64 for backward compat)
            tool_result = {
                "type": "tool_call",
                "tool": "generate_posts",
                "x_post": post_result.get("x_post", ""),
                "linkedin_post": post_result.get("linkedin_post", ""),
                "source_url": post_result.get("source_url", ""),
                "persona": post_result.get("persona", persona),
                "visual_style": post_result.get("visual_style", final_visual_style)
            }
            encoded = base64.b64encode(json.dumps(tool_result).encode()).decode()
            yield f"__TOOL_CALL_B64__{encoded}__END_TOOL_CALL__"
            yield emit_agent_event("complete",
                success=True,
                message=f"Posts generated in the {persona} style!",
                source_url=search_result.get("selected_url")
            )
        else:
            error_msg = post_result.get('error', 'Unknown error')
            yield emit_agent_event("error",
                message=f"Had trouble generating posts: {error_msg}",
                error=error_msg,
                retryable=True
            )
            yield emit_agent_event("text", content="Try rephrasing your request or being more specific about the topic.")

    except Exception as e:
        logger.error(f"Error in chat_post_builder_stream: {e}", exc_info=True)
        error_type = "network" if is_network_error(e) else "general"
        yield emit_agent_event("error",
            message=f"Sorry, I encountered an error: {str(e)}",
            error=str(e),
            error_type=error_type,
            retryable=error_type == "network"
        )


def parse_generated_posts(response_text: str) -> dict:
    """
    Parse the LLM response to extract generated posts.

    Returns:
        Dict with 'x_post' and 'linkedin_post' keys (values may be None)
    """
    result = {"x_post": None, "linkedin_post": None}

    # Extract X post
    x_match = re.search(r'---X_POST_START---\s*(.*?)\s*---X_POST_END---', response_text, re.DOTALL)
    if x_match:
        result["x_post"] = x_match.group(1).strip()

    # Extract LinkedIn post
    li_match = re.search(r'---LINKEDIN_POST_START---\s*(.*?)\s*---LINKEDIN_POST_END---', response_text, re.DOTALL)
    if li_match:
        result["linkedin_post"] = strip_markdown_formatting(li_match.group(1).strip())

    return result


def generate_image_for_post_builder(post_text: str, visual_style: str = None, user_id: int = None) -> Optional[bytes]:
    """
    Generate an image for a post builder preview.

    Args:
        post_text: The post text to visualize
        visual_style: Optional visual style from the chat (e.g., "Mario and Luigi cartoon characters...")
        user_id: Optional user ID to load campaign visual style as fallback

    Returns:
        Image bytes or None
    """
    try:
        # Priority: 1. Provided visual_style, 2. Campaign visual_style, 3. Default
        style = visual_style
        user_prompt = post_text

        if not style and user_id:
            campaign = get_campaign(user_id)
            if campaign:
                if campaign.get("visual_style"):
                    style = campaign["visual_style"]
                if campaign.get("user_prompt"):
                    user_prompt = campaign["user_prompt"]

        if not style:
            style = "Modern, clean, professional social media graphic"

        logger.info(f"Generating image with visual_style: {style[:100]}...")
        return generate_image(post_text, style, user_prompt, post_text)

    except Exception as e:
        logger.error(f"Error generating image for post builder: {e}", exc_info=True)
        return None


def generate_video_for_post(
    post_text: str,
    visual_style: str = None,
    user_id: int = None,
    aspect_ratio: str = "16:9"
) -> Optional[bytes]:
    """
    Generate an 8-second video for a social media post using first-frame approach.

    Uses Veo 3.1 prompt refinement for better quality and realism.

    Args:
        post_text: The post text to visualize
        visual_style: Visual style for the image/video
        user_id: Optional user ID for campaign config fallback
        aspect_ratio: "16:9" (landscape) or "9:16" (portrait) - default 16:9

    Returns:
        Video bytes (MP4) or None
    """
    from video_generation import generate_video_from_image, refine_video_prompt

    try:
        # Step 1: Generate first frame image
        logger.info("Generating first frame for video...")
        image_bytes = generate_image_for_post_builder(post_text, visual_style, user_id)
        if not image_bytes:
            logger.error("Failed to generate first frame image")
            return None

        # Step 2: Create and refine motion prompt using Veo 3.1 best practices
        style_desc = visual_style or "professional, cinematic"
        base_prompt = f"Subtle cinematic motion, smooth camera movement. Style: {style_desc}. Content: {post_text[:300]}"

        # Refine prompt for Veo 3.1 with realism techniques
        logger.info("Refining video prompt for Veo 3.1...")
        refined_prompt = refine_video_prompt(
            video_prompt=base_prompt,
            scene_number=1,
            total_scenes=1,
            style="social_media",
            aspect_ratio=aspect_ratio
        )

        # Step 3: Generate video from first frame
        logger.info("Generating video from first frame...")
        video_bytes = generate_video_from_image(
            first_frame_bytes=image_bytes,
            video_prompt=refined_prompt,
            aspect_ratio=aspect_ratio
        )

        if video_bytes:
            logger.info(f"Video generated successfully ({len(video_bytes)} bytes)")
        else:
            logger.warning("Video generation returned no bytes")

        return video_bytes

    except Exception as e:
        logger.error(f"Error generating video for post: {e}", exc_info=True)
        return None


def generate_media_for_post_builder(
    post_text: str,
    visual_style: str = None,
    user_id: int = None,
    media_type: str = "image"
) -> tuple[Optional[bytes], str]:
    """
    Generate either an image or video for a post.

    Args:
        post_text: The post text to visualize
        visual_style: Visual style for the media
        user_id: Optional user ID for campaign config
        media_type: "image" (default) or "video"

    Returns:
        Tuple of (media_bytes, mime_type)
        mime_type is "image/png" or "video/mp4"
    """
    if media_type == "video":
        video_bytes = generate_video_for_post(post_text, visual_style, user_id)
        return (video_bytes, "video/mp4")
    else:
        image_bytes = generate_image_for_post_builder(post_text, visual_style, user_id)
        return (image_bytes, "image/png")
