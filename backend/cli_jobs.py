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
