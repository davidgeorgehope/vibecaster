"""
Song to Video Module - Generate karaoke-style videos from audio files.

Provides functionality for:
- Transcribing songs with word-level timestamps using Gemini
- Generating cover art based on lyrics mood
- Creating videos with karaoke-style captions using FFmpeg + ASS subtitles
- SSE streaming for progress updates
"""

import os
import time
import json
import tempfile
import subprocess
from typing import Generator, Optional, Dict, List, Any
from io import BytesIO
from google import genai
from google.genai import types
from PIL import Image
from dotenv import load_dotenv
from logger_config import agent_logger as logger

load_dotenv()

# Initialize Google GenAI client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Models
LLM_MODEL = "gemini-3-pro-preview"
IMAGE_MODEL = "gemini-3-pro-image-preview"

# Supported audio MIME types
SUPPORTED_AUDIO_TYPES = {
    "audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav",
    "audio/mp4", "audio/ogg", "audio/aac", "audio/flac"
}


def emit_event(event_type: str, **kwargs) -> str:
    """Create a JSON event string for SSE streaming."""
    event = {
        "type": event_type,
        "timestamp": time.time(),
        **kwargs
    }
    return json.dumps(event)


def get_audio_duration(audio_bytes: bytes, mime_type: str) -> float:
    """Get audio duration in seconds using FFmpeg."""
    # Determine file extension from mime type
    ext_map = {
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/mp4": ".m4a",
        "audio/ogg": ".ogg",
        "audio/aac": ".aac",
        "audio/flac": ".flac",
    }
    ext = ext_map.get(mime_type, ".mp3")

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", tmp_path],
            capture_output=True, text=True, timeout=30
        )
        return float(result.stdout.strip())
    except Exception as e:
        logger.warning(f"Failed to get audio duration: {e}")
        return 180.0  # Default to 3 minutes
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def transcribe_song_with_timestamps(audio_bytes: bytes, mime_type: str, filename: str) -> Dict[str, Any]:
    """
    Transcribe a song with word-level timestamps using Gemini.

    Args:
        audio_bytes: Raw audio file bytes
        mime_type: MIME type of the audio
        filename: Original filename

    Returns:
        Dict with:
        - title: Detected song title (if known)
        - mood: Emotional tone of the song
        - lyrics: Full lyrics text
        - words: List of {word, start_ms, end_ms} dicts
    """
    from transcription import upload_to_gemini, cleanup_gemini_file

    logger.info(f"[SongVideo] Transcribing song: {filename} ({len(audio_bytes)} bytes)")

    # Upload audio to Gemini
    media_part, uploaded_file = upload_to_gemini(audio_bytes, filename, mime_type)

    try:
        prompt = """Transcribe this song with precise word-level timestamps.

Listen carefully to the audio and provide timestamps for when each word starts and ends.
Be as accurate as possible with the timing - this will be used for karaoke-style captions.

Return as JSON with this exact structure:
{
  "title": "detected song title if recognizable, otherwise null",
  "artist": "detected artist if recognizable, otherwise null",
  "mood": "emotional tone (e.g., energetic, melancholic, upbeat, romantic, angry, peaceful)",
  "lyrics": "full lyrics text with line breaks",
  "words": [
    {"word": "Hello", "start_ms": 1000, "end_ms": 1400},
    {"word": "world", "start_ms": 1450, "end_ms": 1900}
  ]
}

IMPORTANT:
- Timestamps are in milliseconds from the start of the audio
- Include ALL words, including repeated phrases and choruses
- If a word is held/stretched, reflect that in the end_ms
- For instrumental sections, you can skip to the next lyric
- Keep punctuation with words where appropriate
- Include newlines in the "lyrics" field to show verse/line structure

Return ONLY valid JSON, no other text."""

        response = client.models.generate_content(
            model=LLM_MODEL,
            contents=[prompt, media_part],
            config=types.GenerateContentConfig(
                temperature=0.3,
                response_mime_type="application/json"
            )
        )

        if hasattr(response, 'text') and response.text:
            result = json.loads(response.text)
            logger.info(f"[SongVideo] Transcription complete: {len(result.get('words', []))} words, mood: {result.get('mood')}")
            return result

        logger.error("No text in transcription response")
        return {"title": None, "mood": "unknown", "lyrics": "", "words": []}

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse transcription JSON: {e}")
        # Try to extract raw text as fallback
        if hasattr(response, 'text'):
            return {"title": None, "mood": "unknown", "lyrics": response.text[:2000], "words": []}
        return {"title": None, "mood": "unknown", "lyrics": "", "words": []}
    except Exception as e:
        logger.error(f"Error transcribing song: {e}", exc_info=True)
        raise
    finally:
        cleanup_gemini_file(uploaded_file)


