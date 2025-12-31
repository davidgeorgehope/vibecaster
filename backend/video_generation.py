"""
Video Generation Module - Multi-scene video generation with Veo 3.1

Provides functionality for:
- Script planning with LLM (scenes, image prompts, video prompts)
- Scene image generation with character reference (Nano Banana Pro)
- Video generation from first frame (Veo 3.1)
- Video extension and stitching (FFmpeg)
- SSE streaming for progress updates
"""

import os
import time
import json
import subprocess
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
        "educational": "Create an educational explainer video. Use clear, instructive visuals that help explain concepts. The narrator should be informative and engaging.",
        "storybook": "Create a narrative story with a beginning, middle, and end. Each scene should advance the plot with engaging visuals and storytelling.",
        "social_media": "Create a short, attention-grabbing video suitable for social media. Make it punchy, visually striking, and memorable."
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
            "narration": "What is spoken/shown in this scene (2-3 sentences)",
            "visual_description": "Detailed description of what appears visually",
            "image_prompt": "Detailed prompt for generating the first frame image (include style, lighting, composition)",
            "video_prompt": "Motion/action prompt for video generation (describe camera movement, character actions)",
            "include_character": true/false
        }}
    ],
    "total_scenes": {num_scenes},
    "estimated_duration": {num_scenes * DEFAULT_VIDEO_DURATION}
}}

