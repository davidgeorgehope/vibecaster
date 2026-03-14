"""Async CLI jobs for Vibecaster — submit/poll pattern to survive Cloudflare timeouts."""

import json
import time
import uuid
import threading
import traceback
import base64
from typing import Optional
import fastapi
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from auth_utils import get_current_user_id
from database import get_db, get_campaign, get_recent_topics
from logger_config import app_logger as logger


router = APIRouter(prefix="/api/cli", tags=["cli"])


# ===== DB helpers =====

def _ensure_cli_jobs_table():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cli_jobs (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                job_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                input_json TEXT,
                result_json TEXT,
                error TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

_ensure_cli_jobs_table()


def _create_job(user_id: int, job_type: str, input_data: dict) -> str:
    job_id = str(uuid.uuid4())[:8]
    now = int(time.time())
    with get_db() as conn:
        conn.execute(
            "INSERT INTO cli_jobs (id, user_id, job_type, status, input_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (job_id, user_id, job_type, "pending", json.dumps(input_data), now, now),
        )
    return job_id


def _update_job(job_id: str, status: str, result: dict = None, error: str = None):
    now = int(time.time())
    with get_db() as conn:
        conn.execute(
            "UPDATE cli_jobs SET status=?, result_json=?, error=?, updated_at=? WHERE id=?",
            (status, json.dumps(result) if result else None, error, now, job_id),
        )


def _get_job(job_id: str, user_id: int) -> Optional[dict]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, user_id, job_type, status, input_json, result_json, error, created_at, updated_at FROM cli_jobs WHERE id=? AND user_id=?",
            (job_id, user_id),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row[0], "user_id": row[1], "job_type": row[2], "status": row[3],
            "input": json.loads(row[4]) if row[4] else None,
            "result": json.loads(row[5]) if row[5] else None,
            "error": row[6], "created_at": row[7], "updated_at": row[8],
        }


# ===== Background workers =====

def _worker_create_post(job_id: str, user_id: int, prompt: str, platforms: list, media_type: str):
    """Generate post text + image from a prompt using Gemini directly, then optionally post."""
    try:
        _update_job(job_id, "generating_text")

        # Load campaign context
        campaign = get_campaign(user_id)
        refined_persona = (campaign.get("refined_persona") or "professional tech enthusiast") if campaign else "professional tech enthusiast"
        visual_style = (campaign.get("visual_style") or "Modern, clean, professional social media graphic") if campaign else "Modern, clean, professional social media graphic"
        user_prompt = (campaign.get("user_prompt") or prompt) if campaign else prompt
        recent_topics = get_recent_topics(user_id, days=14)

        # Use the prompt as search context (it IS the topic)
        search_context = f"Topic requested by user: {prompt}"

        # Step 1: Generate posts directly via post_generator
        from agents_lib.post_generator import generate_x_post, generate_linkedin_post

        x_post_text, _ = generate_x_post(
            search_context=search_context,
            refined_persona=refined_persona,
            user_prompt=user_prompt,
            source_url=None,
            recent_topics=recent_topics,
        )

        linkedin_text = generate_linkedin_post(
            search_context=search_context,
            refined_persona=refined_persona,
            user_prompt=user_prompt,
            source_url=None,
            recent_topics=recent_topics,
        )

        _update_job(job_id, "generating_image", result={
            "x_post": x_post_text, "linkedin_post": linkedin_text,
        })

        # Step 2: Generate image
        image_b64 = None
        if media_type != "none":
            from agents_lib.content_generator import generate_image
            image_bytes = generate_image(
                post_text=x_post_text or linkedin_text,
                visual_style=visual_style,
                user_prompt=user_prompt,
                topic_context=prompt,
            )
            if image_bytes:
                image_b64 = base64.b64encode(image_bytes).decode()

        if not platforms:
            # Preview only
            _update_job(job_id, "complete", result={
                "x_post": x_post_text, "linkedin_post": linkedin_text,
                "has_image": image_b64 is not None,
                "posted": [], "errors": {},
            })
            return

        _update_job(job_id, "posting", result={
            "x_post": x_post_text, "linkedin_post": linkedin_text,
            "has_image": image_b64 is not None,
        })

        # Step 3: Post to platforms
        from agents_lib.url_content import post_url_content
        post_result = post_url_content(user_id, x_post_text, linkedin_text, image_b64, platforms)

        _update_job(job_id, "complete", result={
            "x_post": x_post_text, "linkedin_post": linkedin_text,
            "has_image": image_b64 is not None,
            "posted": post_result.get("posted", []),
            "errors": post_result.get("errors", {}),
        })

    except Exception as e:
        logger.error(f"CLI job {job_id} failed: {e}\n{traceback.format_exc()}")
        _update_job(job_id, "failed", error=str(e))


