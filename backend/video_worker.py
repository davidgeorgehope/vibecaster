"""
Background video generation worker.

Runs video generation in a background thread, independent of HTTP request lifecycle.
All events are persisted to SQLite for SSE replay on reconnection.
"""

import threading
import logging
from typing import Dict, Optional

logger = logging.getLogger("vibecaster.video_worker")

# Thread registry - tracks running job threads (not events, those go to DB)
_active_jobs: Dict[int, threading.Thread] = {}
_lock = threading.Lock()


def start_video_job(
    job_id: int,
    user_id: int,
    topic: str,
    style: str = "educational",
    target_duration: int = 30,
    user_prompt: str = "",
    aspect_ratio: str = "16:9"
) -> bool:
    """
    Start video generation in a background thread.

    Events are written to database as they occur.
    Returns True if job was started, False if already running.
    """
    with _lock:
        if job_id in _active_jobs:
            logger.warning(f"Job {job_id} already running, not starting again")
            return False

        thread = threading.Thread(
            target=_run_video_job,
            args=(job_id, user_id, topic, style, target_duration, user_prompt, aspect_ratio),
            daemon=True,
            name=f"video-job-{job_id}"
        )
        _active_jobs[job_id] = thread
        thread.start()
        logger.info(f"Started background video job {job_id}")
        return True


def _run_video_job(
    job_id: int,
    user_id: int,
    topic: str,
    style: str,
    target_duration: int,
    user_prompt: str,
    aspect_ratio: str = "16:9"
):
    """Worker function that runs in background thread."""
    from video_generation import generate_video_stream
    from database import save_job_event, update_video_job

    try:
        logger.info(f"Background job {job_id} starting generation (aspect_ratio={aspect_ratio})")

        for event_json in generate_video_stream(
            user_id=user_id,
            topic=topic,
            style=style,
            target_duration=target_duration,
            user_prompt=user_prompt,
            job_id=job_id,  # Pass existing job_id to skip creation
            aspect_ratio=aspect_ratio
        ):
            # Persist event to database for SSE consumers
            save_job_event(job_id, event_json)

        logger.info(f"Background job {job_id} completed successfully")

    except Exception as e:
        logger.exception(f"Background job {job_id} failed with error: {e}")
        # Mark job as error in database
        try:
            update_video_job(job_id, status="error", error_message=str(e))
            # Also save error event for SSE consumers
            import json
            import time
            error_event = json.dumps({
                "type": "error",
                "message": f"Background job failed: {str(e)}",
                "timestamp": time.time()
            })
            save_job_event(job_id, error_event)
        except Exception as db_error:
            logger.error(f"Failed to update job {job_id} error status: {db_error}")
    finally:
        with _lock:
            _active_jobs.pop(job_id, None)
            logger.info(f"Background job {job_id} removed from active jobs")


def is_job_running(job_id: int) -> bool:
    """Check if a job is currently running in a background thread."""
    with _lock:
        return job_id in _active_jobs


def get_running_jobs() -> list:
    """Get list of currently running job IDs."""
    with _lock:
        return list(_active_jobs.keys())


def cancel_job(job_id: int) -> bool:
    """
    Request cancellation of a running job.

    Note: This doesn't immediately stop the thread, but the job should
    check for cancellation at appropriate points.

    Returns True if job was found and cancellation requested.
    """
    # For now, we don't have a cancellation mechanism in the generator
    # This would require adding a cancellation check in the generate loop
    with _lock:
        if job_id in _active_jobs:
            logger.info(f"Cancellation requested for job {job_id}")
            # TODO: Implement proper cancellation via threading.Event
            return True
        return False
