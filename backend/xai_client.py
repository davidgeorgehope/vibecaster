"""Thin xAI (Grok) API client used by every AI feature in Vibecaster.

Models (latest flagship tiers only):
  - TEXT_MODEL  grok-4.7                  text, JSON, vision, web search, tool calls
  - IMAGE_MODEL grok-imagine-image-2.0    image generation and reference-image edits
  - VIDEO_MODEL grok-imagine-video-1.5    image-to-video
  - STT         /v1/stt                   transcription with word timestamps + diarization
"""
import base64
import io
import json
import logging
import os
import subprocess
import tempfile
import time
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

API_BASE = "https://api.x.ai/v1"
TEXT_MODEL = "grok-4.7"
IMAGE_MODEL = "grok-imagine-image-2.0"
VIDEO_MODEL = "grok-imagine-video-1.5"

TEXT_TIMEOUT = 600
MEDIA_TIMEOUT = 300
VIDEO_POLL_INTERVAL = 5
VIDEO_MAX_WAIT = 900



class XaiError(RuntimeError):
    """Raised when the xAI API returns an error or an unusable response."""


def _headers() -> Dict[str, str]:
    key = os.getenv("XAI_API_KEY")
    if not key:
        raise XaiError("XAI_API_KEY is not set")
    return {"Authorization": f"Bearer {key}"}