def _worker_generate_from_url(job_id: str, user_id: int, url: str, platforms: list):
    """Generate posts from a URL, then optionally post."""
    try:
        _update_job(job_id, "generating")

        from agents_lib.url_content import generate_from_url, post_url_content
        result = generate_from_url(user_id, url)

        if result.get("error"):
            _update_job(job_id, "failed", error=result["error"])
            return

        x_post = result.get("x_post", "")
        linkedin_post = result.get("linkedin_post", "")
        image_b64 = result.get("image_base64")

        if not platforms:
            _update_job(job_id, "complete", result={
                "x_post": x_post, "linkedin_post": linkedin_post,
                "has_image": image_b64 is not None,
                "posted": [], "errors": {},
            })
            return

        _update_job(job_id, "posting")
        post_result = post_url_content(user_id, x_post, linkedin_post, image_b64, platforms)

        _update_job(job_id, "complete", result={
            "x_post": x_post, "linkedin_post": linkedin_post,
            "has_image": image_b64 is not None,
            "posted": post_result.get("posted", []),
            "errors": post_result.get("errors", {}),
        })

    except Exception as e:
        logger.error(f"CLI job {job_id} failed: {e}\n{traceback.format_exc()}")
        _update_job(job_id, "failed", error=str(e))


def _worker_direct_post(job_id: str, user_id: int, text: str, platforms: list, media_bytes: bytes = None, media_type: str = None):
    """Post directly with custom text and optional media. No AI generation."""
    try:
        _update_job(job_id, "posting")

        posted = []
        errors = {}

        if "linkedin" in platforms:
            if media_type and media_type.startswith("video"):
                from agents_lib.video_posting import upload_video_to_linkedin
                success, result = upload_video_to_linkedin(user_id, media_bytes, text)
                if success:
                    posted.append("linkedin")
                else:
                    errors["linkedin"] = str(result)
            else:
                from agents_lib.social_media import post_to_linkedin
                success = post_to_linkedin(user_id, text, media_bytes if media_type and media_type.startswith("image") else None)
                if success:
                    posted.append("linkedin")
                else:
                    errors["linkedin"] = "Failed to post"

        if "twitter" in platforms:
            from agents_lib.social_media import post_to_twitter
            success = post_to_twitter(user_id, text[:280], media_bytes if media_type and media_type.startswith("image") else None)
            if success:
                posted.append("twitter")
            else:
                errors["twitter"] = "Failed to post"

        _update_job(job_id, "complete", result={
            "text": text,
            "has_media": media_bytes is not None,
            "posted": posted,
            "errors": errors,
        })

    except Exception as e:
        logger.error(f"CLI direct post job {job_id} failed: {e}\n{traceback.format_exc()}")
        _update_job(job_id, "failed", error=str(e))