IMPORTANT:
- Each scene is exactly {DEFAULT_VIDEO_DURATION} seconds
- Image prompts should be detailed and specific
- Video prompts should describe motion and action
- Keep narration concise but informative
- Ensure visual continuity between scenes"""

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


def generate_scene_image(
    image_prompt: str,
    character_reference: Optional[bytes] = None,
    style: str = "real_person"
) -> Optional[bytes]:
    """
    Generate a scene's first frame using Nano Banana Pro.

    Args:
        image_prompt: Detailed prompt for the image
        character_reference: Optional reference image bytes for character consistency
        style: Visual style for the image

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

    full_prompt = image_prompt + style_suffix.get(style, style_suffix["real_person"])

    try:
        logger.info(f"🖼️ Generating scene image...")

        contents = [full_prompt]

        # Add character reference if provided
        if character_reference:
            ref_image = Image.open(BytesIO(character_reference))
            contents.insert(0, "Use this character reference for consistency:")
            contents.insert(1, ref_image)

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
    video_prompt: str
):
    """
    Generate a video using Veo 3.1 with progress events (generator).

    Yields:
        ('progress', poll_count, max_polls) during polling
        ('complete', video_bytes) on success
        ('error', error_message) on failure

    NOTE: Use this for SSE streaming to keep Cloudflare connection alive.
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

        # Start video generation
        operation = client.models.generate_videos(
            model=VIDEO_MODEL,
            prompt=video_prompt,
            image=first_frame
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
            yield ('complete', video_bytes)
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


def generate_video_from_image(
    first_frame_bytes: bytes,
    video_prompt: str
) -> Optional[bytes]:
    """
    Generate a video using Veo 3.1 (blocking wrapper).

    For SSE streaming with Cloudflare, use generate_video_from_image_stream() instead.
    """
    for event_type, *data in generate_video_from_image_stream(first_frame_bytes, video_prompt):
        if event_type == 'complete':
            return data[0]
        elif event_type == 'error':
            return None
    return None


def stitch_videos(video_segments: List[bytes], output_format: str = "mp4") -> Optional[bytes]:
    """
    Stitch multiple video segments into a single video using FFmpeg.

    Args:
        video_segments: List of video bytes (MP4)
        output_format: Output format (default: mp4)

    Returns:
        Combined video bytes or None if stitching fails
    """
    if not video_segments:
        return None

    if len(video_segments) == 1:
        return video_segments[0]

    try:
        logger.info(f"🔗 Stitching {len(video_segments)} video segments...")

        # Create temp directory for video files
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write each segment to a file
            segment_files = []
            for i, segment in enumerate(video_segments):
                segment_path = os.path.join(tmpdir, f"segment_{i:03d}.mp4")
                with open(segment_path, 'wb') as f:
                    f.write(segment)
                segment_files.append(segment_path)

            # Create concat list file
            concat_list_path = os.path.join(tmpdir, "concat_list.txt")
            with open(concat_list_path, 'w') as f:
                for segment_path in segment_files:
                    f.write(f"file '{segment_path}'\n")

            # Output path
            output_path = os.path.join(tmpdir, f"output.{output_format}")

            # Run FFmpeg concat
            cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_list_path,
                '-c', 'copy',  # Copy codec, no re-encoding
                output_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

            if result.returncode != 0:
                logger.error(f"FFmpeg error: {result.stderr}")
                return None

            # Read output
            with open(output_path, 'rb') as f:
                output_bytes = f.read()

            logger.info(f"Videos stitched successfully ({len(output_bytes)} bytes)")
            return output_bytes

    except subprocess.TimeoutExpired:
        logger.error("FFmpeg timed out")
        return None
    except Exception as e:
        logger.error(f"Error stitching videos: {e}", exc_info=True)
        return None


def generate_video_stream(
    user_id: int,
    topic: str,
    style: str = "educational",
    target_duration: int = 30,
    author_bio: Optional[Dict] = None,
    user_prompt: str = ""
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

    Yields:
        SSE event strings
    """
    from database import (
        create_video_job, update_video_job, create_video_scene,
        update_video_scene, get_author_bio
    )
    import base64

    job_id = None

    try:
        # Load author bio if not provided
        if not author_bio:
            author_bio = get_author_bio(user_id)

        character_reference = None
        if author_bio and author_bio.get('reference_image'):
            character_reference = author_bio['reference_image']

        # Create job
        job_id = create_video_job(user_id, title=topic[:100])
        yield emit_event("job_created", job_id=job_id)

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

        # Phase 2: Generate scenes
        update_video_job(job_id, status="generating")
        scenes = script.get('scenes', [])
        video_segments = []
        failed_scenes = []  # Track which scenes failed for partial success warning

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

        for scene in scenes:
            scene_num = scene['scene_number']
            scene_id = scene_ids[scene_num]

            # Rate limit protection: delay between scenes (except first)
            # Veo API has 10-20 RPM limit; 2 min delay to avoid hitting limits on scene 3+
            if scene_num > 1:
                logger.info(f"Waiting 2 minutes before scene {scene_num} to avoid rate limits...")
                yield emit_event("scene_delay", scene=scene_num, delay=120,
                               message=f"Waiting 2 minutes before scene {scene_num} (rate limit cooldown)...")
                time.sleep(120)

            # Generate first frame image
            yield emit_event(f"scene_image",
                           scene=scene_num,
                           total=len(scenes),
                           message=f"Generating image for scene {scene_num}...")
            update_video_scene(scene_id, status="generating_image")

            image_bytes = generate_scene_image(
                image_prompt=scene.get('image_prompt', scene.get('visual_description', '')),
                character_reference=character_reference if scene.get('include_character') else None,
                style=author_bio.get('style', 'real_person') if author_bio else 'real_person'
            )

            if not image_bytes:
                # Scene 1 failed - can't make video without first scene
                if scene_num == 1:
                    yield emit_event("error", message="First scene image failed - cannot continue")
                    update_video_scene(scene_id, status="error", error_message="Image generation failed")
                    update_video_job(job_id, status="error", error_message="Scene 1 image failed")
                    return

                yield emit_event("scene_error", scene=scene_num, error="Failed to generate image")
                update_video_scene(scene_id, status="error", error_message="Image generation failed")
                failed_scenes.append(scene_num)
                continue

            update_video_scene(scene_id, first_frame_image=image_bytes, status="generating_video")

            # Generate video from image with retry logic for quota errors
            # NOTE: Character consistency is handled by generate_scene_image(), not here.
            # Veo API doesn't support reference_images with image-to-video mode.
            video_bytes = None
            quota_retry_count = 0

            while video_bytes is None and quota_retry_count <= MAX_QUOTA_RETRIES:
                yield emit_event("scene_video",
                               scene=scene_num,
                               total=len(scenes),
                               message=f"Generating video for scene {scene_num}..." +
                                       (f" (retry {quota_retry_count})" if quota_retry_count > 0 else ""))

                generation_error = None
                for event_type, *event_data in generate_video_from_image_stream(
                    first_frame_bytes=image_bytes,
                    video_prompt=scene.get('video_prompt', scene.get('visual_description', ''))
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
                        video_bytes = event_data[0]
                    elif event_type == 'error':
                        generation_error = event_data[0]
                        break

                # Handle errors with retry for quota issues
                if generation_error:
                    error_msg = str(generation_error)
                    logger.error(f"Video generation error: {error_msg}")

                    # Quota errors - retry with exponential backoff
                    if '429' in error_msg or 'RESOURCE_EXHAUSTED' in error_msg:
                        if quota_retry_count < MAX_QUOTA_RETRIES:
                            delay = QUOTA_RETRY_DELAYS[quota_retry_count]
                            quota_retry_count += 1
                            logger.info(f"Quota exceeded, waiting {delay}s before retry {quota_retry_count}/{MAX_QUOTA_RETRIES}")
                            yield emit_event("quota_retry",
                                           scene=scene_num,
                                           retry=quota_retry_count,
                                           max_retries=MAX_QUOTA_RETRIES,
                                           delay=delay,
                                           message=f"Quota exceeded - waiting {delay//60}m {delay%60}s before retry {quota_retry_count}/{MAX_QUOTA_RETRIES}...")
                            time.sleep(delay)
                            continue  # Retry the video generation
                        else:
                            # Max retries exhausted
                            yield emit_event("error", message="Quota exceeded after max retries - try again later")
                            update_video_scene(scene_id, status="error", error_message="Quota exceeded after retries")
                            update_video_job(job_id, status="error", error_message="Quota exceeded after retries")
                            return

                    # Scene 1 failed with non-quota error - abort
                    if scene_num == 1:
                        yield emit_event("error", message=f"First scene failed: {error_msg[:80]}")
                        update_video_scene(scene_id, status="error", error_message=error_msg[:200])
                        update_video_job(job_id, status="error", error_message=f"Scene 1 failed: {error_msg[:100]}")
                        return

                    # Later scenes can fail - continue with partial video
                    yield emit_event("scene_error", scene=scene_num, error=error_msg[:100])
                    update_video_scene(scene_id, status="error", error_message=error_msg[:200])
                    failed_scenes.append(scene_num)
                    break  # Exit retry loop, move to next scene

            if video_bytes:
                update_video_scene(scene_id, video_data=video_bytes,
                                 duration_seconds=DEFAULT_VIDEO_DURATION, status="complete")
                video_segments.append(video_bytes)
                yield emit_event("scene_complete", scene=scene_num, total=len(scenes))
            elif scene_num not in failed_scenes:
                # No video and not already marked as failed (shouldn't happen but just in case)
                yield emit_event("scene_error", scene=scene_num, error="Video generation returned empty")
                update_video_scene(scene_id, status="error", error_message="Video generation returned empty")
                failed_scenes.append(scene_num)

        # Fallback: if in-memory list is empty but DB has completed scenes, retrieve them
        # This handles cases where some scenes succeeded but later ones failed
        if not video_segments and job_id:
            from database import get_completed_scene_videos
            db_scenes = get_completed_scene_videos(job_id)
            if db_scenes:
                video_segments = [video_data for _, video_data in db_scenes]
                logger.info(f"Retrieved {len(video_segments)} completed scene(s) from database")
                yield emit_event("info", message=f"Retrieved {len(video_segments)} saved scene(s)")

        if not video_segments:
            yield emit_event("error", message="No video segments generated")
            update_video_job(job_id, status="error", error_message="No segments generated")
            return

        # Warn about partial success if some scenes failed
        if failed_scenes:
            warning_msg = f"Warning: {len(failed_scenes)} scene(s) failed (scenes {', '.join(map(str, failed_scenes))}). Returning partial video."
            logger.warning(warning_msg)
            yield emit_event("warning", message=warning_msg)

        # Phase 3: Stitch videos
        yield emit_event("stitching", message="Combining video segments...")
        update_video_job(job_id, status="stitching")

        final_video = stitch_videos(video_segments)

        if final_video:
            status = "partial" if failed_scenes else "complete"
            update_video_job(job_id, status=status,
                           final_video=final_video, final_video_mime="video/mp4")

            # Return base64 encoded video for immediate preview
            video_base64 = base64.b64encode(final_video).decode('utf-8')
            yield emit_event("complete",
                           job_id=job_id,
                           title=script.get('title'),
                           duration=len(video_segments) * DEFAULT_VIDEO_DURATION,
                           video_base64=video_base64,
                           partial=bool(failed_scenes),
                           failed_scenes=failed_scenes if failed_scenes else None)
        else:
            yield emit_event("error", message="Failed to stitch videos")
            update_video_job(job_id, status="error", error_message="Stitching failed")

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
