import os
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
import uvicorn

# Import local modules
from database import init_database, get_campaign, update_campaign, get_connection_status
from agents import analyze_user_prompt, run_agent_cycle
from auth import router as auth_router
from user_auth import router as user_auth_router
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(user_auth_router)
app.include_router(auth_router)

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


# ===== MAIN ENTRY POINT =====

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info"
    )