def _worker_direct_post_imagegen(job_id: str, user_id: int, text: str, platforms: list, image_prompt: str):
    """Post user's text with an AI-generated image. No campaign/persona needed."""
    try:
        _update_job(job_id, "generating_image")

        from agents_lib.content_generator import generate_image
        image_bytes = generate_image(
            post_text=text,
            visual_style="",
            user_prompt=image_prompt,
            topic_context=image_prompt,
        )

        if not image_bytes:
            _update_job(job_id, "failed", error="Image generation failed — no image returned")
            return

        image_b64 = base64.b64encode(image_bytes).decode()

        _update_job(job_id, "posting")

        posted = []
        errors = {}

        if "linkedin" in platforms:
            from agents_lib.social_media import post_to_linkedin
            success = post_to_linkedin(user_id, text, image_bytes)
            if success:
                posted.append("linkedin")
            else:
                errors["linkedin"] = "Failed to post"

        if "twitter" in platforms:
            from agents_lib.social_media import post_to_twitter
            success = post_to_twitter(user_id, text[:280], image_bytes)
            if success:
                posted.append("twitter")
            else:
                errors["twitter"] = "Failed to post"

        _update_job(job_id, "complete", result={
            "text": text,
            "has_image": True,
            "posted": posted,
            "errors": errors,
        })

    except Exception as e:
        logger.error(f"CLI direct post imagegen job {job_id} failed: {e}\n{traceback.format_exc()}")
        _update_job(job_id, "failed", error=str(e))


def _worker_transcribe(job_id: str, user_id: int, file_bytes: bytes, filename: str, mime_type: str):
    """Transcribe audio/video file and generate summary + blog post."""
    try:
        from transcription import upload_to_gemini, cleanup_gemini_file, client as gemini_client, LLM_MODEL

        _update_job(job_id, "uploading")
        media_part, uploaded_file = upload_to_gemini(file_bytes, filename, mime_type)

        _update_job(job_id, "transcribing")
        transcript_response = gemini_client.models.generate_content(
            model=LLM_MODEL,
            contents=[
                "Generate a complete, accurate, verbatim transcript of this audio/video. "
                "Include all spoken words exactly as said. Do not summarize or paraphrase. "
                "If there are multiple speakers, indicate speaker changes where possible.",
                media_part
            ]
        )
        transcript = transcript_response.text.strip()

        _update_job(job_id, "summarizing", result={"transcript": transcript})
        summary_response = gemini_client.models.generate_content(
            model=LLM_MODEL,
            contents=[
                f"Based on this transcript, write a concise summary (3-5 paragraphs) that captures "
                f"the key points, main topics discussed, and any important conclusions or takeaways.\n\n"
                f"TRANSCRIPT:\n{transcript}"
            ]
        )
        summary = summary_response.text.strip()

        _update_job(job_id, "generating_blog", result={"transcript": transcript, "summary": summary})
        blog_response = gemini_client.models.generate_content(
            model=LLM_MODEL,
            contents=[
                f"Write a standalone blog post about the topics and ideas discussed below. "
                f"The blog should read as an original article - do NOT reference the video, "
                f"transcript, speaker, or recording. Write as if these are your own insights "
                f"and expertise on the subject.\n\n"
                f"Include:\n"
                f"- A clear, descriptive title\n"
                f"- An introduction that sets context for the reader\n"
                f"- Main content organized into clear sections with headers\n"
                f"- A conclusion with key takeaways\n\n"
                f"WRITING STYLE:\n"
                f"- Write authentically - content that resonates with the natural audience\n"
                f"- Avoid marketing hype, buzzwords, and sensationalist language\n"
                f"- No words like 'revolutionizing', 'game-changing', 'cutting-edge', 'unleash', 'supercharge'\n"
                f"- Be clear and genuine rather than promotional\n"
                f"- Let the content speak for itself without overselling\n\n"
                f"Use markdown formatting.\n\n"
                f"SOURCE MATERIAL:\n{transcript}"
            ]
        )
        blog_post = blog_response.text.strip()

        _update_job(job_id, "complete", result={
            "transcript": transcript,
            "summary": summary,
            "blog_post": blog_post,
        })

        cleanup_gemini_file(uploaded_file)

    except Exception as e:
        logger.error(f"CLI transcribe job {job_id} failed: {e}\n{traceback.format_exc()}")
        _update_job(job_id, "failed", error=str(e))