def _post(path: str, body: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    r = httpx.post(f"{API_BASE}{path}", headers=_headers(), json=body, timeout=timeout)
    if r.status_code >= 400:
        raise XaiError(f"xAI {path} HTTP {r.status_code}: {r.text[:300]}")
    return r.json()


def _image_bytes(img: Any) -> bytes:
    if isinstance(img, (bytes, bytearray)):
        return bytes(img)
    buf = io.BytesIO()  # PIL image
    img.save(buf, format="PNG")
    return buf.getvalue()


def _mime(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:3] == b"GIF":
        return "image/gif"
    return "image/png"


def data_uri(data: bytes) -> str:
    return f"data:{_mime(data)};base64,{base64.b64encode(data).decode()}"


def _user_content(prompt: str, images: Optional[Sequence[Any]]) -> Any:
    if not images:
        return prompt
    parts: List[Dict[str, Any]] = [
        {"type": "image_url", "image_url": {"url": data_uri(_image_bytes(i)), "detail": "high"}}
        for i in images
    ]
    parts.append({"type": "text", "text": prompt})
    return parts


def generate_text(
    prompt: str,
    *,
    system: Optional[str] = None,
    json_mode: bool = False,
    temperature: Optional[float] = None,
    images: Optional[Sequence[Any]] = None,
) -> str:
    """Single-turn chat completion on grok-4.7. Returns the message text."""
    messages: List[Dict[str, Any]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": _user_content(prompt, images)})
    body: Dict[str, Any] = {"model": TEXT_MODEL, "messages": messages}
    if temperature is not None:
        body["temperature"] = temperature
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    data = _post("/chat/completions", body, TEXT_TIMEOUT)
    text = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    if not text.strip():
        raise XaiError("xAI returned an empty completion")
    return text


def web_search(
    prompt: str,
    *,
    system: Optional[str] = None,
    temperature: Optional[float] = None,
) -> Tuple[str, List[Dict[str, str]]]:
    """grok-4.7 with live web search (Responses API).

    Returns (text, sources) where sources is a de-duplicated list of {"url", "title"}
    taken from the url_citation annotations.
    """
    inputs: List[Dict[str, Any]] = []
    if system:
        inputs.append({"role": "system", "content": system})
    inputs.append({"role": "user", "content": prompt})
    body: Dict[str, Any] = {"model": TEXT_MODEL, "input": inputs, "tools": [{"type": "web_search"}]}
    if temperature is not None:
        body["temperature"] = temperature
    data = _post("/responses", body, TEXT_TIMEOUT)
    texts: List[str] = []
    sources: List[Dict[str, str]] = []
    seen = set()
    for item in data.get("output", []):
        if item.get("type") != "message":
            continue
        for c in item.get("content", []):
            if c.get("type") != "output_text":
                continue
            texts.append(c.get("text", ""))
            for a in c.get("annotations", []) or []:
                url = a.get("url")
                if a.get("type") == "url_citation" and url and url not in seen:
                    seen.add(url)
                    sources.append({"url": url, "title": a.get("title") or url})
    return "".join(texts), sources


def call_function(
    prompt: str,
    functions: List[Dict[str, Any]],
    *,
    system: Optional[str] = None,
    temperature: Optional[float] = None,
) -> Tuple[Optional[Tuple[str, Dict[str, Any]]], str]:
    """Ask grok-4.7 to call one of `functions` (OpenAI function schema dicts).

    Returns ((name, args) or None, text).
    """
    messages: List[Dict[str, Any]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    body: Dict[str, Any] = {
        "model": TEXT_MODEL,
        "messages": messages,
        "tools": [{"type": "function", "function": f} for f in functions],
        "tool_choice": "auto",
    }
    if temperature is not None:
        body["temperature"] = temperature
    data = _post("/chat/completions", body, TEXT_TIMEOUT)
    msg = (data.get("choices") or [{}])[0].get("message", {})
    calls = msg.get("tool_calls") or []
    if calls:
        fn = calls[0].get("function", {})
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        return (fn.get("name", ""), args), msg.get("content") or ""
    return None, msg.get("content") or ""


def generate_image(
    prompt: str,
    *,
    reference_images: Optional[Sequence[Any]] = None,
    aspect_ratio: Optional[str] = None,
) -> bytes:
    """grok-imagine-image-2.0. With reference_images (max 5) this is an edit/compose call."""
    body: Dict[str, Any] = {"model": IMAGE_MODEL, "prompt": prompt, "response_format": "b64_json"}
    if aspect_ratio:
        body["aspect_ratio"] = aspect_ratio
    refs = [_image_bytes(i) for i in (reference_images or [])][:5]
    if refs:
        if len(refs) == 1:
            body["image"] = {"url": data_uri(refs[0]), "type": "image_url"}
        else:
            body["images"] = [{"url": data_uri(r), "type": "image_url"} for r in refs]
        data = _post("/images/edits", body, MEDIA_TIMEOUT)
    else:
        data = _post("/images/generations", body, MEDIA_TIMEOUT)
    items = data.get("data") or []
    if not items or not items[0].get("b64_json"):
        raise XaiError("xAI returned no image")
    return base64.b64decode(items[0]["b64_json"])


def generate_video(
    prompt: str,
    *,
    image: Optional[bytes] = None,
    aspect_ratio: Optional[str] = None,
    duration: Optional[int] = None,
    poll_interval: float = VIDEO_POLL_INTERVAL,
    max_wait: float = VIDEO_MAX_WAIT,
) -> Iterator[Tuple[str, Any]]:
    """grok-imagine-video-1.5 (image-to-video when `image` is given).

    Yields ("progress", elapsed_seconds) while polling, then ("complete", mp4_bytes).
    Raises XaiError on failure or timeout.
    """
    body: Dict[str, Any] = {"model": VIDEO_MODEL, "prompt": prompt}
    if image is not None:
        body["image"] = {"url": data_uri(image)}
    elif aspect_ratio:
        body["aspect_ratio"] = aspect_ratio  # image-to-video inherits the image's ratio
    if duration:
        body["duration"] = max(1, min(int(duration), 15))
    request_id = _post("/videos/generations", body, MEDIA_TIMEOUT).get("request_id")
    if not request_id:
        raise XaiError("xAI video request returned no request_id")
    start = time.time()
    while True:
        r = httpx.get(f"{API_BASE}/videos/{request_id}", headers=_headers(), timeout=60)
        if r.status_code >= 400:
            raise XaiError(f"xAI video poll HTTP {r.status_code}: {r.text[:300]}")
        data = r.json()
        status = data.get("status")
        if status == "done":
            url = (data.get("video") or {}).get("url")
            if not url:
                raise XaiError("xAI video finished without a URL")
            v = httpx.get(url, timeout=MEDIA_TIMEOUT, follow_redirects=True)
            v.raise_for_status()
            yield ("complete", v.content)
            return
        if status in ("failed", "expired"):
            raise XaiError(f"xAI video {status}: {json.dumps(data)[:300]}")
        if time.time() - start > max_wait:
            raise XaiError("xAI video generation timed out")
        yield ("progress", int(time.time() - start))
        time.sleep(poll_interval)


def transcribe(data: bytes, filename: str = "audio.mp3", *, diarize: bool = True) -> Dict[str, Any]:
    """xAI speech-to-text. Accepts any audio or video ffmpeg can read (non-mp3 input is
    converted to mono mp3 first, which also strips video).

    Returns {"text", "duration", "words": [{"text","start","end","speaker"?}]}.
    """
    ext = os.path.splitext(filename)[1].lower() or ".bin"
    if ext != ".mp3":
        data, filename = extract_audio(data, ext), os.path.splitext(filename)[0] + ".mp3"
    files = {"file": (filename, data, "audio/mpeg")}
    form = {"diarize": "true"} if diarize else {}
    r = httpx.post(f"{API_BASE}/stt", headers=_headers(), files=files, data=form, timeout=TEXT_TIMEOUT)
    if r.status_code >= 400:
        raise XaiError(f"xAI STT HTTP {r.status_code}: {r.text[:300]}")
    return r.json()


MIME_EXT = {
    "audio/mpeg": ".mp3", "audio/mp3": ".mp3", "audio/wav": ".wav", "audio/x-wav": ".wav",
    "audio/aac": ".aac", "audio/ogg": ".ogg", "audio/flac": ".flac", "audio/aiff": ".aiff",
    "audio/mp4": ".m4a", "audio/x-m4a": ".m4a", "video/mp4": ".mp4", "video/webm": ".webm",
    "video/quicktime": ".mov", "video/x-m4v": ".m4v",
}


def understand_media(data: bytes, filename: str, mime_type: str = "", *, timestamps: bool = True) -> str:
    """Verbatim, speaker-labelled transcript of audio/video.

    Video with no speech falls back to a grok-4.7 description of sampled frames.
    """
    ext = os.path.splitext(filename)[1].lower() or MIME_EXT.get(mime_type, ".mp4")
    name = os.path.splitext(filename)[0] + ext
    transcript = format_transcript(transcribe(data, name), timestamps=timestamps).strip()
    if transcript or not (mime_type.startswith("video/") or ext in (".mp4", ".mov", ".webm", ".m4v")):
        return transcript
    frames = sample_frames(data, 6, ext)
    if not frames:
        return ""
    return "[No speech detected. Visual description:]\n" + generate_text(
        "These frames are sampled evenly from a video with no speech. Describe what happens in the video "
        "in order, concisely and factually.",
        images=frames,
    ).strip()


def format_transcript(stt: Dict[str, Any], *, timestamps: bool = True) -> str:
    """Render STT output as readable lines, one per speaker turn: "[mm:ss] Speaker 1: ..."."""
    words = stt.get("words") or []
    if not words:
        return (stt.get("text") or "").strip()
    lines: List[str] = []
    cur_spk, cur_start, buf = object(), 0.0, []

    def flush():
        if buf:
            prefix = f"[{int(cur_start // 60):02d}:{int(cur_start % 60):02d}] " if timestamps else ""
            spk = f"Speaker {cur_spk + 1}: " if isinstance(cur_spk, int) else ""
            lines.append(prefix + spk + " ".join(buf))

    for w in words:
        spk = w.get("speaker")
        sentence_break = buf and buf[-1][-1:] in ".?!" and len(buf) >= 40
        if spk != cur_spk or sentence_break:
            flush()
            cur_spk, cur_start, buf = spk, float(w.get("start") or 0), []
        buf.append(w.get("text", ""))
    flush()
    return "\n".join(lines)


def _ffmpeg(args: List[str]) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True, timeout=600)


def extract_audio(video: bytes, ext: str = ".mp4") -> bytes:
    with tempfile.TemporaryDirectory() as d:
        src, out = os.path.join(d, "in" + ext), os.path.join(d, "out.mp3")
        open(src, "wb").write(video)
        _ffmpeg(["-i", src, "-vn", "-ac", "1", "-b:a", "64k", out])
        return open(out, "rb").read()


def sample_frames(video: bytes, count: int = 6, ext: str = ".mp4") -> List[bytes]:
    """Evenly sampled JPEG frames, for describing videos without speech."""
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "in" + ext)
        open(src, "wb").write(video)
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src],
            capture_output=True, text=True, timeout=60,
        )
        try:
            dur = float(probe.stdout.strip())
        except ValueError:
            dur = 0.0
        frames = []
        for i in range(count):
            t = dur * (i + 0.5) / count if dur else 0
            out = os.path.join(d, f"f{i}.jpg")
            try:
                _ffmpeg(["-ss", f"{t:.2f}", "-i", src, "-frames:v", "1", "-vf", "scale=768:-2", out])
                frames.append(open(out, "rb").read())
            except subprocess.CalledProcessError:
                continue
        return frames


