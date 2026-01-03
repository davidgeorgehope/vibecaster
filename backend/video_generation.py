"""
Video Generation Module - Multi-scene video generation with Veo 3.1

Provides functionality for:
- Script planning with LLM (scenes, narration, video prompts with dialogue)
- Scene image generation with character reference (Nano Banana Pro)
- Video generation from first frame (Veo 3.1)
- Video extension for scene continuity (Veo 3.1 extend)
- SSE streaming for progress updates

Note: Audio/dialogue is generated natively by Veo 3.1 when prompts include
quoted speech like: "The presenter says: \"Welcome to the tutorial.\""
"""

import os
import time
import json
import tempfile
from typing import Optional, Dict, Any, List, Generator
from io import BytesIO
from google import genai
from google.genai import types
from PIL import Image
from dotenv import load_dotenv
from logger_config import agent_logger as logger

load_dotenv()

# Initialize Google GenAI client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Models
LLM_MODEL = "gemini-3-pro-preview"
IMAGE_MODEL = "gemini-3-pro-image-preview"  # Nano Banana Pro
VIDEO_MODEL = "veo-3.1-generate-preview"

# Video generation settings
DEFAULT_VIDEO_DURATION = 8  # Veo generates 8-second clips
MAX_SCENES = 6  # Cap at 6 scenes (48 seconds) to control costs
POLL_INTERVAL = 10  # seconds between status checks

# Retry settings for quota errors
# Only 3 retries (7 min total) - if still failing, likely daily quota exhausted
MAX_QUOTA_RETRIES = 3
QUOTA_RETRY_DELAYS = [60, 120, 240]  # 1m, 2m, 4m backoff


def emit_event(event_type: str, **kwargs) -> str:
    """Create a JSON event string for SSE streaming."""
    event = {
        "type": event_type,
        "timestamp": time.time(),
        **kwargs
    }
    return json.dumps(event) + "\n"


def extract_characters_from_prompt(user_prompt: str) -> Dict[str, Any]:
    """
    Analyze user prompt and extract character definitions for reference generation.

    Uses LLM to identify recurring characters that would benefit from
    reference images to maintain visual consistency across scenes.

    Args:
        user_prompt: The full user prompt describing the video

    Returns:
        Dict with:
        - characters: List of character dicts (id, name, description, style, priority)
        - scene_characters: Map of scene number to character IDs
        - global_style: Overall visual style
        - needs_references: Whether reference generation is recommended
    """
    prompt = f"""Analyze this video prompt and extract character information for reference image generation.

User Prompt:
{user_prompt}

Return a JSON object with:

1. "characters": Array of up to 3 main recurring characters. Each character needs:
   - "id": lowercase identifier (e.g., "david", "elky")
   - "name": display name
   - "description": detailed visual description for image generation (appearance, clothing, distinctive features)
   - "style": one of "photorealistic", "storybook_human", "pixar_3d", "anime", "cartoon_2d"
   - "priority": 1-3 (1 = most important/screen time)

2. "scene_characters": Object mapping scene numbers to arrays of character IDs appearing in each scene.
   Example: {{"1": ["david", "elky"], "2": ["david", "loggy"]}}

3. "global_style": The overall visual style - one of "photorealistic", "storybook", "pixar", "anime", "cartoon"

4. "needs_references": boolean - true if there are 2+ distinct characters with detailed visual descriptions
   that would benefit from reference images for consistency. false for simple videos with no specific characters.

Rules:
- Include ALL distinct characters with clear visual descriptions (no limit)
- Each scene can use up to 3 character references, so prioritize appropriately
- Prioritize characters that appear in multiple scenes (lower priority number = more important)
- For mixed styles (e.g., realistic human + cartoon mascots), note each character's individual style
- If the prompt is simple (e.g., "explain quantum physics" with no character details), set needs_references: false

Return ONLY valid JSON, no other text."""

    try:
        logger.info("🔍 Analyzing prompt for character extraction...")

        response = client.models.generate_content(
            model=LLM_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                response_mime_type="application/json"
            )
        )

        if hasattr(response, 'text') and response.text:
            result = json.loads(response.text)

            characters = result.get('characters', [])
            needs_refs = result.get('needs_references', False)

            logger.info(f"Character analysis: {len(characters)} characters found, needs_references={needs_refs}")

            if characters:
                for char in characters:
                    logger.info(f"  - {char.get('name')} ({char.get('style')}): {char.get('description', '')[:50]}...")

            return result

        logger.warning("No text in character extraction response")
        return {"characters": [], "scene_characters": {}, "global_style": "storybook", "needs_references": False}

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse character extraction JSON: {e}")
        return {"characters": [], "scene_characters": {}, "global_style": "storybook", "needs_references": False}
    except Exception as e:
        logger.error(f"Error extracting characters: {e}", exc_info=True)
        return {"characters": [], "scene_characters": {}, "global_style": "storybook", "needs_references": False}