def _worker_video_gen(job_id: str, user_id: int, topic: str, style: str, target_duration: int, aspect_ratio: str, user_prompt: str):
    """Generate a multi-scene AI video by wrapping generate_video_stream."""
    try:
        from video_generation import generate_video_stream

        _update_job(job_id, "generating")

        video_job_id = None
        last_status = "generating"

        for event_str in generate_video_stream(
            user_id=user_id,
            topic=topic,
            style=style,
            target_duration=target_duration,
            user_prompt=user_prompt,
            aspect_ratio="16:9" if aspect_ratio == "landscape" else "9:16",
        ):
            try:
                event = json.loads(event_str.strip())
            except (json.JSONDecodeError, ValueError):
                continue

            event_type = event.get("type", "")

            if event_type == "job_created":
                video_job_id = event.get("job_id")
                _update_job(job_id, "generating", result={"video_job_id": video_job_id})
            elif event_type == "script_ready":
                _update_job(job_id, "generating", result={
                    "video_job_id": video_job_id,
                    "step": "script_ready",
                    "scene_count": event.get("scene_count"),
                })
            elif event_type.startswith("scene_video_"):
                scene_num = event_type.replace("scene_video_", "")
                _update_job(job_id, "generating", result={
                    "video_job_id": video_job_id,
                    "step": f"scene_{scene_num}",
                    "message": event.get("message", ""),
                })
            elif event_type == "stitching":
                _update_job(job_id, "generating", result={
                    "video_job_id": video_job_id,
                    "step": "stitching",
                })
            elif event_type == "complete":
                _update_job(job_id, "complete", result={
                    "video_job_id": video_job_id,
                    "duration": event.get("duration"),
                })
                return
            elif event_type == "error":
                _update_job(job_id, "failed", error=event.get("message", "Video generation failed"))
                return

        # If we get here without complete/error, mark as failed
        _update_job(job_id, "failed", error="Video generation ended without completion")

    except Exception as e:
        logger.error(f"CLI video gen job {job_id} failed: {e}\n{traceback.format_exc()}")
        _update_job(job_id, "failed", error=str(e))


def _worker_video_post(job_id: str, user_id: int, file_bytes: bytes, filename: str, mime_type: str, platforms: list):
    """Transcribe video, generate platform posts, optionally post."""
    try:
        from transcription import upload_to_gemini, cleanup_gemini_file, client as gemini_client, LLM_MODEL

        _update_job(job_id, "uploading")
        media_part, uploaded_file = upload_to_gemini(file_bytes, filename, mime_type)

        _update_job(job_id, "transcribing")
        transcript_response = gemini_client.models.generate_content(
            model=LLM_MODEL,
            contents=[
                "Generate a complete, accurate, verbatim transcript of this video. "
                "Include all spoken words exactly as said.",
                media_part
            ]
        )
        transcript = transcript_response.text.strip()

        cleanup_gemini_file(uploaded_file)

        _update_job(job_id, "generating_posts", result={"transcript": transcript})

        # Import the generate function from main module
        import importlib
        main_mod = importlib.import_module("main")
        posts = main_mod.generate_video_posts_from_transcript(transcript, user_id)

        x_post = posts.get("x_post", "")
        linkedin_post = posts.get("linkedin_post", "")
        youtube_title = posts.get("youtube_title", "")
        youtube_description = posts.get("youtube_description", "")
        blog_post = posts.get("blog_post", "")

        if not platforms:
            _update_job(job_id, "complete", result={
                "transcript": transcript,
                "x_post": x_post,
                "linkedin_post": linkedin_post,
                "youtube_title": youtube_title,
                "youtube_description": youtube_description,
                "blog_post": blog_post,
                "posted": [],
                "errors": {},
            })
            return

        _update_job(job_id, "posting", result={
            "transcript": transcript,
            "x_post": x_post,
            "linkedin_post": linkedin_post,
            "youtube_title": youtube_title,
            "youtube_description": youtube_description,
            "blog_post": blog_post,
        })

        posted = []
        errors = {}

        if "linkedin" in platforms:
            try:
                from agents_lib.video_posting import upload_video_to_linkedin
                success, result = upload_video_to_linkedin(user_id, file_bytes, linkedin_post)
                if success:
                    posted.append("linkedin")
                else:
                    errors["linkedin"] = str(result)
            except Exception as e:
                errors["linkedin"] = str(e)

        if "twitter" in platforms:
            try:
                from agents_lib.social_media import post_to_twitter
                success = post_to_twitter(user_id, x_post[:280], file_bytes)
                if success:
                    posted.append("twitter")
                else:
                    errors["twitter"] = "Failed to post"
            except Exception as e:
                errors["twitter"] = str(e)

        if "youtube" in platforms:
            try:
                from agents_lib.video_posting import upload_video_to_youtube
                success, result = upload_video_to_youtube(user_id, file_bytes, youtube_title, youtube_description, filename)
                if success:
                    posted.append("youtube")
                else:
                    errors["youtube"] = str(result)
            except Exception as e:
                errors["youtube"] = str(e)

        _update_job(job_id, "complete", result={
            "transcript": transcript,
            "x_post": x_post,
            "linkedin_post": linkedin_post,
            "youtube_title": youtube_title,
            "youtube_description": youtube_description,
            "blog_post": blog_post,
            "posted": posted,
            "errors": errors,
        })

    except Exception as e:
        logger.error(f"CLI video post job {job_id} failed: {e}\n{traceback.format_exc()}")
        _update_job(job_id, "failed", error=str(e))


