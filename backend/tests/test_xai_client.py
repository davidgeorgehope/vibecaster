"""Unit tests for xai_client (HTTP mocked) plus opt-in live smoke tests (-m integration)."""
import base64
import json
import os
import shutil
import sys
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import xai_client
from xai_client import XaiError


def _resp(payload=None, status=200, content=b""):
    r = Mock()
    r.status_code = status
    r.json.return_value = payload or {}
    r.text = json.dumps(payload or {})
    r.content = content
    r.raise_for_status = Mock()
    return r


@pytest.fixture(autouse=True)
def api_key(monkeypatch, request):
    if "integration" not in request.keywords:
        monkeypatch.setenv("XAI_API_KEY", "test-key")


def test_flagship_models_only():
    assert xai_client.TEXT_MODEL == "grok-4.7"
    assert xai_client.IMAGE_MODEL == "grok-imagine-image-2.0"
    assert xai_client.VIDEO_MODEL == "grok-imagine-video-1.5"


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("XAI_API_KEY")
    with pytest.raises(XaiError, match="XAI_API_KEY"):
        xai_client.generate_text("hi")


@patch("xai_client.httpx.post")
def test_generate_text_builds_request(mock_post):
    mock_post.return_value = _resp({"choices": [{"message": {"content": '{"a": 1}'}}]})

    out = xai_client.generate_text("prompt", system="sys", json_mode=True, temperature=0.2)

    assert out == '{"a": 1}'
    url, kwargs = mock_post.call_args.args[0], mock_post.call_args.kwargs
    assert url.endswith("/chat/completions")
    body = kwargs["json"]
    assert body["model"] == "grok-4.7"
    assert body["messages"] == [{"role": "system", "content": "sys"}, {"role": "user", "content": "prompt"}]
    assert body["temperature"] == 0.2
    assert body["response_format"] == {"type": "json_object"}
    assert kwargs["headers"]["Authorization"] == "Bearer test-key"


