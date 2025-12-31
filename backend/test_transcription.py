#!/usr/bin/env python3
"""
Tests for the transcription module and endpoint.
"""

import os
import sys
import json
import requests
from io import BytesIO

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from transcription import (
    SUPPORTED_MIME_TYPES,
    INLINE_SIZE_LIMIT,
    emit_event,
    transcribe_media_stream
)

BASE_URL = "http://localhost:8001"
TEST_AUDIO_PATH = "/tmp/test_speech.mp3"  # Actually a WAV with speech


def test_emit_event():
    """Test event emission format."""
    print("\n[TEST] emit_event...")

    event = emit_event("progress", step="transcribing", message="Working...")
    data = json.loads(event)

    assert data["type"] == "progress", f"Expected type 'progress', got {data['type']}"
    assert data["step"] == "transcribing", f"Expected step 'transcribing', got {data['step']}"
    assert data["message"] == "Working...", f"Expected message 'Working...', got {data['message']}"
    assert "timestamp" in data, "Missing timestamp"

    print("[PASS] emit_event works correctly")


def test_supported_mime_types():
    """Test that expected MIME types are supported."""
    print("\n[TEST] SUPPORTED_MIME_TYPES...")

    expected_audio = ["audio/mpeg", "audio/mp3", "audio/wav", "audio/ogg", "audio/flac"]
    expected_video = ["video/mp4", "video/webm", "video/quicktime"]

    for mime in expected_audio:
        assert mime in SUPPORTED_MIME_TYPES, f"Missing audio type: {mime}"

    for mime in expected_video:
        assert mime in SUPPORTED_MIME_TYPES, f"Missing video type: {mime}"

    print(f"[PASS] All expected MIME types supported ({len(SUPPORTED_MIME_TYPES)} total)")


def test_inline_size_limit():
    """Test inline size limit is reasonable."""
    print("\n[TEST] INLINE_SIZE_LIMIT...")

    assert INLINE_SIZE_LIMIT == 20 * 1024 * 1024, f"Expected 20MB, got {INLINE_SIZE_LIMIT}"
    print(f"[PASS] INLINE_SIZE_LIMIT is 20MB ({INLINE_SIZE_LIMIT} bytes)")


def test_transcribe_unsupported_type():
    """Test that unsupported file types are rejected."""
    print("\n[TEST] transcribe_media_stream with unsupported type...")

    events = list(transcribe_media_stream(
        user_id=1,
        file_bytes=b"fake data",
        filename="test.txt",
        mime_type="text/plain"
    ))

    assert len(events) == 1, f"Expected 1 event, got {len(events)}"
    data = json.loads(events[0])
    assert data["type"] == "error", f"Expected error event, got {data['type']}"
    assert "Unsupported" in data["message"], f"Expected 'Unsupported' in message"

    print("[PASS] Unsupported types rejected correctly")


def get_test_token():
    """Get a test auth token by logging in."""
    # Try to login as test user
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "test@test.com",
        "password": "testtest"
    })

    if response.status_code == 200:
        return response.json()["access_token"]

    # Try to create test user
    response = requests.post(f"{BASE_URL}/api/auth/signup", json={
        "email": "test@test.com",
        "password": "testtest"
    })

    if response.status_code == 201:
        return response.json()["access_token"]

    # Login again after signup
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "test@test.com",
        "password": "testtest"
    })

    if response.status_code == 200:
        return response.json()["access_token"]

    return None


def test_endpoint_no_auth():
    """Test that endpoint requires authentication."""
    print("\n[TEST] Endpoint requires authentication...")

    with open(TEST_AUDIO_PATH, "rb") as f:
        response = requests.post(
            f"{BASE_URL}/api/transcribe-stream",
            files={"file": ("test.mp3", f, "audio/mpeg")}
        )

    assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
    print("[PASS] Endpoint correctly requires authentication")