def plan_video_script(
    topic: str,
    style: str,
    target_duration: int,
    author_bio: Optional[Dict] = None,
    user_prompt: str = ""
) -> Dict[str, Any]:
    """
    Use LLM with thinking to plan a video script.

    Args:
        topic: The main topic/concept for the video
        style: Visual style ('educational', 'storybook', 'social_media')
        target_duration: Target video duration in seconds
        author_bio: Optional author bio for character reference
        user_prompt: Additional context from user

    Returns:
        Script with scenes, each containing narration and prompts
    """
    num_scenes = min(max(target_duration // DEFAULT_VIDEO_DURATION, 1), MAX_SCENES)

    style_instructions = {
        "educational": """Create an educational explainer video with a presenter.
- The presenter should speak directly to camera, explaining concepts clearly
- Include dialogue in the video_prompt using quotes: "The presenter says: \\"Let me explain...\\""
- Use a whiteboard, desk, or professional setting as the backdrop
- The tone should be informative, engaging, and conversational""",
        "storybook": """Create a narrative story with spoken narration and character dialogue.
- Include narrator voiceover in quotes: "The narrator says: \\"Once upon a time...\\""
- Characters should have dialogue: "The hero exclaims: \\"We must find the treasure!\\""
- Each scene advances the plot with engaging visuals and storytelling""",
        "social_media": """Create a short, attention-grabbing video with energetic voiceover.
- Include punchy voiceover in quotes: "A voice says: \\"You won't believe this!\\""
- Add sound effect descriptions for impact
- Make it visually striking and memorable with quick energy"""
    }

    character_context = ""
    if author_bio:
        character_context = f"""
Character Reference:
- Name: {author_bio.get('name', 'The Host')}
- Description: {author_bio.get('description', 'A friendly presenter')}
- Visual Style: {author_bio.get('style', 'real_person')}

Include this character appropriately in scenes if relevant to the content.
"""

    prompt = f"""You are a video script planner. Create a detailed script for a video about:

Topic: {topic}

Style: {style_instructions.get(style, style_instructions['educational'])}

Target Duration: ~{target_duration} seconds ({num_scenes} scenes of {DEFAULT_VIDEO_DURATION} seconds each)

{character_context}

{f'Additional Context: {user_prompt}' if user_prompt else ''}

Return a JSON object with this exact structure:
{{
    "title": "Video title",
    "summary": "One-sentence summary",
    "scenes": [
        {{
            "scene_number": 1,
            "narration": "What is spoken in this scene - the actual words (2-3 sentences)",
            "visual_description": "Detailed description of what appears visually",
            "image_prompt": "Detailed prompt for generating the first frame image (include style, lighting, composition)",
            "video_prompt": "Video prompt WITH DIALOGUE IN QUOTES. Example: The presenter gestures and says: \\"Welcome! Today we will learn about...\\" Camera slowly zooms in.",
            "include_character": true/false
        }}
    ],
    "total_scenes": {num_scenes},
    "estimated_duration": {num_scenes * DEFAULT_VIDEO_DURATION}
}}

CRITICAL REQUIREMENTS:
- The video_prompt MUST include spoken dialogue in quotes using this format:
  The presenter says: "Actual words they speak here."
- Use gender-neutral language (they/the presenter) - the reference image determines appearance
- Each scene is {DEFAULT_VIDEO_DURATION} seconds (scene 1) or 7 seconds (extensions)
- Scene 1 establishes the setting and character - subsequent scenes EXTEND from it
- Maintain visual and narrative continuity - scenes flow naturally into each other
- Keep dialogue natural and conversational, not robotic
- Include ambient sounds or effects where appropriate: "birds chirping", "keyboard clicking\""""

    try:
        logger.info(f"🎬 Planning video script for: {topic}")

        response = client.models.generate_content(
            model=LLM_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,
                thinking_config=types.ThinkingConfig(thinking_level="HIGH"),
                response_mime_type="application/json"
            )
        )

        script = json.loads(response.text)
        logger.info(f"Script planned: {script.get('title')} with {len(script.get('scenes', []))} scenes")
        return script

    except Exception as e:
        logger.error(f"Error planning script: {e}", exc_info=True)
        raise


def refine_video_prompt(
    video_prompt: str,
    scene_number: int,
    total_scenes: int,
    style: str,
    aspect_ratio: str = "16:9",
    full_context: str = ""
) -> str:
    """
    Use LLM with thinking to ENHANCE video prompts for Veo 3.1 best practices.

    CRITICAL: Preserves ALL character names, descriptions, story elements, and dialogue.
    Only ADDS cinematography and realism techniques - does NOT rewrite content.

    Args:
        video_prompt: Scene-specific video prompt
        scene_number: Current scene number (1-indexed)
        total_scenes: Total number of scenes
        style: Visual style (educational, storybook, social_media)
        aspect_ratio: "16:9" (landscape) or "9:16" (portrait)
        full_context: Original user prompt with character/setting descriptions for consistency

    Returns:
        Enhanced prompt with original content preserved
    """
    # Build aspect ratio guidance
    if aspect_ratio == "9:16":
        composition_note = "vertical 9:16 portrait framing for mobile"
    else:
        composition_note = "horizontal 16:9 widescreen framing"

    # Include full context if provided for character/setting consistency
    context_section = ""
    if full_context:
        context_section = f"""
FULL STORY CONTEXT (for character/setting consistency - MUST maintain these details):
{full_context[:2000]}

"""

    prompt = f"""You are enhancing a video prompt for Veo 3.1. Your job is to ADD technical details while PRESERVING the original content exactly.

{context_section}SCENE {scene_number} OF {total_scenes} - PROMPT TO ENHANCE:
{video_prompt}

## CRITICAL RULES - READ CAREFULLY:

1. **PRESERVE EVERYTHING**: Keep ALL character names, descriptions, appearances, dialogue, actions, and story elements EXACTLY as written. Do NOT generalize "David" to "a man" or "Elky" to "an elk". Keep specific details.

2. **ADD CINEMATOGRAPHY** (prepend to prompt):
   - ONE shot type: medium shot, wide shot, close-up, etc.
   - ONE camera movement: static, slow pan, gentle dolly, etc.
   - Framing: {composition_note}

3. **ADD REALISM** (append to prompt):
   - "natural skin texture, no plastic sheen"
   - "subtle film grain"
   - "specular highlights controlled"

4. **DIALOGUE FORMAT**: If dialogue exists, keep it as: Character says: "exact words"

5. **KEEP IT CONCISE**: The enhanced prompt should be 80-150 words max.

## WHAT TO OUTPUT:
[Cinematography: shot type, camera movement, framing] + [ORIGINAL scene content preserved exactly] + [Realism notes]

OUTPUT the enhanced prompt only. No explanations."""

    try:
        logger.info(f"🎬 Refining video prompt for scene {scene_number}...")

        response = client.models.generate_content(
            model=LLM_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.5,  # Lower temp for more consistent structure
                thinking_config=types.ThinkingConfig(thinking_level="HIGH")
            )
        )

        refined = response.text.strip()
        logger.info(f"📝 Refined prompt: {refined[:150]}...")
        return refined

    except Exception as e:
        logger.error(f"Error refining video prompt: {e}", exc_info=True)
        # Fallback to original prompt if refinement fails
        return video_prompt


