import os
import asyncio
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv
import uvicorn

# Import local modules
from database import init_database, get_campaign, update_campaign, get_connection_status
from agents import analyze_user_prompt, run_agent_cycle, generate_from_url, generate_from_url_stream, post_url_content, chat_post_builder_stream, parse_generated_posts, generate_image_for_post_builder
from transcription import transcribe_media_stream, SUPPORTED_MIME_TYPES
from author_bio import generate_character_reference, search_author_images, download_image_from_url, validate_image
from video_generation import generate_video_stream, get_video_job_status
from database import save_author_bio, get_author_bio, delete_author_bio, get_user_video_jobs, run_cleanup
from auth import router as auth_router
from user_auth import router as user_auth_router
from admin import router as admin_router
from auth_utils import get_current_user_id
from logger_config import app_logger as logger

load_dotenv()

# Allow insecure OAuth transport for local development
if os.getenv('ENVIRONMENT') == 'development':
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# Initialize FastAPI app
app = FastAPI(
    title="Vibecaster API",
    description="Local-first social media automation platform",
    version="1.0.0"
)

# Configure CORS
# In production with nginx reverse proxy, CORS is handled by nginx
# For direct access (development), we need to allow frontend origin
frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:3000')
allowed_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    frontend_url
]
# Remove duplicates
allowed_origins = list(set(allowed_origins))

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(user_auth_router)
app.include_router(auth_router)
app.include_router(admin_router)

# Initialize scheduler
scheduler = BackgroundScheduler()


# ===== PYDANTIC MODELS =====

class SetupRequest(BaseModel):
    user_prompt: str
    schedule_cron: str = "0 9 * * *"  # Default: Daily at 9 AM
    media_type: Optional[str] = None  # Auto-detected from prompt if not provided


def detect_media_type_from_prompt(prompt: str) -> str:
    """
    Auto-detect whether the user wants video or image content based on their prompt.

    Examples that trigger video:
    - "generate opentelemetry memes daily with a 40 second video"
    - "create short video clips about kubernetes"
    - "post animated explainers"

    Default is image.
    """
    prompt_lower = prompt.lower()

    # Video keywords and patterns
    video_patterns = [
        'video', 'videos', 'clip', 'clips', 'animation', 'animated',
        'second video', 'seconds video', 'minute video', 'minutes video',
        's video', 'sec video', 'min video',
        'motion', 'moving', 'explainer video', 'short video'
    ]

    # Check for video indicators
    for pattern in video_patterns:
        if pattern in prompt_lower:
            return 'video'

    # Check for duration mentions (e.g., "30s", "1 minute", "40 seconds")
    import re
    duration_pattern = r'\b(\d+)\s*(s|sec|second|seconds|min|minute|minutes)\b'
    if re.search(duration_pattern, prompt_lower):
        return 'video'

    # Default to image
    return 'image'


class CampaignResponse(BaseModel):
    user_prompt: str
    refined_persona: str
    visual_style: str
    schedule_cron: str
    last_run: int
    media_type: str = "image"


class GenerateFromURLRequest(BaseModel):
    url: str


class PostFromURLRequest(BaseModel):
    x_post: str = None
    linkedin_post: str = None
    image_base64: str = None
    platforms: list[str]


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


class GenerateImageRequest(BaseModel):
    post_text: str
    visual_style: Optional[str] = None


class GenerateMediaRequest(BaseModel):
    post_text: str
    visual_style: Optional[str] = None
    media_type: str = "image"  # "image" or "video"


# ===== AUTHOR BIO MODELS =====

class AuthorBioRequest(BaseModel):
    name: str
    description: str
    style: str = "real_person"  # real_person, cartoon, anime, avatar, 3d_render


class GenerateReferenceRequest(BaseModel):
    description: str
    style: str = "real_person"
    additional_context: Optional[str] = None


class SearchImagesRequest(BaseModel):
    author_name: str
    limit: int = 5


