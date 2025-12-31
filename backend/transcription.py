"""
Transcription module for audio/video processing using Gemini.
Handles file upload, transcription, summarization, and blog post generation.
"""

import os
import json
import time
from typing import Generator
from google import genai
from google.genai import types
from dotenv import load_dotenv
from logger_config import agent_logger as logger

load_dotenv()

# Initialize Gemini client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Model for transcription and generation
LLM_MODEL = "gemini-3-pro-preview"

# Supported MIME types
SUPPORTED_AUDIO = {
    "audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav",
    "audio/aac", "audio/ogg", "audio/flac", "audio/aiff"
}
SUPPORTED_VIDEO = {
    "video/mp4", "video/webm", "video/quicktime", "video/x-m4v"
}
SUPPORTED_MIME_TYPES = SUPPORTED_AUDIO | SUPPORTED_VIDEO

# Size threshold for using Files API vs inline bytes (20MB)
INLINE_SIZE_LIMIT = 20 * 1024 * 1024


def emit_event(event_type: str, **kwargs) -> str:
    """Create a JSON event string for SSE streaming."""
    event = {
        "type": event_type,
        "timestamp": time.time(),
        **kwargs
    }
    return json.dumps(event)


def transcribe_media_stream(
    user_id: int,
    file_bytes: bytes,
    filename: str,
    mime_type: str
) -> Generator[str, None, None]:
    """
    Stream transcription and content generation from audio/video.

    Yields SSE events for progress updates, transcript, summary, blog post.
    File bytes are processed in memory - no disk storage.

    Args:
        user_id: User ID for logging
        file_bytes: Raw file bytes
        filename: Original filename
        mime_type: MIME type of the file

    Yields:
        JSON event strings for SSE streaming
    """
    logger.info(f"[Transcribe] User {user_id} starting transcription of {filename} ({len(file_bytes)} bytes)")

    uploaded_file = None

    try:
        # Validate MIME type
        if mime_type not in SUPPORTED_MIME_TYPES:
            yield emit_event("error", message=f"Unsupported file type: {mime_type}")
            return

        # Step 1: Upload/prepare file for Gemini
        yield emit_event("progress", step="uploading", message="Preparing file...")

        if len(file_bytes) > INLINE_SIZE_LIMIT:
            # Use Files API for large files
            logger.info(f"[Transcribe] Using Files API for large file ({len(file_bytes)} bytes)")
            yield emit_event("progress", step="uploading", message="Uploading to Gemini...")

            uploaded_file = client.files.upload(
                file=file_bytes,
                config=types.UploadFileConfig(
                    display_name=filename,
                    mime_type=mime_type
                )
            )
            media_part = uploaded_file
            logger.info(f"[Transcribe] File uploaded: {uploaded_file.name}")
        else:
            # Use inline bytes for smaller files
            logger.info(f"[Transcribe] Using inline bytes ({len(file_bytes)} bytes)")
            media_part = types.Part.from_bytes(data=file_bytes, mime_type=mime_type)

        # Step 2: Transcribe
        yield emit_event("progress", step="transcribing", message="Transcribing audio...")

        transcript_response = client.models.generate_content(
            model=LLM_MODEL,
            contents=[
                "Generate a complete, accurate, verbatim transcript of this audio/video. "
                "Include all spoken words exactly as said. Do not summarize or paraphrase. "
                "If there are multiple speakers, indicate speaker changes where possible.",
                media_part
            ]
        )
        transcript = transcript_response.text.strip()
        logger.info(f"[Transcribe] Transcript generated: {len(transcript)} chars")

        yield emit_event("transcript", transcript=transcript)

        # Step 3: Generate summary
        yield emit_event("progress", step="summarizing", message="Generating summary...")

        summary_response = client.models.generate_content(
            model=LLM_MODEL,
            contents=[
                f"Based on this transcript, write a concise summary (3-5 paragraphs) that captures "
                f"the key points, main topics discussed, and any important conclusions or takeaways.\n\n"
                f"TRANSCRIPT:\n{transcript}"
            ]
        )
        summary = summary_response.text.strip()
        logger.info(f"[Transcribe] Summary generated: {len(summary)} chars")

        yield emit_event("summary", summary=summary)

        # Step 4: Generate blog post
        yield emit_event("progress", step="generating_blog", message="Generating blog post...")

        blog_response = client.models.generate_content(
            model=LLM_MODEL,
            contents=[
                f"Based on this transcript, write a well-structured blog post. Include:\n"
                f"- An engaging title\n"
                f"- An introduction that hooks the reader\n"
                f"- Main content organized into clear sections with headers\n"
                f"- A conclusion with key takeaways\n\n"
                f"Make it informative, engaging, and easy to read. Use markdown formatting.\n\n"
                f"TRANSCRIPT:\n{transcript}"
            ]
        )
        blog_post = blog_response.text.strip()
        logger.info(f"[Transcribe] Blog post generated: {len(blog_post)} chars")

        yield emit_event("blog_post", blog_post=blog_post)

        # Done
        yield emit_event("complete")
        logger.info(f"[Transcribe] User {user_id} transcription complete")

    except Exception as e:
        logger.error(f"[Transcribe] Error for user {user_id}: {e}", exc_info=True)
        yield emit_event("error", message=str(e))

    finally:
        # Clean up uploaded file from Gemini if we used Files API
        if uploaded_file:
            try:
                client.files.delete(name=uploaded_file.name)
                logger.info(f"[Transcribe] Deleted uploaded file: {uploaded_file.name}")
            except Exception as e:
                logger.warning(f"[Transcribe] Failed to delete uploaded file: {e}")
