"""
Transcription module for audio/video processing using Gemini.
Handles file upload, transcription, summarization, and blog post generation.
"""

import os
import json
import time
import threading
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


def upload_to_gemini(file_bytes: bytes, filename: str, mime_type: str, on_progress=None):
    """
    Upload file to Gemini for processing.

    For small files (<20MB): Returns Part.from_bytes() directly
    For large files: Writes to temp file, uploads via Files API, waits for ACTIVE state

    Args:
        file_bytes: Raw file bytes
        filename: Original filename (for extension/display)
        mime_type: MIME type of the file
        on_progress: Optional callback(message) for progress updates

    Returns:
        tuple: (media_part, uploaded_file_or_none)
        - media_part: The Part object to use in generate_content
        - uploaded_file: The File object if uploaded (for cleanup), or None
    """
    import tempfile

    if len(file_bytes) <= INLINE_SIZE_LIMIT:
        # Small file - use inline bytes
        logger.info(f"[Gemini] Using inline bytes ({len(file_bytes)} bytes)")
        return types.Part.from_bytes(data=file_bytes, mime_type=mime_type), None

    # Large file - write to temp file and upload via Files API
    logger.info(f"[Gemini] Using Files API for large file ({len(file_bytes)} bytes)")

    if on_progress:
        on_progress("Uploading to Gemini...")

    ext = os.path.splitext(filename)[1] or '.mp4'
    temp_file_path = None

    try:
        # Write to temp file
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(file_bytes)
            temp_file_path = tmp.name

        # Upload to Gemini
        uploaded_file = client.files.upload(
            file=temp_file_path,
            config=types.UploadFileConfig(
                display_name=filename,
                mime_type=mime_type
            )
        )

    finally:
        # Clean up temp file immediately after upload
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)

    # Wait for file to become ACTIVE
    logger.info(f"[Gemini] Waiting for file {uploaded_file.name} to become ACTIVE...")
    while uploaded_file.state.name == "PROCESSING":
        if on_progress:
            on_progress("Processing file on Gemini...")
        time.sleep(5)
        uploaded_file = client.files.get(name=uploaded_file.name)

    if uploaded_file.state.name != "ACTIVE":
        raise Exception(f"File processing failed: {uploaded_file.state.name}")

    logger.info(f"[Gemini] File {uploaded_file.name} is now ACTIVE")
    return uploaded_file, uploaded_file


def cleanup_gemini_file(uploaded_file):
    """Clean up an uploaded file from Gemini."""
    if uploaded_file:
        try:
            client.files.delete(name=uploaded_file.name)
            logger.info(f"[Gemini] Deleted file: {uploaded_file.name}")
        except Exception as e:
            logger.warning(f"[Gemini] Failed to delete file: {e}")


def emit_event(event_type: str, **kwargs) -> str:
    """Create a JSON event string for SSE streaming."""
    event = {
        "type": event_type,
        "timestamp": time.time(),
        **kwargs
    }
    return json.dumps(event)


