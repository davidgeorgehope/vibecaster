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


def generate_video_from_image(
    first_frame_bytes: bytes,
    video_prompt: str,
    reference_images: Optional[List[bytes]] = None
) -> Optional[bytes]:
    """
    Generate a video using Veo 3.1 with a first frame image.

    Args:
        first_frame_bytes: First frame image bytes
        video_prompt: Motion/action prompt for video generation
        reference_images: Optional list of reference images for consistency (max 3)

    Returns:
        Video bytes (MP4) or None if generation fails
    """
    try:
        logger.info(f"🎥 Generating video from first frame...")

        # Load first frame as PIL Image
        first_frame = Image.open(BytesIO(first_frame_bytes))

        # Build config with reference images if provided
        config_kwargs = {}
        if reference_images:
            ref_list = []
            for ref_bytes in reference_images[:3]:  # Max 3 references
                ref_img = Image.open(BytesIO(ref_bytes))
                ref_list.append(types.VideoGenerationReferenceImage(
                    image=ref_img,
                    reference_type="asset"
                ))
            config_kwargs["reference_images"] = ref_list

        config = types.GenerateVideosConfig(**config_kwargs) if config_kwargs else None

        # Start video generation
        operation = client.models.generate_videos(
            model=VIDEO_MODEL,
            prompt=video_prompt,
            image=first_frame,
            config=config
        )

        # Poll until complete
        poll_count = 0
        max_polls = 60  # 10 minutes max
        while not operation.done and poll_count < max_polls:
            logger.info(f"Video generation in progress... (poll {poll_count + 1})")
            time.sleep(POLL_INTERVAL)
            operation = client.operations.get(operation)
            poll_count += 1

        if not operation.done:
            logger.error("Video generation timed out")
            return None

        # Download the generated video
        if operation.response and operation.response.generated_videos:
            video = operation.response.generated_videos[0]
            client.files.download(file=video.video)

            # Read video bytes
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
                video.video.save(tmp.name)
                tmp.flush()
                with open(tmp.name, 'rb') as f:
                    video_bytes = f.read()
                os.unlink(tmp.name)

            logger.info(f"Video generated successfully ({len(video_bytes)} bytes)")
            return video_bytes

        logger.warning("No video in response")
        return None

    except Exception as e:
        logger.error(f"Error generating video: {e}", exc_info=True)
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

        for scene in scenes:
            scene_num = scene['scene_number']
            scene_id = create_video_scene(
                job_id=job_id,
                scene_number=scene_num,
                prompt=scene.get('video_prompt'),
                narration=scene.get('narration')
            )

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
                yield emit_event("scene_error", scene=scene_num, error="Failed to generate image")
                update_video_scene(scene_id, status="error", error_message="Image generation failed")
                continue

            update_video_scene(scene_id, first_frame_image=image_bytes, status="generating_video")

            # Generate video from image
            yield emit_event("scene_video",
                           scene=scene_num,
                           total=len(scenes),
                           message=f"Generating video for scene {scene_num}...")

            # Build reference images list
            reference_images = []
            if character_reference and scene.get('include_character'):
                reference_images.append(character_reference)

            video_bytes = generate_video_from_image(
                first_frame_bytes=image_bytes,
                video_prompt=scene.get('video_prompt', scene.get('visual_description', '')),
                reference_images=reference_images if reference_images else None
            )

            if video_bytes:
                update_video_scene(scene_id, video_data=video_bytes,
                                 duration_seconds=DEFAULT_VIDEO_DURATION, status="complete")
                video_segments.append(video_bytes)
                yield emit_event("scene_complete", scene=scene_num, total=len(scenes))
            else:
                yield emit_event("scene_error", scene=scene_num, error="Failed to generate video")
                update_video_scene(scene_id, status="error", error_message="Video generation failed")

        if not video_segments:
            yield emit_event("error", message="No video segments generated")
            update_video_job(job_id, status="error", error_message="No segments generated")
            return

        # Phase 3: Stitch videos
        yield emit_event("stitching", message="Combining video segments...")
        update_video_job(job_id, status="stitching")

        final_video = stitch_videos(video_segments)

        if final_video:
            update_video_job(job_id, status="complete",
                           final_video=final_video, final_video_mime="video/mp4")

            # Return base64 encoded video for immediate preview
            video_base64 = base64.b64encode(final_video).decode('utf-8')
            yield emit_event("complete",
                           job_id=job_id,
                           title=script.get('title'),
                           duration=len(video_segments) * DEFAULT_VIDEO_DURATION,
                           video_base64=video_base64)
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

    # Include final video base64 if complete
    if job['status'] == 'complete' and job.get('final_video'):
        result['final_video_base64'] = base64.b64encode(job['final_video']).decode('utf-8')
        result['final_video_mime'] = job.get('final_video_mime', 'video/mp4')

    return result