def generate_scene_image(
    image_prompt: str,
    character_references: Optional[List[bytes]] = None,
    style: str = "real_person",
    aspect_ratio: str = "16:9"
) -> Optional[bytes]:
    """
    Generate a scene's first frame using Nano Banana Pro.

    Args:
        image_prompt: Detailed prompt for the image
        character_references: Optional list of reference image bytes for character consistency (max 3)
        style: Visual style for the image
        aspect_ratio: "16:9" (landscape) or "9:16" (portrait) for composition guidance

    Returns:
        Image bytes (PNG) or None if generation fails
    """
    style_suffix = {
        "real_person": ", photorealistic, cinematic lighting, 4K quality",
        "cartoon": ", cartoon style, vibrant colors, clean lines",
        "anime": ", anime style, detailed, expressive",
        "avatar": ", 3D avatar style, clean design",
        "3d_render": ", 3D rendered, cinematic lighting, high detail"
    }

    # Add aspect ratio guidance to prompt
    if aspect_ratio == "9:16":
        aspect_guidance = ", vertical portrait composition (9:16 aspect ratio), mobile-friendly framing"
    else:
        aspect_guidance = ", horizontal widescreen composition (16:9 aspect ratio), cinematic framing"

    full_prompt = image_prompt + style_suffix.get(style, style_suffix["real_person"]) + aspect_guidance

    try:
        logger.info(f"🖼️ Generating scene image...")

        contents = [full_prompt]

        # Add character references if provided (max 3)
        if character_references:
            refs_to_use = character_references[:3]
            if len(refs_to_use) == 1:
                contents.insert(0, "Use this character reference for consistency:")
            else:
                contents.insert(0, f"Use these {len(refs_to_use)} character references for consistency:")
            for i, ref in enumerate(refs_to_use):
                ref_image = Image.open(BytesIO(ref))
                contents.insert(1 + i, ref_image)
            logger.info(f"Including {len(refs_to_use)} character reference(s) in scene image")

        response = client.models.generate_content(
            model=IMAGE_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"]
            )
        )

        # Extract image from response
        if hasattr(response, 'candidates'):
            for candidate in response.candidates:
                if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                    for part in candidate.content.parts:
                        if hasattr(part, 'inline_data') and part.inline_data:
                            if hasattr(part.inline_data, 'data') and part.inline_data.data:
                                logger.info(f"Scene image generated ({len(part.inline_data.data)} bytes)")
                                return part.inline_data.data

                        if hasattr(part, 'as_image'):
                            try:
                                image = part.as_image()
                                if image and hasattr(image, 'save'):
                                    img_byte_arr = BytesIO()
                                    image.save(img_byte_arr, format='PNG')
                                    return img_byte_arr.getvalue()
                            except Exception as e:
                                logger.warning(f"as_image() method failed: {e}")

        logger.warning("No image found in response")
        return None

    except Exception as e:
        logger.error(f"Error generating scene image: {e}", exc_info=True)
        return None