def generate_song_cover_image(lyrics: str, mood: str, title: Optional[str] = None) -> Optional[bytes]:
    """
    Generate album/cover art based on the song's lyrics and mood.

    Args:
        lyrics: Song lyrics text
        mood: Emotional tone of the song
        title: Optional song title

    Returns:
        Image bytes (PNG) or None if generation fails
    """
    logger.info(f"[SongVideo] Generating cover image for mood: {mood}")

    # Extract key themes from lyrics for the image prompt
    lyrics_excerpt = lyrics[:500] if len(lyrics) > 500 else lyrics

    prompt = f"""Create album cover art for a song with this mood: {mood}

{f'Song title: {title}' if title else ''}

Key lyrics for inspiration:
{lyrics_excerpt}

Create a visually striking, artistic album cover that captures the emotional essence of these lyrics.
The image should:
- Be suitable as a square album cover (1080x1080)
- Have strong visual impact
- Convey the mood: {mood}
- NOT contain any text or words
- Be original and artistic, not a photograph of real people
- Use colors and imagery that match the emotional tone

Style: Modern album artwork, digital art, cinematic lighting, high quality"""

    try:
        response = client.models.generate_content(
            model=IMAGE_MODEL,
            contents=[prompt],
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"]
            )
        )

        # Extract image from response
        if hasattr(response, 'candidates'):
            for candidate in response.candidates:
                if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                    for part in candidate.content.parts:
                        if hasattr(part, 'inline_data') and part.inline_data:
                            if hasattr(part.inline_data, 'data') and part.inline_data.data:
                                logger.info(f"[SongVideo] Cover image generated ({len(part.inline_data.data)} bytes)")
                                return part.inline_data.data

                        if hasattr(part, 'as_image'):
                            try:
                                image = part.as_image()
                                if image and hasattr(image, 'save'):
                                    img_byte_arr = BytesIO()
                                    image.save(img_byte_arr, format='PNG')
                                    return img_byte_arr.getvalue()
                            except Exception as e:
                                logger.warning(f"as_image() method failed: {e}")

        logger.warning("No image found in response")
        return None

    except Exception as e:
        logger.error(f"Error generating cover image: {e}", exc_info=True)
        return None


def create_ass_subtitle_file(words: List[Dict], duration_seconds: float) -> str:
    """
    Create an ASS subtitle file with karaoke timing tags.

    Args:
        words: List of {word, start_ms, end_ms} dicts
        duration_seconds: Total audio duration

    Returns:
        ASS subtitle file content as string
    """
    # ASS header with karaoke style
    # Using a style optimized for readability: white text with black outline
    ass_content = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,Arial,72,&H00FFFFFF,&H000088FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,50,50,80,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    if not words:
        return ass_content

    # Group words into lines (roughly 6-8 words per line, or by timing gaps)
    lines = []
    current_line = []
    last_end_ms = 0

    for word_data in words:
        word = word_data.get('word', '')
        start_ms = word_data.get('start_ms', 0)
        end_ms = word_data.get('end_ms', start_ms + 500)

        # Start new line if:
        # 1. Gap > 1.5 seconds between words
        # 2. Current line has 8+ words
        # 3. Word contains newline indicator
        gap = start_ms - last_end_ms if last_end_ms > 0 else 0

        if current_line and (gap > 1500 or len(current_line) >= 8):
            lines.append(current_line)
            current_line = []

        current_line.append({
            'word': word,
            'start_ms': start_ms,
            'end_ms': end_ms,
            'duration_cs': max(1, (end_ms - start_ms) // 10)  # Duration in centiseconds for \k tag
        })
        last_end_ms = end_ms

    if current_line:
        lines.append(current_line)

    # Generate dialogue lines with karaoke tags
    for line_words in lines:
        if not line_words:
            continue

        line_start_ms = line_words[0]['start_ms']
        line_end_ms = line_words[-1]['end_ms']

        # Add padding for readability
        display_start_ms = max(0, line_start_ms - 200)
        display_end_ms = min(int(duration_seconds * 1000), line_end_ms + 500)

        # Format times as H:MM:SS.cc
        def ms_to_ass_time(ms):
            total_seconds = ms / 1000
            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)
            seconds = total_seconds % 60
            return f"{hours}:{minutes:02d}:{seconds:05.2f}"

        start_time = ms_to_ass_time(display_start_ms)
        end_time = ms_to_ass_time(display_end_ms)

        # Build karaoke text with \k tags
        # \k<duration> means "highlight this text for <duration> centiseconds"
        karaoke_text = ""
        for i, wd in enumerate(line_words):
            # Add delay before first word if needed
            if i == 0 and wd['start_ms'] > display_start_ms:
                delay_cs = (wd['start_ms'] - display_start_ms) // 10
                if delay_cs > 0:
                    karaoke_text += f"{{\\k{delay_cs}}}"

            karaoke_text += f"{{\\kf{wd['duration_cs']}}}{wd['word']} "

        karaoke_text = karaoke_text.strip()

        ass_content += f"Dialogue: 0,{start_time},{end_time},Karaoke,,0,0,0,,{karaoke_text}\n"

    return ass_content


