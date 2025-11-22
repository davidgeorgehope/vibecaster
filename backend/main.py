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

load_dotenv()

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

def setup_scheduler():
    """Configure and start the scheduler with the current campaign settings."""
    try:
        # Remove existing jobs
        scheduler.remove_all_jobs()

        # Get campaign configuration
        campaign = get_campaign()
        if campaign and campaign.get("user_prompt"):
            cron_schedule = campaign.get("schedule_cron", "0 9 * * *")

            # Parse cron schedule (minute hour day month day_of_week)
            parts = cron_schedule.split()
            if len(parts) == 5:
                minute, hour, day, month, day_of_week = parts

                # Add job to scheduler
                scheduler.add_job(
                    run_agent_cycle,
                    trigger=CronTrigger(
                        minute=minute,
                        hour=hour,
                        day=day,
                        month=month,
                        day_of_week=day_of_week
                    ),
                    id="agent_cycle",
                    name="Vibecaster Agent Cycle",
                    replace_existing=True
                )

                print(f"Scheduler configured with cron: {cron_schedule}")
            else:
                print(f"Invalid cron schedule: {cron_schedule}")
        else:
            print("No campaign configured. Scheduler not started.")

    except Exception as e:
        print(f"Error setting up scheduler: {e}")


# ===== LIFECYCLE EVENTS =====

@app.on_event("startup")
async def startup_event():
    """Initialize database and scheduler on startup."""
    print("Starting Vibecaster API...")

    # Initialize database
    init_database()
    print("Database initialized")

    # Start scheduler
    scheduler.start()
    print("Scheduler started")

    # Configure scheduler with existing campaign
    setup_scheduler()


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    print("Shutting down Vibecaster API...")
    scheduler.shutdown()
    print("Scheduler stopped")


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
        print(f"Analyzing prompt: {request.user_prompt}")
        refined_persona, visual_style = analyze_user_prompt(request.user_prompt)

        # Update campaign in database
        update_campaign(
            user_id=user_id,
            user_prompt=request.user_prompt,
            refined_persona=refined_persona,
            visual_style=visual_style,
            schedule_cron=request.schedule_cron
        )

        # Reconfigure scheduler
        setup_scheduler()

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

        # Remove scheduler jobs
        scheduler.remove_all_jobs()

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