def generate_video_from_image_stream(
    first_frame_bytes: bytes,
    video_prompt: str,
    aspect_ratio: str = "16:9"
):
    """
    Generate a video using Veo 3.1 with progress events (generator).

    Args:
        first_frame_bytes: PNG bytes of the first frame image
        video_prompt: The video generation prompt
        aspect_ratio: "16:9" (landscape) or "9:16" (portrait)

    Yields:
        ('progress', poll_count, max_polls) during polling
        ('complete', video_object, video_bytes) on success - returns both for extension chaining
        ('error', error_message) on failure

    NOTE: Use this for SSE streaming to keep Cloudflare connection alive.
    The video_object can be passed to generate_video_extension_stream() for continuity.
    """
    tmp_image_path = None
    tmp_video_path = None

    try:
        logger.info(f"🎥 Generating video from first frame...")

        # Save first frame to temp file
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_img:
            tmp_image_path = tmp_img.name
            tmp_img.write(first_frame_bytes)
            tmp_img.flush()

        first_frame = types.Image.from_file(location=tmp_image_path)

        # Start video generation with aspect ratio
        operation = client.models.generate_videos(
            model=VIDEO_MODEL,
            prompt=video_prompt,
            image=first_frame,
            config=types.GenerateVideosConfig(aspect_ratio=aspect_ratio)
        )

        # Poll until complete, yielding progress for SSE keepalive
        poll_count = 0
        max_polls = 60  # 10 minutes max
        while not operation.done and poll_count < max_polls:
            poll_count += 1
            logger.info(f"Video generation in progress... (poll {poll_count}/{max_polls})")

            # Yield progress event to keep SSE connection alive through Cloudflare
            yield ('progress', poll_count, max_polls)

            time.sleep(POLL_INTERVAL)
            operation = client.operations.get(operation)

        if not operation.done:
            logger.error(f"Video generation timed out after {poll_count * POLL_INTERVAL} seconds")
            yield ('error', 'Video generation timed out')
            return

        # Download the generated video
        if operation.response and operation.response.generated_videos:
            video = operation.response.generated_videos[0]

            if not hasattr(video, 'video') or video.video is None:
                logger.error("Veo API returned video object without video data")
                yield ('error', 'No video data in response')
                return

            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_vid:
                tmp_video_path = tmp_vid.name

            try:
                client.files.download(file=video.video)
                video.video.save(tmp_video_path)
            except Exception as save_error:
                logger.error(f"Failed to download/save video from Veo: {save_error}")
                yield ('error', f'Failed to download video: {save_error}')
                return

            with open(tmp_video_path, 'rb') as f:
                video_bytes = f.read()

            MIN_VIDEO_SIZE = 10000
            if len(video_bytes) < MIN_VIDEO_SIZE:
                logger.error(f"Video file too small ({len(video_bytes)} bytes)")
                yield ('error', 'Video file too small')
                return

            logger.info(f"Video generated successfully ({len(video_bytes)} bytes)")
            # Return both video object (for extension chaining) and bytes (for storage)
            yield ('complete', video.video, video_bytes)
        else:
            logger.warning("No video in response")
            yield ('error', 'No video in API response')

    except Exception as e:
        logger.error(f"Error generating video: {e}", exc_info=True)
        yield ('error', str(e))

    finally:
        # Cleanup temp files
        if tmp_image_path and os.path.exists(tmp_image_path):
            try:
                os.unlink(tmp_image_path)
            except:
                pass
        if tmp_video_path and os.path.exists(tmp_video_path):
            try:
                os.unlink(tmp_video_path)
            except:
                pass