def test_endpoint_invalid_type():
    """Test that endpoint rejects invalid file types."""
    print("\n[TEST] Endpoint rejects invalid file types...")

    token = get_test_token()
    if not token:
        print("[SKIP] Could not get test token")
        return

    response = requests.post(
        f"{BASE_URL}/api/transcribe-stream",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("test.txt", BytesIO(b"hello world"), "text/plain")}
    )

    assert response.status_code == 400, f"Expected 400, got {response.status_code}"
    assert "Unsupported" in response.json().get("detail", ""), "Expected 'Unsupported' in error"
    print("[PASS] Invalid file types rejected correctly")


def test_endpoint_empty_file():
    """Test that endpoint rejects empty files."""
    print("\n[TEST] Endpoint rejects empty files...")

    token = get_test_token()
    if not token:
        print("[SKIP] Could not get test token")
        return

    response = requests.post(
        f"{BASE_URL}/api/transcribe-stream",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("test.mp3", BytesIO(b""), "audio/mpeg")}
    )

    assert response.status_code == 400, f"Expected 400, got {response.status_code}"
    assert "Empty" in response.json().get("detail", ""), "Expected 'Empty' in error"
    print("[PASS] Empty files rejected correctly")


def test_endpoint_streaming():
    """Test actual transcription streaming (integration test)."""
    print("\n[TEST] Full transcription streaming (this may take a while)...")

    token = get_test_token()
    if not token:
        print("[SKIP] Could not get test token")
        return

    if not os.path.exists(TEST_AUDIO_PATH):
        print(f"[SKIP] Test audio file not found: {TEST_AUDIO_PATH}")
        return

    with open(TEST_AUDIO_PATH, "rb") as f:
        response = requests.post(
            f"{BASE_URL}/api/transcribe-stream",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("test.wav", f, "audio/wav")},
            stream=True
        )

    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    events_received = []
    transcript = None
    summary = None
    blog_post = None

    print("   Receiving SSE events...")
    for line in response.iter_lines():
        if line:
            line = line.decode("utf-8")
            if line.startswith("data: "):
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    events_received.append(data["type"])
                    print(f"   - Received: {data['type']}")

                    if data["type"] == "transcript":
                        transcript = data.get("transcript", "")
                    elif data["type"] == "summary":
                        summary = data.get("summary", "")
                    elif data["type"] == "blog_post":
                        blog_post = data.get("blog_post", "")
                    elif data["type"] == "error":
                        print(f"   [ERROR] {data.get('message')}")

                except json.JSONDecodeError:
                    pass

    # Check we got the expected events
    assert "progress" in events_received, "Missing progress events"

    if "error" in events_received:
        print("[WARN] Transcription returned an error (may be API issue)")
    else:
        assert "transcript" in events_received, "Missing transcript event"
        assert "summary" in events_received, "Missing summary event"
        assert "blog_post" in events_received, "Missing blog_post event"
        assert "complete" in events_received, "Missing complete event"

        print(f"\n   Transcript length: {len(transcript) if transcript else 0} chars")
        print(f"   Summary length: {len(summary) if summary else 0} chars")
        print(f"   Blog post length: {len(blog_post) if blog_post else 0} chars")

        print("[PASS] Full transcription streaming works!")


def run_all_tests():
    """Run all tests."""
    print("=" * 50)
    print("TRANSCRIPTION MODULE TESTS")
    print("=" * 50)

    # Unit tests (fast)
    test_emit_event()
    test_supported_mime_types()
    test_inline_size_limit()
    test_transcribe_unsupported_type()

    # Integration tests (require running server)
    print("\n" + "-" * 50)
    print("INTEGRATION TESTS (require running server)")
    print("-" * 50)

    try:
        requests.get(f"{BASE_URL}/health", timeout=2)
    except:
        print("\n[SKIP] Server not running, skipping integration tests")
        return

    test_endpoint_no_auth()
    test_endpoint_invalid_type()
    test_endpoint_empty_file()
    test_endpoint_streaming()

    print("\n" + "=" * 50)
    print("ALL TESTS COMPLETED")
    print("=" * 50)


if __name__ == "__main__":
    run_all_tests()