class DownloadImageRequest(BaseModel):
    url: str


# ===== VIDEO GENERATION MODELS =====

class VideoGenerateRequest(BaseModel):
    topic: str
    style: str = "educational"  # educational, storybook, social_media
    target_duration: int = 30  # Target duration in seconds
    user_prompt: Optional[str] = None


# ===== SCHEDULER MANAGEMENT =====

def setup_scheduler(user_id: int = None):
    """Configure and start the scheduler with the current campaign settings.

    Args:
        user_id: If provided, set up scheduler for this user.
                If None, set up schedulers for all users with campaigns.
    """
    try:
        if user_id is not None:
            # Set up scheduler for a specific user
            _setup_user_scheduler(user_id)
        else:
            # On startup, set up schedulers for all users with campaigns
            from database import get_db
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT user_id FROM campaign
                    WHERE user_prompt IS NOT NULL AND user_prompt != ''
                """)
                users_with_campaigns = cursor.fetchall()

            for row in users_with_campaigns:
                _setup_user_scheduler(row[0])

            logger.info(f"Scheduler configured for {len(users_with_campaigns)} user(s)")

    except Exception as e:
        logger.error(f"Error setting up scheduler: {e}", exc_info=True)


def _setup_user_scheduler(user_id: int):
    """Set up scheduler for a specific user."""
    try:
        job_id = f"agent_cycle_user_{user_id}"

        # Get campaign configuration for this user
        campaign = get_campaign(user_id)
        if campaign and campaign.get("user_prompt"):
            cron_schedule = campaign.get("schedule_cron", "0 9 * * *")

            # Parse cron schedule (minute hour day month day_of_week)
            parts = cron_schedule.split()
            if len(parts) == 5:
                minute, hour, day, month, day_of_week = parts

                # Add job to scheduler (user-specific)
                scheduler.add_job(
                    run_agent_cycle,
                    trigger=CronTrigger(
                        minute=minute,
                        hour=hour,
                        day=day,
                        month=month,
                        day_of_week=day_of_week
                    ),
                    args=[user_id],  # Pass user_id to run_agent_cycle
                    id=job_id,
                    name=f"Vibecaster Agent Cycle (User {user_id})",
                    replace_existing=True
                )

                logger.info(f"Scheduler configured for user {user_id} with cron: {cron_schedule}")
            else:
                logger.warning(f"Invalid cron schedule for user {user_id}: {cron_schedule}")
        else:
            # Remove job if campaign is empty or deleted
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)
                logger.info(f"Removed scheduler job for user {user_id}")

    except Exception as e:
        logger.error(f"Error setting up scheduler for user {user_id}: {e}", exc_info=True)


# ===== LIFECYCLE EVENTS =====

def run_cleanup_job():
    """Background job to cleanup old files."""
    try:
        result = run_cleanup(video_job_hours=24, post_history_days=90)
        if result["video_jobs_deleted"] > 0 or result["post_history_deleted"] > 0:
            logger.info(f"Cleanup completed: {result['video_jobs_deleted']} video jobs, {result['post_history_deleted']} old posts deleted")
    except Exception as e:
        logger.error(f"Cleanup job failed: {e}", exc_info=True)


@app.on_event("startup")
async def startup_event():
    """Initialize database and scheduler on startup."""
    logger.info("Starting Vibecaster API...")

    # Initialize database
    init_database()
    logger.info("Database initialized")

    # Start scheduler
    scheduler.start()
    logger.info("Scheduler started")

    # Add cleanup job (runs every hour)
    scheduler.add_job(
        run_cleanup_job,
        trigger=IntervalTrigger(hours=1),
        id="cleanup_job",
        replace_existing=True
    )
    logger.info("Cleanup job scheduled (every hour)")

    # Run initial cleanup on startup
    run_cleanup_job()

    # Configure scheduler with existing campaign
    setup_scheduler()


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("Shutting down Vibecaster API...")
    scheduler.shutdown()
    logger.info("Scheduler stopped")


# ===== API ENDPOINTS =====

@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "running",
        "service": "Vibecaster API",
        "version": "1.0.0"
    }


@app.get("/api/status")
async def get_status(user_id: int = Depends(get_current_user_id)):
    """Get overall system status."""
    campaign = get_campaign(user_id)
    connections = get_connection_status(user_id)

    return {
        "connections": connections,
        "campaign_configured": bool(campaign and campaign.get("user_prompt")),
        "scheduler_running": scheduler.running,
        "active_jobs": len(scheduler.get_jobs())
    }


@app.get("/api/campaign")
async def get_campaign_info(user_id: int = Depends(get_current_user_id)):
    """Get current campaign configuration."""
    campaign = get_campaign(user_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="No campaign configured")

    return {
        "user_prompt": campaign.get("user_prompt", ""),
        "refined_persona": campaign.get("refined_persona", ""),
        "visual_style": campaign.get("visual_style", ""),
        "schedule_cron": campaign.get("schedule_cron", "0 9 * * *"),
        "last_run": campaign.get("last_run", 0)
    }


@app.post("/api/setup")
async def setup_campaign(request: SetupRequest, user_id: int = Depends(get_current_user_id)):
    """
    Setup or update the campaign configuration.
    This analyzes the user prompt and configures the AI agent.
    Media type (image/video) is auto-detected from the prompt.
    """
    try:
        # Analyze user prompt with AI
        logger.info(f"Analyzing prompt: {request.user_prompt}")
        refined_persona, visual_style = analyze_user_prompt(request.user_prompt)

        # Auto-detect media type from prompt (or use explicit value if provided)
        if request.media_type and request.media_type in ("image", "video"):
            media_type = request.media_type
        else:
            media_type = detect_media_type_from_prompt(request.user_prompt)
            logger.info(f"Auto-detected media type: {media_type}")

        # Update campaign in database
        update_campaign(
            user_id=user_id,
            user_prompt=request.user_prompt,
            refined_persona=refined_persona,
            visual_style=visual_style,
            schedule_cron=request.schedule_cron,
            media_type=media_type
        )

        # Reconfigure scheduler for this user
        setup_scheduler(user_id)

        return {
            "success": True,
            "message": "Campaign configured successfully",
            "campaign": {
                "user_prompt": request.user_prompt,
                "refined_persona": refined_persona,
                "visual_style": visual_style,
                "schedule_cron": request.schedule_cron,
                "media_type": media_type
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to setup campaign: {str(e)}")


@app.post("/api/run-now")
async def run_agent_now(user_id: int = Depends(get_current_user_id)):
    """Manually trigger the agent cycle immediately."""
    try:
        campaign = get_campaign(user_id)
        if not campaign or not campaign.get("user_prompt"):
            raise HTTPException(status_code=400, detail="No campaign configured")

        # Run agent cycle in background
        import threading
        thread = threading.Thread(target=run_agent_cycle, args=(user_id,))
        thread.start()

        return {
            "success": True,
            "message": "Agent cycle started"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/campaign")
async def delete_campaign(user_id: int = Depends(get_current_user_id)):
    """Delete the current campaign configuration."""
    try:
        update_campaign(
            user_id=user_id,
            user_prompt="",
            refined_persona="",
            visual_style="",
            schedule_cron="0 9 * * *"
        )

        # Remove scheduler job for this user only
        job_id = f"agent_cycle_user_{user_id}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)

        return {
            "success": True,
            "message": "Campaign deleted"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/generate-from-url")
async def generate_from_url_endpoint(request: GenerateFromURLRequest, user_id: int = Depends(get_current_user_id)):
    """
    Generate social media posts from a URL.
    Returns X post, LinkedIn post, and image for preview before posting.
    """
    try:
        # Validate URL format
        if not request.url or not request.url.startswith(('http://', 'https://')):
            raise HTTPException(status_code=400, detail="Invalid URL format")

        # Run generation in a separate thread to avoid blocking
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(generate_from_url, user_id, request.url)
            result = future.result(timeout=180)  # 3 minute timeout

        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])

        return result

    except concurrent.futures.TimeoutError:
        raise HTTPException(status_code=504, detail="Generation timed out")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate posts: {str(e)}")


@app.post("/api/generate-from-url-stream")
async def generate_from_url_stream_endpoint(request: GenerateFromURLRequest, user_id: int = Depends(get_current_user_id)):
    """
    Stream social media post generation from a URL with progress updates.
    Uses Server-Sent Events (SSE) to avoid timeout issues.
    """
    # Validate URL format
    if not request.url or not request.url.startswith(('http://', 'https://')):
        raise HTTPException(status_code=400, detail="Invalid URL format")

    def generate():
        for chunk in generate_from_url_stream(user_id, request.url):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.post("/api/post-from-url")
async def post_from_url_endpoint(request: PostFromURLRequest, user_id: int = Depends(get_current_user_id)):
    """
    Post pre-generated content to specified platforms.
    """
    try:
        if not request.platforms:
            raise HTTPException(status_code=400, detail="No platforms specified")

        valid_platforms = ['twitter', 'linkedin']
        for platform in request.platforms:
            if platform not in valid_platforms:
                raise HTTPException(status_code=400, detail=f"Invalid platform: {platform}")

        result = post_url_content(
            user_id=user_id,
            x_post=request.x_post,
            linkedin_post=request.linkedin_post,
            image_base64=request.image_base64,
            platforms=request.platforms
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to post: {str(e)}")


# ===== POST BUILDER CHAT =====

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest, user_id: int = Depends(get_current_user_id)):
    """
    Stream a chat response for the post builder.
    Uses Server-Sent Events (SSE) for real-time streaming.
    """
    def generate():
        try:
            # Convert Pydantic models to dicts
            history = [{"role": msg.role, "content": msg.content} for msg in request.history]

            for chunk in chat_post_builder_stream(request.message, history, user_id):
                # SSE format: data: <content>\n\n
                yield f"data: {chunk}\n\n"

            # Signal end of stream
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"Error in chat stream: {e}")
            yield f"data: Error: {str(e)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


@app.post("/api/chat/generate-image")
async def chat_generate_image(request: GenerateImageRequest, user_id: int = Depends(get_current_user_id)):
    """
    Generate an image for a post builder preview.
    Accepts optional visual_style to customize the image (e.g., "Mario and Luigi cartoon characters...")
    """
    try:
        import concurrent.futures
        import base64

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                generate_image_for_post_builder,
                request.post_text,
                request.visual_style,  # Pass visual_style from request
                user_id
            )
            image_bytes = future.result(timeout=120)  # 2 minute timeout

        if not image_bytes:
            raise HTTPException(status_code=500, detail="Failed to generate image")

        # Return base64 encoded image
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        return {"image_base64": image_base64}

    except concurrent.futures.TimeoutError:
        raise HTTPException(status_code=504, detail="Image generation timed out")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate image: {str(e)}")


@app.post("/api/chat/generate-media")
async def chat_generate_media(request: GenerateMediaRequest, user_id: int = Depends(get_current_user_id)):
    """
    Generate media (image or video) for a post builder preview.
    Set media_type to "video" for 8-second video clips, defaults to "image".
    """
    from agents import generate_media_for_post_builder

    try:
        import concurrent.futures
        import base64

        # Validate media_type
        if request.media_type not in ("image", "video"):
            raise HTTPException(status_code=400, detail="media_type must be 'image' or 'video'")

        # Video takes much longer
        timeout = 120 if request.media_type == "image" else 600

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                generate_media_for_post_builder,
                request.post_text,
                request.visual_style,
                user_id,
                request.media_type
            )
            media_bytes, mime_type = future.result(timeout=timeout)

        if not media_bytes:
            raise HTTPException(status_code=500, detail=f"Failed to generate {request.media_type}")

        media_base64 = base64.b64encode(media_bytes).decode('utf-8')
        return {
            "media_base64": media_base64,
            "mime_type": mime_type,
            "media_type": request.media_type
        }

    except concurrent.futures.TimeoutError:
        raise HTTPException(status_code=504, detail=f"{request.media_type.title()} generation timed out")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate {request.media_type}: {str(e)}")


# ===== TRANSCRIPTION =====

MAX_UPLOAD_SIZE = 200 * 1024 * 1024  # 200MB


@app.post("/api/transcribe-stream")
async def transcribe_stream_endpoint(
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id)
):
    """
    Stream transcription and content generation from audio/video files.
    Uses Server-Sent Events (SSE) for real-time progress updates.

    Returns transcript, summary, and blog post.
    File is processed in memory and immediately discarded.
    """
    # Validate file type
    content_type = file.content_type or ""
    if content_type not in SUPPORTED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {content_type}. Supported: audio (mp3, wav, aac, ogg, flac) and video (mp4, webm, mov)"
        )

    # Read file into memory
    file_bytes = await file.read()

    # Validate file size
    if len(file_bytes) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {MAX_UPLOAD_SIZE // (1024*1024)}MB"
        )

    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    logger.info(f"[Transcribe] User {user_id} uploading {file.filename} ({len(file_bytes)} bytes)")

    def generate():
        for chunk in transcribe_media_stream(user_id, file_bytes, file.filename, content_type):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# ===== AUTHOR BIO ENDPOINTS =====

@app.get("/api/author-bio")
async def get_author_bio_endpoint(user_id: int = Depends(get_current_user_id)):
    """Get current author/character bio."""
    bio = get_author_bio(user_id)
    if not bio:
        return {
            "exists": False,
            "name": "",
            "description": "",
            "style": "real_person",
            "has_reference_image": False
        }

    return {
        "exists": True,
        "name": bio.get("name", ""),
        "description": bio.get("description", ""),
        "style": bio.get("style", "real_person"),
        "has_reference_image": bool(bio.get("reference_image")),
        "reference_image_base64": bio.get("reference_image_base64"),
        "reference_image_mime": bio.get("reference_image_mime", "image/png"),
        "created_at": bio.get("created_at"),
        "updated_at": bio.get("updated_at")
    }


@app.post("/api/author-bio")
async def save_author_bio_endpoint(
    request: AuthorBioRequest,
    user_id: int = Depends(get_current_user_id)
):
    """Save or update author/character bio."""
    try:
        save_author_bio(
            user_id=user_id,
            name=request.name,
            description=request.description,
            style=request.style
        )
        return {"success": True, "message": "Author bio saved"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save bio: {str(e)}")


@app.delete("/api/author-bio")
async def delete_author_bio_endpoint(user_id: int = Depends(get_current_user_id)):
    """Delete author/character bio."""
    try:
        delete_author_bio(user_id)
        return {"success": True, "message": "Author bio deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete bio: {str(e)}")


@app.post("/api/author-bio/generate-reference")
async def generate_reference_endpoint(
    request: GenerateReferenceRequest,
    user_id: int = Depends(get_current_user_id)
):
    """Generate a character reference image from description."""
    try:
        import concurrent.futures
        import base64

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                generate_character_reference,
                request.description,
                request.style,
                request.additional_context or ""
            )
            image_bytes = future.result(timeout=120)  # 2 minute timeout

        if not image_bytes:
            raise HTTPException(status_code=500, detail="Failed to generate character reference")

        # Save the generated image to the bio
        save_author_bio(
            user_id=user_id,
            reference_image=image_bytes,
            reference_image_mime="image/png"
        )

        # Return base64 encoded image
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        return {
            "success": True,
            "image_base64": image_base64,
            "mime_type": "image/png"
        }

    except concurrent.futures.TimeoutError:
        raise HTTPException(status_code=504, detail="Image generation timed out")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate reference: {str(e)}")


@app.post("/api/author-bio/search-images")
async def search_images_endpoint(
    request: SearchImagesRequest,
    user_id: int = Depends(get_current_user_id)
):
    """Search for author images online."""
    try:
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                search_author_images,
                request.author_name,
                request.limit
            )
            results = future.result(timeout=30)

        return {"results": results}

    except concurrent.futures.TimeoutError:
        raise HTTPException(status_code=504, detail="Search timed out")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@app.post("/api/author-bio/upload-reference")
async def upload_reference_endpoint(
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id)
):
    """Upload author/character reference image."""
    import base64

    # Validate file type
    content_type = file.content_type or ""
    if not content_type.startswith('image/'):
        raise HTTPException(
            status_code=400,
            detail="File must be an image (PNG, JPEG, GIF, or WEBP)"
        )

    # Read file
    file_bytes = await file.read()

    # Validate size (max 10MB)
    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image too large. Maximum size: 10MB")

    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    # Validate image
    validation = validate_image(file_bytes)
    if not validation.get('valid'):
        raise HTTPException(status_code=400, detail=f"Invalid image: {validation.get('error')}")

    # Save to bio
    save_author_bio(
        user_id=user_id,
        reference_image=file_bytes,
        reference_image_mime=validation.get('mime_type', content_type)
    )

    # Return success with image info
    return {
        "success": True,
        "image_base64": base64.b64encode(file_bytes).decode('utf-8'),
        "mime_type": validation.get('mime_type'),
        "width": validation.get('width'),
        "height": validation.get('height')
    }


@app.post("/api/author-bio/download-image")
async def download_image_endpoint(
    request: DownloadImageRequest,
    user_id: int = Depends(get_current_user_id)
):
    """Download an image from URL and set as reference."""
    import base64
    import concurrent.futures

    try:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(download_image_from_url, request.url)
            image_bytes = future.result(timeout=30)

        if not image_bytes:
            raise HTTPException(status_code=400, detail="Failed to download image from URL")

        # Validate image
        validation = validate_image(image_bytes)
        if not validation.get('valid'):
            raise HTTPException(status_code=400, detail=f"Invalid image: {validation.get('error')}")

        # Save to bio
        save_author_bio(
            user_id=user_id,
            reference_image=image_bytes,
            reference_image_mime=validation.get('mime_type', 'image/png')
        )

        return {
            "success": True,
            "image_base64": base64.b64encode(image_bytes).decode('utf-8'),
            "mime_type": validation.get('mime_type'),
            "width": validation.get('width'),
            "height": validation.get('height')
        }

    except concurrent.futures.TimeoutError:
        raise HTTPException(status_code=504, detail="Download timed out")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download image: {str(e)}")


# ===== VIDEO GENERATION ENDPOINTS =====

@app.post("/api/video/generate-stream")
async def video_generate_stream_endpoint(
    request: VideoGenerateRequest,
    user_id: int = Depends(get_current_user_id)
):
    """
    Stream video generation with progress updates.

    Video generation runs in a background thread. This endpoint:
    1. Creates the job in database
    2. Starts background worker
    3. Polls database for events and streams them via SSE

    If client disconnects, background job continues. Client can reconnect
    via polling GET /api/video/jobs/{job_id}.
    """
    from database import create_video_job, get_job_events_since
    from video_worker import start_video_job, is_job_running
    import json
    import time as time_module

    # Create job upfront so we have an ID
    job_id = create_video_job(user_id, title=request.topic[:100])

    # Start background worker
    started = start_video_job(
        job_id=job_id,
        user_id=user_id,
        topic=request.topic,
        style=request.style,
        target_duration=request.target_duration,
        user_prompt=request.user_prompt or ""
    )

    if not started:
        raise HTTPException(status_code=409, detail="Job already running")

    async def generate():
        # Emit job_created immediately (before worker has a chance to)
        job_created_event = json.dumps({
            "type": "job_created",
            "job_id": job_id,
            "timestamp": time_module.time()
        })
        yield f"data: {job_created_event}\n\n"

        last_event_id = 0
        no_event_count = 0

        while True:
            # Poll database for new events
            events = get_job_events_since(job_id, last_event_id)

            if events:
                no_event_count = 0
                for event_id, event_json in events:
                    yield f"data: {event_json}\n\n"
                    last_event_id = event_id

                    # Check for terminal events
                    if '"type": "complete"' in event_json or '"type": "error"' in event_json:
                        yield "data: [DONE]\n\n"
                        return
            else:
                no_event_count += 1
                # Send keepalive every ~10 seconds to prevent Cloudflare timeout
                if no_event_count % 10 == 0:
                    keepalive = json.dumps({
                        "type": "keepalive",
                        "timestamp": time_module.time()
                    })
                    yield f"data: {keepalive}\n\n"

                # If job is no longer running and no new events, it may have crashed
                if not is_job_running(job_id) and no_event_count > 5:
                    # Check if we have a terminal event we might have missed
                    final_events = get_job_events_since(job_id, last_event_id)
                    for event_id, event_json in final_events:
                        yield f"data: {event_json}\n\n"
                    yield "data: [DONE]\n\n"
                    return

            await asyncio.sleep(1)  # Poll every 1 second

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/api/video/jobs")
async def get_video_jobs_endpoint(user_id: int = Depends(get_current_user_id)):
    """Get list of user's video generation jobs."""
    jobs = get_user_video_jobs(user_id)
    return {"jobs": jobs}