# ===== API endpoints =====

class CreatePostRequest(BaseModel):
    prompt: str
    platforms: list[str] = []  # empty = preview only, ["twitter", "linkedin"] = post
    media_type: str = "image"


class GenerateFromURLJobRequest(BaseModel):
    url: str
    platforms: list[str] = []


@router.post("/create-post", status_code=status.HTTP_202_ACCEPTED)
async def create_post_job(request: CreatePostRequest, user_id: int = Depends(get_current_user_id)):
    """Submit an async post creation job. Returns job ID for polling."""
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt is required")

    job_id = _create_job(user_id, "create_post", {
        "prompt": request.prompt,
        "platforms": request.platforms,
        "media_type": request.media_type,
    })

    thread = threading.Thread(
        target=_worker_create_post,
        args=(job_id, user_id, request.prompt.strip(), request.platforms, request.media_type),
        daemon=True,
    )
    thread.start()

    return {"job_id": job_id, "status": "pending"}


@router.post("/generate-from-url", status_code=status.HTTP_202_ACCEPTED)
async def generate_from_url_job(request: GenerateFromURLJobRequest, user_id: int = Depends(get_current_user_id)):
    """Submit an async URL generation job. Returns job ID for polling."""
    if not request.url or not request.url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Valid URL is required")

    job_id = _create_job(user_id, "generate_from_url", {
        "url": request.url,
        "platforms": request.platforms,
    })

    thread = threading.Thread(
        target=_worker_generate_from_url,
        args=(job_id, user_id, request.url, request.platforms),
        daemon=True,
    )
    thread.start()

    return {"job_id": job_id, "status": "pending"}


@router.post("/direct-post", status_code=status.HTTP_202_ACCEPTED)
async def direct_post_job(
    text: str = fastapi.Form(...),
    platforms: str = fastapi.Form("linkedin"),  # comma-separated
    media: Optional[fastapi.UploadFile] = fastapi.File(None),
    user_id: int = Depends(get_current_user_id),
):
    """Post directly with custom text and optional media file. No AI generation."""
    if not text.strip():
        raise HTTPException(status_code=400, detail="Text is required")

    platform_list = [p.strip() for p in platforms.split(",") if p.strip()]

    media_bytes = None
    media_content_type = None
    if media:
        media_bytes = await media.read()
        media_content_type = media.content_type

    job_id = _create_job(user_id, "direct_post", {
        "text": text,
        "platforms": platform_list,
        "has_media": media_bytes is not None,
        "media_type": media_content_type,
    })

    thread = threading.Thread(
        target=_worker_direct_post,
        args=(job_id, user_id, text.strip(), platform_list, media_bytes, media_content_type),
        daemon=True,
    )
    thread.start()

    return {"job_id": job_id, "status": "pending"}


class DirectPostImagegenRequest(BaseModel):
    text: str
    platforms: list[str] = ["linkedin"]
    image_prompt: str