def generate_video_extension_stream(
    previous_video,  # Veo Video object from previous generation
    video_prompt: str,
    aspect_ratio: str = "16:9",
    character_references: Optional[List[bytes]] = None
):
    """
    Extend a video using Veo 3.1 with progress events (generator).

    Uses the last second of the previous video to maintain visual and audio
    continuity. Each extension adds ~7 seconds to the video.

    Args:
        previous_video: The Veo Video object from the previous scene's generation
        video_prompt: Prompt for the extension (should include dialogue in quotes)
        aspect_ratio: "16:9" (landscape) or "9:16" (portrait) - must match original
        character_references: Optional list of reference image bytes for character consistency (max 3)

    Yields:
        ('progress', poll_count, max_polls) during polling
        ('complete', video_object, video_bytes) on success - returns both for chaining
        ('error', error_message) on failure
    """
    tmp_video_path = None

    try:
        logger.info(f"🔗 Extending video with next scene...")

        # Build config with optional reference images for character consistency
        config_kwargs = {"aspect_ratio": aspect_ratio}
        if character_references:
            ref_images = [
                types.Image.from_file(location=BytesIO(ref))
                for ref in character_references[:3]  # Veo max is 3
            ]
            config_kwargs["reference_images"] = ref_images
            logger.info(f"Including {len(ref_images)} character reference(s) for consistency")

        # Start video extension with aspect ratio and optional reference
        operation = client.models.generate_videos(
            model=VIDEO_MODEL,
            prompt=video_prompt,
            video=previous_video,  # Pass video object for extension
            config=types.GenerateVideosConfig(**config_kwargs)
        )

        # Poll until complete, yielding progress for SSE keepalive
        poll_count = 0
        max_polls = 60  # 10 minutes max
        while not operation.done and poll_count < max_polls:
            poll_count += 1
            logger.info(f"Video extension in progress... (poll {poll_count}/{max_polls})")

            yield ('progress', poll_count, max_polls)

            time.sleep(POLL_INTERVAL)
            operation = client.operations.get(operation)

        if not operation.done:
            logger.error(f"Video extension timed out after {poll_count * POLL_INTERVAL} seconds")
            yield ('error', 'Video extension timed out')
            return

        # Get the extended video
        if operation.response and operation.response.generated_videos:
            video = operation.response.generated_videos[0]

            if not hasattr(video, 'video') or video.video is None:
                logger.error("Veo API returned video object without video data")
                yield ('error', 'No video data in response')
                return

            # Download video bytes for storage
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_vid:
                tmp_video_path = tmp_vid.name

            try:
                client.files.download(file=video.video)
                video.video.save(tmp_video_path)
            except Exception as save_error:
                logger.error(f"Failed to download/save extended video: {save_error}")
                yield ('error', f'Failed to download video: {save_error}')
                return

            with open(tmp_video_path, 'rb') as f:
                video_bytes = f.read()

            MIN_VIDEO_SIZE = 10000
            if len(video_bytes) < MIN_VIDEO_SIZE:
                logger.error(f"Extended video too small ({len(video_bytes)} bytes)")
                yield ('error', 'Extended video too small')
                return

            logger.info(f"Video extended successfully ({len(video_bytes)} bytes)")
            # Return both the video object (for next extension) and bytes (for storage)
            yield ('complete', video.video, video_bytes)
        else:
            logger.warning("No video in extension response")
            yield ('error', 'No video in API response')

    except Exception as e:
        logger.error(f"Error extending video: {e}", exc_info=True)
        yield ('error', str(e))

    finally:
        if tmp_video_path and os.path.exists(tmp_video_path):
            try:
                os.unlink(tmp_video_path)
            except:
                pass


def generate_video_from_image(
    first_frame_bytes: bytes,
    video_prompt: str,
    aspect_ratio: str = "16:9"
) -> Optional[bytes]:
    """
    Generate a video using Veo 3.1 (blocking wrapper).

    For SSE streaming with Cloudflare, use generate_video_from_image_stream() instead.
    Returns just the video bytes (not the video object).
    """
    for event_type, *data in generate_video_from_image_stream(
        first_frame_bytes, video_prompt, aspect_ratio
    ):
        if event_type == 'complete':
            # data is (video_object, video_bytes) - return bytes
            return data[1]
        elif event_type == 'error':
            return None
    return None