@app.get("/api/video/jobs/{job_id}")
async def get_video_job_endpoint(job_id: int, user_id: int = Depends(get_current_user_id)):
    """Get status and details of a specific video job."""
    job = get_video_job_status(job_id, user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Video job not found")
    return job


@app.get("/api/video/jobs/{job_id}/download")
async def download_video_endpoint(job_id: int, user_id: int = Depends(get_current_user_id)):
    """Download completed video."""
    from database import get_video_job

    job = get_video_job(job_id, user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Video job not found")

    if job['status'] != 'complete':
        raise HTTPException(status_code=400, detail="Video not ready")

    if not job.get('final_video'):
        raise HTTPException(status_code=404, detail="Video data not found")

    from fastapi.responses import Response
    return Response(
        content=job['final_video'],
        media_type=job.get('final_video_mime', 'video/mp4'),
        headers={
            "Content-Disposition": f"attachment; filename=\"{job.get('title', 'video')}.mp4\""
        }
    )


@app.post("/api/video/jobs/{job_id}/cancel")
async def cancel_video_job_endpoint(job_id: int, user_id: int = Depends(get_current_user_id)):
    """Cancel an in-progress video job (marks as error)."""
    from database import get_video_job, update_video_job

    job = get_video_job(job_id, user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Video job not found")

    # Only allow canceling in-progress jobs
    if job['status'] in ('complete', 'partial', 'error'):
        raise HTTPException(status_code=400, detail="Job already finished")

    update_video_job(job_id, status='error', error_message='Cancelled by user')
    return {"success": True, "message": "Job cancelled"}


@app.delete("/api/video/jobs/{job_id}")
async def delete_video_job_endpoint(job_id: int, user_id: int = Depends(get_current_user_id)):
    """Delete a video job (for cleanup/dismiss of finished jobs)."""
    from database import get_video_job, delete_video_job

    job = get_video_job(job_id, user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Video job not found")

    delete_video_job(job_id)
    return {"success": True, "message": "Job deleted"}


# ===== MAIN ENTRY POINT =====

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info"
    )