@router.post("/direct-post-imagegen", status_code=status.HTTP_202_ACCEPTED)
async def direct_post_imagegen_job(request: DirectPostImagegenRequest, user_id: int = Depends(get_current_user_id)):
    """Post user's text with an AI-generated image. No campaign/persona needed."""
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Text is required")
    if not request.image_prompt.strip():
        raise HTTPException(status_code=400, detail="Image prompt is required")

    platform_list = [p.strip() for p in request.platforms if p.strip()]

    job_id = _create_job(user_id, "direct_post_imagegen", {
        "text": request.text,
        "platforms": platform_list,
        "image_prompt": request.image_prompt,
    })

    thread = threading.Thread(
        target=_worker_direct_post_imagegen,
        args=(job_id, user_id, request.text.strip(), platform_list, request.image_prompt.strip()),
        daemon=True,
    )
    thread.start()

    return {"job_id": job_id, "status": "pending"}


@router.post("/transcribe", status_code=status.HTTP_202_ACCEPTED)
async def transcribe_job(
    file: fastapi.UploadFile = fastapi.File(...),
    user_id: int = Depends(get_current_user_id),
):
    """Submit an async transcription job. Returns job ID for polling."""
    supported_types = {
        "audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav",
        "audio/aac", "audio/ogg", "audio/flac", "audio/aiff",
        "video/mp4", "video/webm", "video/quicktime", "video/x-m4v",
    }
    content_type = file.content_type or ""
    if content_type not in supported_types:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {content_type}")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    job_id = _create_job(user_id, "transcribe", {
        "filename": file.filename,
        "mime_type": content_type,
        "size": len(file_bytes),
    })

    thread = threading.Thread(
        target=_worker_transcribe,
        args=(job_id, user_id, file_bytes, file.filename, content_type),
        daemon=True,
    )
    thread.start()

    return {"job_id": job_id, "status": "pending"}


class VideoGenRequest(BaseModel):
    topic: str
    style: str = "educational"
    target_duration: int = 24
    aspect_ratio: str = "landscape"
    user_prompt: str = ""


@router.post("/video", status_code=status.HTTP_202_ACCEPTED)
async def video_gen_job(request: VideoGenRequest, user_id: int = Depends(get_current_user_id)):
    """Submit an async video generation job. Returns job ID for polling."""
    if not request.topic.strip():
        raise HTTPException(status_code=400, detail="Topic is required")

    job_id = _create_job(user_id, "video_gen", {
        "topic": request.topic,
        "style": request.style,
        "target_duration": request.target_duration,
        "aspect_ratio": request.aspect_ratio,
        "user_prompt": request.user_prompt,
    })

    thread = threading.Thread(
        target=_worker_video_gen,
        args=(job_id, user_id, request.topic.strip(), request.style, request.target_duration, request.aspect_ratio, request.user_prompt),
        daemon=True,
    )
    thread.start()

    return {"job_id": job_id, "status": "pending"}


@router.post("/video-post", status_code=status.HTTP_202_ACCEPTED)
async def video_post_job(
    file: fastapi.UploadFile = fastapi.File(...),
    platforms: str = fastapi.Form(""),
    user_id: int = Depends(get_current_user_id),
):
    """Submit an async video post job — transcribe video, generate posts, optionally post."""
    video_types = {"video/mp4", "video/webm", "video/quicktime", "video/x-m4v"}
    content_type = file.content_type or ""
    if content_type not in video_types:
        raise HTTPException(status_code=400, detail=f"Only video files allowed. Got: {content_type}")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    platform_list = [p.strip() for p in platforms.split(",") if p.strip()]

    job_id = _create_job(user_id, "video_post", {
        "filename": file.filename,
        "mime_type": content_type,
        "size": len(file_bytes),
        "platforms": platform_list,
    })

    thread = threading.Thread(
        target=_worker_video_post,
        args=(job_id, user_id, file_bytes, file.filename, content_type, platform_list),
        daemon=True,
    )
    thread.start()

    return {"job_id": job_id, "status": "pending"}


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str, user_id: int = Depends(get_current_user_id)):
    """Poll job status. Returns status + result when complete."""
    job = _get_job(job_id, user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    response = {
        "job_id": job["id"],
        "status": job["status"],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
    }
    if job["result"]:
        response["result"] = job["result"]
    if job["error"]:
        response["error"] = job["error"]

    return response