def create_karaoke_video(
    image_bytes: bytes,
    audio_bytes: bytes,
    words: List[Dict],
    audio_duration: float,
    mime_type: str
) -> Optional[bytes]:
    """
    Create a video with karaoke-style captions using FFmpeg.

    Args:
        image_bytes: Cover image bytes (PNG)
        audio_bytes: Audio file bytes
        words: List of {word, start_ms, end_ms} dicts for timing
        audio_duration: Audio duration in seconds
        mime_type: Audio MIME type

    Returns:
        Video bytes (MP4) or None if creation fails
    """
    logger.info(f"[SongVideo] Creating karaoke video ({audio_duration:.1f}s)")

    # Determine audio extension
    ext_map = {
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/mp4": ".m4a",
        "audio/ogg": ".ogg",
        "audio/aac": ".aac",
        "audio/flac": ".flac",
    }
    audio_ext = ext_map.get(mime_type, ".mp3")

    # Create temp files
    tmp_image = None
    tmp_audio = None
    tmp_ass = None
    tmp_video = None

    try:
        # Write image
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            f.write(image_bytes)
            tmp_image = f.name

        # Write audio
        with tempfile.NamedTemporaryFile(suffix=audio_ext, delete=False) as f:
            f.write(audio_bytes)
            tmp_audio = f.name

        # Create ASS subtitle file
        ass_content = create_ass_subtitle_file(words, audio_duration)
        with tempfile.NamedTemporaryFile(suffix='.ass', delete=False, mode='w', encoding='utf-8') as f:
            f.write(ass_content)
            tmp_ass = f.name

        # Output video path
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
            tmp_video = f.name

        # Resize image to 1920x1080 (16:9) with padding if needed
        # Then overlay subtitles and add audio
        # Using -shortest to match audio duration

        ffmpeg_cmd = [
            'ffmpeg', '-y',
            '-loop', '1',  # Loop the image
            '-i', tmp_image,
            '-i', tmp_audio,
            '-filter_complex',
            f"[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,ass={tmp_ass}[v]",
            '-map', '[v]',
            '-map', '1:a',
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-crf', '23',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-shortest',  # End when shortest stream ends (audio)
            '-movflags', '+faststart',
            tmp_video
        ]

        logger.info(f"[SongVideo] Running FFmpeg: {' '.join(ffmpeg_cmd[:10])}...")

        result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )

        if result.returncode != 0:
            logger.error(f"FFmpeg error: {result.stderr}")
            return None

        # Read output video
        with open(tmp_video, 'rb') as f:
            video_bytes = f.read()

        logger.info(f"[SongVideo] Video created: {len(video_bytes)} bytes")
        return video_bytes

    except subprocess.TimeoutExpired:
        logger.error("FFmpeg timed out")
        return None
    except Exception as e:
        logger.error(f"Error creating karaoke video: {e}", exc_info=True)
        return None
    finally:
        # Cleanup temp files
        for tmp_path in [tmp_image, tmp_audio, tmp_ass, tmp_video]:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except:
                    pass