@patch("xai_client.httpx.post")
def test_generate_text_with_images_uses_data_uris(mock_post):
    mock_post.return_value = _resp({"choices": [{"message": {"content": "ok"}}]})
    xai_client.generate_text("describe", images=[b"\xff\xd8\xffjpeg"])
    content = mock_post.call_args.kwargs["json"]["messages"][0]["content"]
    assert content[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert content[-1] == {"type": "text", "text": "describe"}


@patch("xai_client.httpx.post")
def test_generate_text_empty_and_http_errors(mock_post):
    mock_post.return_value = _resp({"choices": [{"message": {"content": "  "}}]})
    with pytest.raises(XaiError, match="empty"):
        xai_client.generate_text("x")
    mock_post.return_value = _resp({"error": "bad"}, status=429)
    with pytest.raises(XaiError, match="429"):
        xai_client.generate_text("x")


@patch("xai_client.httpx.post")
def test_web_search_returns_text_and_deduped_sources(mock_post):
    ann = {"type": "url_citation", "url": "https://a.com", "title": "A"}
    mock_post.return_value = _resp({"output": [
        {"type": "web_search_call"},
        {"type": "message", "content": [
            {"type": "output_text", "text": "Hello ", "annotations": [ann, ann]},
            {"type": "output_text", "text": "world", "annotations": [{"type": "url_citation", "url": "https://b.com"}]},
        ]},
    ]})

    text, sources = xai_client.web_search("news", temperature=0.5)

    assert text == "Hello world"
    assert sources == [{"url": "https://a.com", "title": "A"}, {"url": "https://b.com", "title": "https://b.com"}]
    body = mock_post.call_args.kwargs["json"]
    assert mock_post.call_args.args[0].endswith("/responses")
    assert body["tools"] == [{"type": "web_search"}] and body["model"] == "grok-4.7"


@patch("xai_client.httpx.post")
def test_call_function_parses_tool_call(mock_post):
    mock_post.return_value = _resp({"choices": [{"message": {"content": "", "tool_calls": [
        {"function": {"name": "make_post", "arguments": '{"text": "hi"}'}}]}}]})
    fn = {"name": "make_post", "parameters": {"type": "object"}}

    call, text = xai_client.call_function("p", [fn])

    assert call == ("make_post", {"text": "hi"})
    assert mock_post.call_args.kwargs["json"]["tools"] == [{"type": "function", "function": fn}]

    mock_post.return_value = _resp({"choices": [{"message": {"content": "no tool"}}]})
    assert xai_client.call_function("p", [fn]) == (None, "no tool")


@patch("xai_client.httpx.post")
def test_generate_image_generation_vs_edit(mock_post):
    png = b"\x89PNG\r\n\x1a\nimg"
    mock_post.return_value = _resp({"data": [{"b64_json": base64.b64encode(png).decode()}]})

    assert xai_client.generate_image("cat", aspect_ratio="1:1") == png
    assert mock_post.call_args.args[0].endswith("/images/generations")
    body = mock_post.call_args.kwargs["json"]
    assert body["model"] == "grok-imagine-image-2.0" and body["aspect_ratio"] == "1:1"

    xai_client.generate_image("cat", reference_images=[png])
    assert mock_post.call_args.args[0].endswith("/images/edits")
    assert mock_post.call_args.kwargs["json"]["image"]["url"].startswith("data:image/png;base64,")

    xai_client.generate_image("cat", reference_images=[png] * 7)
    assert len(mock_post.call_args.kwargs["json"]["images"]) == 5

    mock_post.return_value = _resp({"data": []})
    with pytest.raises(XaiError):
        xai_client.generate_image("cat")


@patch("xai_client.time.sleep")
@patch("xai_client.httpx.get")
@patch("xai_client.httpx.post")
def test_generate_video_polls_then_downloads(mock_post, mock_get, _sleep):
    mock_post.return_value = _resp({"request_id": "r1"})
    mock_get.side_effect = [
        _resp({"status": "pending"}),
        _resp({"status": "done", "video": {"url": "https://vid/x.mp4"}}),
        _resp(content=b"MP4DATA"),
    ]

    events = list(xai_client.generate_video("move", image=b"\x89PNGframe", duration=30))

    assert events[0][0] == "progress"
    assert events[-1] == ("complete", b"MP4DATA")
    body = mock_post.call_args.kwargs["json"]
    assert body["model"] == "grok-imagine-video-1.5"
    assert body["duration"] == 15  # clamped
    assert "aspect_ratio" not in body  # image-to-video inherits the frame's ratio


@patch("xai_client.time.sleep")
@patch("xai_client.httpx.get")
@patch("xai_client.httpx.post")
def test_generate_video_failure_raises(mock_post, mock_get, _sleep):
    mock_post.return_value = _resp({"request_id": "r1"})
    mock_get.return_value = _resp({"status": "failed"})
    with pytest.raises(XaiError, match="failed"):
        list(xai_client.generate_video("move"))


def test_format_transcript_speaker_turns():
    stt = {"words": [
        {"text": "Hi", "start": 0.0, "speaker": 0},
        {"text": "there.", "start": 0.5, "speaker": 0},
        {"text": "Hello.", "start": 65.2, "speaker": 1},
    ]}
    assert xai_client.format_transcript(stt) == "[00:00] Speaker 1: Hi there.\n[01:05] Speaker 2: Hello."
    assert xai_client.format_transcript({"text": " plain "}) == "plain"


def test_parse_json_tolerates_fences():
    assert xai_client.parse_json('```json\n{"a": [1]}\n```') == {"a": [1]}


@patch("xai_client.sample_frames", return_value=[b"\x89PNGf"])
@patch("xai_client.generate_text", return_value="A sunset.")
@patch("xai_client.transcribe", return_value={"text": "", "words": []})
def test_understand_media_silent_video_falls_back_to_frames(_t, mock_text, _f):
    out = xai_client.understand_media(b"vid", "clip.mp4", "video/mp4")
    assert out.endswith("A sunset.") and "No speech" in out
    assert mock_text.call_args.kwargs["images"] == [b"\x89PNGf"]


@patch("xai_client.transcribe", return_value={"text": "", "words": []})
def test_understand_media_silent_audio_returns_empty(_t):
    assert xai_client.understand_media(b"aud", "a.mp3", "audio/mpeg") == ""


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_ffmpeg_helpers_roundtrip(tmp_path):
    import subprocess
    clip = tmp_path / "c.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=160x90:rate=24:duration=1",
                    "-pix_fmt", "yuv420p", str(clip)], check=True)
    data = clip.read_bytes()
    frame = xai_client.last_frame(data)
    assert frame[:8] == b"\x89PNG\r\n\x1a\n" or frame[:3] == b"\xff\xd8\xff"
    assert len(xai_client.sample_frames(data, 3)) == 3
    combined = xai_client.concat_videos(data, data)
    assert b"ftyp" in combined[:32]


# ---- live smoke (costs credits): pytest -m integration tests/test_xai_client.py ----

live = pytest.mark.skipif(os.getenv("XAI_LIVE") != "1", reason="set XAI_LIVE=1 with a real XAI_API_KEY")


@pytest.mark.integration
@live
def test_live_text_json_and_search():
    assert "ok" in xai_client.generate_text('Reply with JSON {"status":"ok"}', json_mode=True).lower()
    text, sources = xai_client.web_search("What is the latest news about xAI? One sentence.")
    assert text and sources


@pytest.mark.integration
@live
def test_live_image():
    img = xai_client.generate_image("A small red circle on white", aspect_ratio="1:1")
    assert len(img) > 1000
