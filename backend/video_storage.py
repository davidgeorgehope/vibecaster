"""
Shared video storage module.

This module provides a shared dictionary for storing processed videos
that need to be posted to social media platforms. Videos are stored
temporarily with an expiry time.
"""

import time
from typing import Dict

# Store processed videos for posting: {video_ref: {bytes, content_type, created_at, user_id}}
# This avoids sending huge base64 strings to the browser
processed_videos: Dict[str, dict] = {}

UPLOAD_EXPIRY_SECONDS = 30 * 60  # 30 minutes


def store_video(video_ref: str, video_bytes: bytes, content_type: str, user_id: int) -> None:
    """Store a processed video for later posting."""
    processed_videos[video_ref] = {
        'bytes': video_bytes,
        'content_type': content_type,
        'created_at': time.time(),
        'user_id': user_id
    }


def get_video(video_ref: str) -> dict | None:
    """Get a stored video by reference."""
    return processed_videos.get(video_ref)


def delete_video(video_ref: str) -> bool:
    """Delete a stored video."""
    if video_ref in processed_videos:
        del processed_videos[video_ref]
        return True
    return False


def cleanup_expired_videos() -> int:
    """Remove videos older than UPLOAD_EXPIRY_SECONDS. Returns count of removed videos."""
    now = time.time()
    expired = [
        video_ref for video_ref, data in processed_videos.items()
        if now - data.get('created_at', 0) > UPLOAD_EXPIRY_SECONDS
    ]
    for video_ref in expired:
        del processed_videos[video_ref]
    return len(expired)