def generate_video_stream(
    user_id: int,
    topic: str,
    style: str = "educational",
    target_duration: int = 30,
    author_bio: Optional[Dict] = None,
    user_prompt: str = "",
    job_id: Optional[int] = None,
    aspect_ratio: str = "16:9"
) -> Generator[str, None, None]:
    """
    Full video generation pipeline with SSE progress streaming.

    Yields SSE events:
    - planning: Script planning in progress
    - script_ready: Script planned with scene count
    - scene_image_{n}: Generating first frame for scene N
    - scene_video_{n}: Generating video for scene N
    - stitching: Combining videos
    - complete: Final video ready with base64 data
    - error: Something went wrong

    Args:
        user_id: User ID for database storage
        topic: Video topic
        style: Visual style (educational, storybook, social_media)
        target_duration: Target duration in seconds
        author_bio: Optional author bio with character reference
        user_prompt: Additional context
        job_id: Optional pre-created job ID (for background worker)
        aspect_ratio: "16:9" (landscape) or "9:16" (portrait) - locked for all scenes

    Yields:
        SSE event strings
    """
    from database import (
        create_video_job, update_video_job, create_video_scene,
        update_video_scene, get_author_bio
    )
    from author_bio import generate_character_references_batch
    import base64

    try:
        # Load author bio if not provided
        if not author_bio:
            author_bio = get_author_bio(user_id)

        # Legacy single character reference (from author bio)
        legacy_character_reference = None
        if author_bio and author_bio.get('reference_image'):
            legacy_character_reference = author_bio['reference_image']

        # Create job (or use provided job_id from background worker)
        if job_id is None:
            job_id = create_video_job(user_id, title=topic[:100])
            yield emit_event("job_created", job_id=job_id)
        # If job_id was provided, job_created event is emitted by the endpoint

        # Phase 0: Analyze prompt for multi-character references
        yield emit_event("analyzing", message="Analyzing characters...")

        char_analysis = extract_characters_from_prompt(user_prompt)
        characters = char_analysis.get('characters', [])
        scene_characters = char_analysis.get('scene_characters', {})
        global_style = char_analysis.get('global_style', 'storybook')
        needs_references = char_analysis.get('needs_references', False)

        # Dict mapping character_id -> image bytes
        character_references = {}

        if needs_references and characters:
            yield emit_event("generating_references",
                           message=f"Generating {len(characters)} character reference(s)...",
                           characters=[c.get('name') for c in characters])

            character_references = generate_character_references_batch(
                characters=characters,
                global_style=global_style
            )

            yield emit_event("references_ready",
                           count=len(character_references),
                           characters=list(character_references.keys()))
            logger.info(f"Generated {len(character_references)} character references")
        elif legacy_character_reference:
            # Fallback to legacy single author reference
            character_references = {"author": legacy_character_reference}
            logger.info("Using legacy author reference image")

        # Phase 1: Plan script
        yield emit_event("planning", message="Planning video script...")
        update_video_job(job_id, status="planning")

        script = plan_video_script(
            topic=topic,
            style=style,
            target_duration=target_duration,
            author_bio=author_bio,
            user_prompt=user_prompt
        )

        update_video_job(job_id, title=script.get('title', topic[:100]),
                        script_json=json.dumps(script))

        yield emit_event("script_ready",
                        title=script.get('title'),
                        summary=script.get('summary'),
                        scene_count=len(script.get('scenes', [])))

        # Phase 2: Generate scenes using video extension chain
        # Scene 1: Generate from first-frame image
        # Scenes 2+: Extend from previous video for continuity
        update_video_job(job_id, status="generating")
        scenes = script.get('scenes', [])

        # Track the current video object for extension chaining
        current_video_object = None
        final_video_bytes = None
        total_duration = 0

        # Pre-create all scenes in DB so frontend can see total count
        scene_ids = {}
        for scene in scenes:
            scene_num = scene['scene_number']
            scene_ids[scene_num] = create_video_scene(
                job_id=job_id,
                scene_number=scene_num,
                prompt=scene.get('video_prompt'),
                narration=scene.get('narration')
            )

        # Helper to get references for a specific scene
        def get_scene_references(scene_num: int, scene: dict) -> List[bytes]:
            """Get character references relevant to a specific scene."""
            # First try scene_characters from char_analysis
            scene_key = str(scene_num)
            char_ids = scene_characters.get(scene_key, [])

            if char_ids and character_references:
                refs = [character_references[cid] for cid in char_ids if cid in character_references]
                if refs:
                    return refs[:3]  # Max 3

            # Fallback: if scene has include_character flag and we have any references
            if scene.get('include_character') and character_references:
                return list(character_references.values())[:3]

            # No references for this scene
            return []

        for scene in scenes:
            scene_num = scene['scene_number']
            scene_id = scene_ids[scene_num]

            # Get references for this specific scene
            scene_refs = get_scene_references(scene_num, scene)
            if scene_refs:
                logger.info(f"Scene {scene_num}: using {len(scene_refs)} character reference(s)")

            # Rate limit protection: delay between scenes (except first)
            if scene_num > 1:
                logger.info(f"Waiting 1 minute before scene {scene_num} to avoid rate limits...")
                yield emit_event("scene_delay", scene=scene_num, delay=60,
                               message=f"Waiting 1 minute before scene {scene_num} (rate limit cooldown)...")
                time.sleep(60)

            # Scene 1: Generate first frame image and initial video
            if scene_num == 1:
                yield emit_event("scene_image",
                               scene=scene_num,
                               total=len(scenes),
                               message=f"Generating image for scene {scene_num}...")
                update_video_scene(scene_id, status="generating_image")

                image_bytes = generate_scene_image(
                    image_prompt=scene.get('image_prompt', scene.get('visual_description', '')),
                    character_references=scene_refs if scene_refs else None,
                    style=author_bio.get('style', 'real_person') if author_bio else 'real_person',
                    aspect_ratio=aspect_ratio
                )

                if not image_bytes:
                    yield emit_event("error", message="First scene image failed - cannot continue")
                    update_video_scene(scene_id, status="error", error_message="Image generation failed")
                    update_video_job(job_id, status="error", error_message="Scene 1 image failed")
                    return

                update_video_scene(scene_id, first_frame_image=image_bytes, status="generating_video")

                # Generate initial video from image
                yield emit_event("scene_video",
                               scene=scene_num,
                               total=len(scenes),
                               message=f"Generating video for scene {scene_num}...")

                # Refine the video prompt for Veo 3.1 best practices + realism
                raw_prompt = scene.get('video_prompt', scene.get('visual_description', ''))
                yield emit_event("refining_prompt", scene=scene_num,
                               message=f"Refining prompt for scene {scene_num}...")
                refined_prompt = refine_video_prompt(
                    video_prompt=raw_prompt,
                    scene_number=scene_num,
                    total_scenes=len(scenes),
                    style=style,
                    aspect_ratio=aspect_ratio,
                    full_context=user_prompt  # Pass original user prompt for character/setting consistency
                )

                video_bytes = None
                video_object = None
                quota_retry_count = 0

                while video_bytes is None and quota_retry_count <= MAX_QUOTA_RETRIES:
                    generation_error = None
                    for event_type, *event_data in generate_video_from_image_stream(
                        first_frame_bytes=image_bytes,
                        video_prompt=refined_prompt,
                        aspect_ratio=aspect_ratio
                    ):
                        if event_type == 'progress':
                            poll_count, max_polls = event_data
                            yield emit_event("scene_progress",
                                           scene=scene_num,
                                           total=len(scenes),
                                           poll=poll_count,
                                           max_polls=max_polls,
                                           message=f"Rendering scene {scene_num}... ({poll_count * 10}s)")
                        elif event_type == 'complete':
                            video_object, video_bytes = event_data[0], event_data[1]
                        elif event_type == 'error':
                            generation_error = event_data[0]
                            break

                    if generation_error:
                        error_msg = str(generation_error)
                        if '429' in error_msg or 'RESOURCE_EXHAUSTED' in error_msg:
                            if quota_retry_count < MAX_QUOTA_RETRIES:
                                delay = QUOTA_RETRY_DELAYS[quota_retry_count]
                                quota_retry_count += 1
                                yield emit_event("quota_retry",
                                               scene=scene_num,
                                               retry=quota_retry_count,
                                               max_retries=MAX_QUOTA_RETRIES,
                                               delay=delay,
                                               message=f"Quota exceeded - waiting {delay//60}m {delay%60}s...")
                                time.sleep(delay)
                                continue
                        yield emit_event("error", message=f"Scene 1 failed: {error_msg[:80]}")
                        update_video_scene(scene_id, status="error", error_message=error_msg[:200])
                        update_video_job(job_id, status="error", error_message=f"Scene 1 failed: {error_msg[:100]}")
                        return

                if not video_bytes or not video_object:
                    yield emit_event("error", message="Scene 1 video generation failed")
                    update_video_job(job_id, status="error", error_message="Scene 1 failed")
                    return

                current_video_object = video_object
                final_video_bytes = video_bytes
                total_duration = DEFAULT_VIDEO_DURATION
                update_video_scene(scene_id, video_data=video_bytes,
                                 duration_seconds=DEFAULT_VIDEO_DURATION, status="complete")
                yield emit_event("scene_complete", scene=scene_num, total=len(scenes))

            else:
                # Scenes 2+: Extend from previous video for continuity
                update_video_scene(scene_id, status="extending_video")

                yield emit_event("scene_video",
                               scene=scene_num,
                               total=len(scenes),
                               message=f"Extending video for scene {scene_num}...")

                # Refine the video prompt for Veo 3.1 best practices + realism
                raw_prompt = scene.get('video_prompt', scene.get('visual_description', ''))
                yield emit_event("refining_prompt", scene=scene_num,
                               message=f"Refining prompt for scene {scene_num}...")
                refined_prompt = refine_video_prompt(
                    video_prompt=raw_prompt,
                    scene_number=scene_num,
                    total_scenes=len(scenes),
                    style=style,
                    aspect_ratio=aspect_ratio,
                    full_context=user_prompt  # Pass original user prompt for character/setting consistency
                )

                video_bytes = None
                video_object = None
                quota_retry_count = 0

                while video_bytes is None and quota_retry_count <= MAX_QUOTA_RETRIES:
                    generation_error = None
                    for event_type, *event_data in generate_video_extension_stream(
                        previous_video=current_video_object,
                        video_prompt=refined_prompt,
                        aspect_ratio=aspect_ratio,
                        character_references=scene_refs if scene_refs else None
                    ):
                        if event_type == 'progress':
                            poll_count, max_polls = event_data
                            yield emit_event("scene_progress",
                                           scene=scene_num,
                                           total=len(scenes),
                                           poll=poll_count,
                                           max_polls=max_polls,
                                           message=f"Extending scene {scene_num}... ({poll_count * 10}s)")
                        elif event_type == 'complete':
                            video_object, video_bytes = event_data[0], event_data[1]
                        elif event_type == 'error':
                            generation_error = event_data[0]
                            break

                    if generation_error:
                        error_msg = str(generation_error)
                        if '429' in error_msg or 'RESOURCE_EXHAUSTED' in error_msg:
                            if quota_retry_count < MAX_QUOTA_RETRIES:
                                delay = QUOTA_RETRY_DELAYS[quota_retry_count]
                                quota_retry_count += 1
                                yield emit_event("quota_retry",
                                               scene=scene_num,
                                               retry=quota_retry_count,
                                               max_retries=MAX_QUOTA_RETRIES,
                                               delay=delay,
                                               message=f"Quota exceeded - waiting {delay//60}m {delay%60}s...")
                                time.sleep(delay)
                                continue
                        yield emit_event("error", message=f"Scene {scene_num} extension failed: {error_msg[:80]}")
                        update_video_scene(scene_id, status="error", error_message=error_msg[:200])
                        update_video_job(job_id, status="error", error_message=f"Scene {scene_num} failed: {error_msg[:100]}")
                        return

                if not video_bytes or not video_object:
                    yield emit_event("error", message=f"Scene {scene_num} extension failed")
                    update_video_job(job_id, status="error", error_message=f"Scene {scene_num} failed")
                    return

                # Update chain for next extension
                current_video_object = video_object
                final_video_bytes = video_bytes  # Extended video includes all previous scenes
                total_duration += 7  # Extensions add ~7 seconds
                update_video_scene(scene_id, video_data=video_bytes,
                                 duration_seconds=7, status="complete")
                yield emit_event("scene_complete", scene=scene_num, total=len(scenes))

        # Final video is already combined by Veo extension - no stitching needed
        if final_video_bytes:
            update_video_job(job_id, status="complete",
                           final_video=final_video_bytes, final_video_mime="video/mp4")

            video_base64 = base64.b64encode(final_video_bytes).decode('utf-8')
            yield emit_event("complete",
                           job_id=job_id,
                           title=script.get('title'),
                           duration=total_duration,
                           video_base64=video_base64)
        else:
            yield emit_event("error", message="No video generated")
            update_video_job(job_id, status="error", error_message="No video generated")

    except Exception as e:
        logger.error(f"Video generation error: {e}", exc_info=True)
        yield emit_event("error", message=str(e))
        if job_id:
            update_video_job(job_id, status="error", error_message=str(e))


def get_video_job_status(job_id: int, user_id: int) -> Optional[Dict]:
    """
    Get the current status of a video job.

    Args:
        job_id: Video job ID
        user_id: User ID for authorization

    Returns:
        Job status dict or None if not found
    """
    from database import get_video_job, get_video_scenes
    import base64

    job = get_video_job(job_id, user_id)
    if not job:
        return None

    scenes = get_video_scenes(job_id)

    result = {
        "id": job['id'],
        "job_id": job['job_id'],
        "status": job['status'],
        "title": job['title'],
        "script": job.get('script'),
        "error_message": job.get('error_message'),
        "created_at": job['created_at'],
        "updated_at": job['updated_at'],
        "scenes": scenes,
        "has_final_video": bool(job.get('final_video'))
    }

    # Include final video base64 if complete or partial
    if job['status'] in ('complete', 'partial') and job.get('final_video'):
        result['final_video_base64'] = base64.b64encode(job['final_video']).decode('utf-8')
        result['final_video_mime'] = job.get('final_video_mime', 'video/mp4')

    return result