def generate_song_video_stream(
    user_id: int,
    audio_bytes: bytes,
    filename: str,
    mime_type: str
) -> Generator[str, None, None]:
    """
    Full song-to-video pipeline with SSE progress streaming.

    Yields SSE events:
    - progress: Current step (transcribing, generating_image, composing_video, generating_posts)
    - keepalive: Connection keepalive during long operations
    - lyrics: Full lyrics text
    - image_ready: Cover image generated (base64 preview)
    - video_ready: Video composed (video_ref for posting)
    - x_post, linkedin_post, youtube: Generated promotional posts
    - complete: All done
    - error: Something went wrong

    Args:
        user_id: User ID for database storage
        audio_bytes: Raw audio file bytes
        filename: Original filename
        mime_type: Audio MIME type

    Yields:
        SSE event strings
    """
    import threading
    import base64

    logger.info(f"[SongVideo] Starting pipeline for user {user_id}: {filename}")

    try:
        # Step 1: Get audio duration
        yield emit_event("progress", step="analyzing", message="Analyzing audio...")

        audio_duration = get_audio_duration(audio_bytes, mime_type)
        logger.info(f"[SongVideo] Audio duration: {audio_duration:.1f}s")

        # Step 2: Transcribe with timestamps (with keepalives)
        yield emit_event("progress", step="transcribing", message="Transcribing lyrics...")

        transcribe_result = {'data': None, 'error': None}
        transcribe_done = threading.Event()

        def do_transcribe():
            try:
                transcribe_result['data'] = transcribe_song_with_timestamps(
                    audio_bytes, mime_type, filename
                )
            except Exception as e:
                transcribe_result['error'] = e
            finally:
                transcribe_done.set()

        thread = threading.Thread(target=do_transcribe)
        thread.start()

        keepalive_count = 0
        while not transcribe_done.wait(timeout=15):
            keepalive_count += 1
            yield emit_event("keepalive", step="transcribing",
                           message=f"Transcribing lyrics... ({keepalive_count * 15}s)")

        if transcribe_result['error']:
            raise transcribe_result['error']

        transcription = transcribe_result['data']
        lyrics = transcription.get('lyrics', '')
        words = transcription.get('words', [])
        mood = transcription.get('mood', 'unknown')
        title = transcription.get('title')

        # Yield lyrics
        yield emit_event("lyrics",
                        lyrics=lyrics,
                        mood=mood,
                        title=title,
                        word_count=len(words))

        # Step 3: Generate cover image (with keepalives)
        yield emit_event("progress", step="generating_image", message="Creating cover art...")

        image_result = {'data': None, 'error': None}
        image_done = threading.Event()

        def do_generate_image():
            try:
                image_result['data'] = generate_song_cover_image(lyrics, mood, title)
            except Exception as e:
                image_result['error'] = e
            finally:
                image_done.set()

        thread = threading.Thread(target=do_generate_image)
        thread.start()

        keepalive_count = 0
        while not image_done.wait(timeout=15):
            keepalive_count += 1
            yield emit_event("keepalive", step="generating_image",
                           message=f"Creating cover art... ({keepalive_count * 15}s)")

        if image_result['error']:
            raise image_result['error']

        image_bytes = image_result['data']
        if not image_bytes:
            raise Exception("Failed to generate cover image")

        # Yield image preview
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        yield emit_event("image_ready", image_base64=image_base64)

        # Step 4: Create karaoke video (with keepalives)
        yield emit_event("progress", step="composing_video", message="Composing video with captions...")

        video_result = {'data': None, 'error': None}
        video_done = threading.Event()

        def do_create_video():
            try:
                video_result['data'] = create_karaoke_video(
                    image_bytes, audio_bytes, words, audio_duration, mime_type
                )
            except Exception as e:
                video_result['error'] = e
            finally:
                video_done.set()

        thread = threading.Thread(target=do_create_video)
        thread.start()

        keepalive_count = 0
        while not video_done.wait(timeout=15):
            keepalive_count += 1
            yield emit_event("keepalive", step="composing_video",
                           message=f"Composing video... ({keepalive_count * 15}s)")

        if video_result['error']:
            raise video_result['error']

        video_bytes = video_result['data']
        if not video_bytes:
            raise Exception("Failed to create video")

        # Store video for posting using shared storage module
        import uuid
        from video_storage import store_video

        video_ref = str(uuid.uuid4())
        store_video(video_ref, video_bytes, 'video/mp4', user_id)

        yield emit_event("video_ready",
                        video_ref=video_ref,
                        mime_type="video/mp4",
                        size_bytes=len(video_bytes),
                        duration_seconds=audio_duration)

        # Step 5: Generate promotional posts (with keepalives)
        yield emit_event("progress", step="generating_posts", message="Creating promotional posts...")

        posts_result = {'data': None, 'error': None}
        posts_done = threading.Event()

        def do_generate_posts():
            try:
                posts_result['data'] = generate_song_posts(lyrics, mood, title, user_id)
            except Exception as e:
                posts_result['error'] = e
            finally:
                posts_done.set()

        thread = threading.Thread(target=do_generate_posts)
        thread.start()

        keepalive_count = 0
        while not posts_done.wait(timeout=15):
            keepalive_count += 1
            yield emit_event("keepalive", step="generating_posts",
                           message=f"Generating posts... ({keepalive_count * 15}s)")

        if posts_result['error']:
            raise posts_result['error']

        posts = posts_result['data']

        # Yield posts
        if posts.get("x_post"):
            yield emit_event("x_post", x_post=posts['x_post'])

        if posts.get("linkedin_post"):
            yield emit_event("linkedin_post", linkedin_post=posts['linkedin_post'])

        if posts.get("youtube_title"):
            yield emit_event("youtube",
                           title=posts['youtube_title'],
                           description=posts.get('youtube_description', ''))

        # Complete
        yield emit_event("complete")
        logger.info(f"[SongVideo] Pipeline complete for user {user_id}")

    except Exception as e:
        error_msg = str(e)[:500] if len(str(e)) > 500 else str(e)
        logger.error(f"[SongVideo] Error for user {user_id}: {error_msg}")
        yield emit_event("error", message=error_msg)


