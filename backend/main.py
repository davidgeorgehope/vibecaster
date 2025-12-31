import os
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
import uvicorn

# Import local modules
from database import init_database, get_campaign, update_campaign, get_connection_status
from agents import analyze_user_prompt, run_agent_cycle, generate_from_url, generate_from_url_stream, post_url_content, chat_post_builder_stream, parse_generated_posts, generate_image_for_post_builder
from transcription import transcribe_media_stream, SUPPORTED_MIME_TYPES
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


class CampaignResponse(BaseModel):
    user_prompt: str
    refined_persona: str
    visual_style: str
    schedule_cron: str
    last_run: int


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
    """
    try:
        # Analyze user prompt with AI
        logger.info(f"Analyzing prompt: {request.user_prompt}")
        refined_persona, visual_style = analyze_user_prompt(request.user_prompt)

        # Update campaign in database
        update_campaign(
            user_id=user_id,
            user_prompt=request.user_prompt,
            refined_persona=refined_persona,
            visual_style=visual_style,
            schedule_cron=request.schedule_cron
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
                "schedule_cron": request.schedule_cron
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


# ===== MAIN ENTRY POINT =====

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info"
    )