class _KeepaliveTask:
    """
    Run a blocking function with keepalive events for SSE streaming.

    Usage:
        task = _KeepaliveTask(lambda: slow_function(), "Processing")
        for keepalive in task.run():
            yield keepalive
        result = task.result
    """
    def __init__(self, func, step_name: str, keepalive_interval: int = 15):
        self.func = func
        self.step_name = step_name
        self.keepalive_interval = keepalive_interval
        self.result = None
        self._error = None

    def run(self):
        done = threading.Event()

        def worker():
            try:
                self.result = self.func()
            except Exception as e:
                self._error = e
            finally:
                done.set()

        thread = threading.Thread(target=worker)
        thread.start()

        keepalive_count = 0
        while not done.wait(timeout=self.keepalive_interval):
            keepalive_count += 1
            yield emit_event("keepalive", step=self.step_name,
                            message=f"{self.step_name}... ({keepalive_count * self.keepalive_interval}s)")

        if self._error:
            raise self._error


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

        # Step 1: Upload/prepare file for Gemini (with keepalives)
        yield emit_event("progress", step="uploading", message="Preparing file...")

        upload_task = _KeepaliveTask(
            lambda: upload_to_gemini(file_bytes, filename, mime_type),
            "Uploading file"
        )
        for keepalive in upload_task.run():
            yield keepalive
        media_part, uploaded_file = upload_task.result

        # Step 2: Transcribe (with keepalives)
        yield emit_event("progress", step="transcribing", message="Transcribing audio...")

        transcribe_task = _KeepaliveTask(
            lambda: client.models.generate_content(
                model=LLM_MODEL,
                contents=[
                    "Generate a complete, accurate, verbatim transcript of this audio/video. "
                    "Include all spoken words exactly as said. Do not summarize or paraphrase. "
                    "If there are multiple speakers, indicate speaker changes where possible.",
                    media_part
                ]
            ),
            "Transcribing"
        )
        for keepalive in transcribe_task.run():
            yield keepalive
        transcript_response = transcribe_task.result
        transcript = transcript_response.text.strip()
        logger.info(f"[Transcribe] Transcript generated: {len(transcript)} chars")

        yield emit_event("transcript", transcript=transcript)

        # Step 3: Generate summary (with keepalives)
        yield emit_event("progress", step="summarizing", message="Generating summary...")

        summary_task = _KeepaliveTask(
            lambda: client.models.generate_content(
                model=LLM_MODEL,
                contents=[
                    f"Based on this transcript, write a concise summary (3-5 paragraphs) that captures "
                    f"the key points, main topics discussed, and any important conclusions or takeaways.\n\n"
                    f"TRANSCRIPT:\n{transcript}"
                ]
            ),
            "Summarizing"
        )
        for keepalive in summary_task.run():
            yield keepalive
        summary_response = summary_task.result
        summary = summary_response.text.strip()
        logger.info(f"[Transcribe] Summary generated: {len(summary)} chars")

        yield emit_event("summary", summary=summary)

        # Step 4: Generate blog post (with keepalives)
        yield emit_event("progress", step="generating_blog", message="Generating blog post...")

        blog_task = _KeepaliveTask(
            lambda: client.models.generate_content(
                model=LLM_MODEL,
                contents=[
                    f"Write a standalone blog post about the topics and ideas discussed below. "
                    f"The blog should read as an original article - do NOT reference the video, "
                    f"transcript, speaker, or recording. Write as if these are your own insights "
                    f"and expertise on the subject.\n\n"
                    f"Include:\n"
                    f"- An engaging title\n"
                    f"- An introduction that hooks the reader\n"
                    f"- Main content organized into clear sections with headers\n"
                    f"- A conclusion with key takeaways\n\n"
                    f"Make it informative, engaging, and easy to read. Use markdown formatting.\n\n"
                    f"SOURCE MATERIAL:\n{transcript}"
                ]
            ),
            "Generating blog post"
        )
        for keepalive in blog_task.run():
            yield keepalive
        blog_response = blog_task.result
        blog_post = blog_response.text.strip()
        logger.info(f"[Transcribe] Blog post generated: {len(blog_post)} chars")

        yield emit_event("blog_post", blog_post=blog_post)

        # Done
        yield emit_event("complete")
        logger.info(f"[Transcribe] User {user_id} transcription complete")

    except Exception as e:
        # Truncate error to avoid logging/sending huge binary data
        error_msg = str(e)[:500] if len(str(e)) > 500 else str(e)
        if len(str(e)) > 1000:
            logger.error(f"[Transcribe] Error for user {user_id}: {type(e).__name__} (message truncated, {len(str(e))} chars)")
        else:
            logger.error(f"[Transcribe] Error for user {user_id}: {error_msg}")
        yield emit_event("error", message=error_msg)

    finally:
        # Clean up uploaded file from Gemini if we used Files API
        cleanup_gemini_file(uploaded_file)