def generate_song_posts(lyrics: str, mood: str, title: Optional[str], user_id: int) -> Dict[str, str]:
    """Generate promotional posts for a song video."""
    from database import get_campaign

    # Get campaign for persona context
    campaign = get_campaign(user_id)
    persona = campaign.get("refined_persona", "") if campaign else ""

    # Truncate lyrics for context
    lyrics_excerpt = lyrics[:2000] if len(lyrics) > 2000 else lyrics

    prompt = f"""Create social media posts for a music video with karaoke-style lyrics.

{f'SONG TITLE: {title}' if title else ''}
MOOD: {mood}
LYRICS EXCERPT:
{lyrics_excerpt}

{f'AUTHOR PERSONA: {persona}' if persona else ''}

Generate the following (output as JSON):
1. x_post: A tweet promoting this music video (max 280 chars, engaging, with relevant hashtags).
   The video is a karaoke-style lyric video. DO NOT include any links.
2. linkedin_post: A professional LinkedIn post about sharing this music/lyric video (2-3 paragraphs).
   Focus on the emotional journey or story behind the song. DO NOT include any links.
3. youtube_title: A compelling YouTube title (max 100 chars) - include "Lyric Video" in the title
4. youtube_description: A YouTube description (2-3 paragraphs) describing the song and lyric video

Output ONLY valid JSON with these four fields. No other text."""

    try:
        response = client.models.generate_content(
            model=LLM_MODEL,
            contents=[prompt],
            config=types.GenerateContentConfig(
                temperature=0.7,
                response_mime_type="application/json"
            )
        )
        result = json.loads(response.text)
        return result
    except Exception as e:
        logger.error(f"Error generating song posts: {e}")
        # Fallback
        display_title = title or "Music Video"
        return {
            "x_post": f"Check out this lyric video! #{mood.replace(' ', '')} #LyricVideo #Music",
            "linkedin_post": f"Excited to share this {mood} lyric video with you all.",
            "youtube_title": f"{display_title} | Lyric Video",
            "youtube_description": f"A {mood} song with karaoke-style lyrics.\n\nLyrics:\n{lyrics[:500]}..."
        }