def last_frame(video: bytes) -> bytes:
    """PNG of the final frame of an mp4 (used to chain scenes)."""
    with tempfile.TemporaryDirectory() as d:
        src, out = os.path.join(d, "in.mp4"), os.path.join(d, "last.png")
        open(src, "wb").write(video)
        _ffmpeg(["-sseof", "-0.1", "-i", src, "-update", "1", "-frames:v", "1", out])
        return open(out, "rb").read()


def concat_videos(first: bytes, second: bytes) -> bytes:
    """Concatenate two mp4 clips (re-encoded so differing encodes join cleanly)."""
    with tempfile.TemporaryDirectory() as d:
        a, b, out = (os.path.join(d, n) for n in ("a.mp4", "b.mp4", "out.mp4"))
        open(a, "wb").write(first)
        open(b, "wb").write(second)
        w, h = _dims(a)
        vf = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24"
        has_audio = _has_audio(a) and _has_audio(b)
        if has_audio:
            fc = f"[0:v]{vf}[v0];[1:v]{vf}[v1];[v0][0:a][v1][1:a]concat=n=2:v=1:a=1[v][a]"
            maps = ["-map", "[v]", "-map", "[a]", "-c:a", "aac"]
        else:
            fc = f"[0:v]{vf}[v0];[1:v]{vf}[v1];[v0][v1]concat=n=2:v=1:a=0[v]"
            maps = ["-map", "[v]"]
        _ffmpeg(["-i", a, "-i", b, "-filter_complex", fc, *maps, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                 "-movflags", "+faststart", out])
        return open(out, "rb").read()


def _dims(path: str) -> Tuple[int, int]:
    p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", path], capture_output=True, text=True, timeout=60)
    w, h = (int(x) for x in p.stdout.strip().split(",")[:2])
    return w - w % 2, h - h % 2


def _has_audio(path: str) -> bool:
    p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                        "-of", "csv=p=0", path], capture_output=True, text=True, timeout=60)
    return bool(p.stdout.strip())


def parse_json(text: str) -> Any:
    """Parse model JSON output, tolerating ```json fences."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return json.loads(t)


class TextResponse:
    """Completion result exposing `.text` (what call sites read)."""

    __slots__ = ("text", "sources")

    def __init__(self, text: str, sources: Optional[List[Dict[str, str]]] = None):
        self.text = text
        self.sources = sources or []


def chat(prompt: str, **kwargs: Any) -> TextResponse:
    """generate_text wrapped in a TextResponse."""
    return TextResponse(generate_text(prompt, **kwargs))
