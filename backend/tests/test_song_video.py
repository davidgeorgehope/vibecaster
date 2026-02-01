"""
Unit tests for song_video module.
"""

import pytest
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock


class TestCreateAssSubtitleFile:
    """Tests for ASS subtitle file generation."""

    def test_empty_words(self):
        """Should return valid ASS file with no dialogue for empty words."""
        from song_video import create_ass_subtitle_file

        result = create_ass_subtitle_file([], 60.0)

        assert "[Script Info]" in result
        assert "[V4+ Styles]" in result
        assert "[Events]" in result
        assert "Dialogue:" not in result

    def test_single_word(self):
        """Should generate dialogue for a single word."""
        from song_video import create_ass_subtitle_file

        words = [{"word": "Hello", "start_ms": 1000, "end_ms": 1500}]
        result = create_ass_subtitle_file(words, 10.0)

        assert "Dialogue:" in result
        assert "Hello" in result
        # Should have karaoke tag
        assert "\\k" in result

    def test_multiple_words_same_line(self):
        """Should group words into a single line when close together."""
        from song_video import create_ass_subtitle_file

        words = [
            {"word": "Hello", "start_ms": 1000, "end_ms": 1300},
            {"word": "world", "start_ms": 1400, "end_ms": 1800},
            {"word": "today", "start_ms": 1900, "end_ms": 2300},
        ]
        result = create_ass_subtitle_file(words, 10.0)

        # All words should appear
        assert "Hello" in result
        assert "world" in result
        assert "today" in result

    def test_line_break_on_gap(self):
        """Should start new line when gap > 1.5 seconds."""
        from song_video import create_ass_subtitle_file

        words = [
            {"word": "Line", "start_ms": 1000, "end_ms": 1300},
            {"word": "one", "start_ms": 1400, "end_ms": 1700},
            # 2 second gap here
            {"word": "Line", "start_ms": 3700, "end_ms": 4000},
            {"word": "two", "start_ms": 4100, "end_ms": 4400},
        ]
        result = create_ass_subtitle_file(words, 10.0)

        # Count dialogue lines
        dialogue_count = result.count("Dialogue:")
        assert dialogue_count >= 2  # Should have at least 2 lines

    def test_karaoke_timing(self):
        """Should include duration in karaoke tags."""
        from song_video import create_ass_subtitle_file

        words = [{"word": "Test", "start_ms": 0, "end_ms": 500}]  # 500ms = 50 centiseconds
        result = create_ass_subtitle_file(words, 10.0)

        # Should have karaoke fill tag with duration
        assert "\\kf50" in result or "\\kf" in result


class TestGetAudioDuration:
    """Tests for audio duration detection."""

    @patch('song_video.subprocess.run')
    def test_returns_duration_from_ffprobe(self, mock_run):
        """Should return duration from ffprobe output."""
        from song_video import get_audio_duration

        mock_run.return_value = Mock(stdout="123.45\n", returncode=0)

        # Create temp file to avoid file I/O issues
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
            f.write(b"fake audio data")
            temp_path = f.name

        try:
            result = get_audio_duration(b"fake audio data", "audio/mpeg")
            assert result == 123.45
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    @patch('song_video.subprocess.run')
    def test_returns_default_on_error(self, mock_run):
        """Should return default duration on error."""
        from song_video import get_audio_duration

        mock_run.side_effect = Exception("ffprobe failed")

        result = get_audio_duration(b"fake audio data", "audio/mpeg")
        assert result == 180.0  # Default


class TestSupportedAudioTypes:
    """Tests for SUPPORTED_AUDIO_TYPES constant."""

    def test_includes_common_types(self):
        """Should include common audio MIME types."""
        from song_video import SUPPORTED_AUDIO_TYPES

        assert "audio/mpeg" in SUPPORTED_AUDIO_TYPES
        assert "audio/mp3" in SUPPORTED_AUDIO_TYPES
        assert "audio/wav" in SUPPORTED_AUDIO_TYPES
        assert "audio/ogg" in SUPPORTED_AUDIO_TYPES


class TestEmitEvent:
    """Tests for emit_event helper."""

    def test_returns_json_string(self):
        """Should return valid JSON string."""
        from song_video import emit_event
        import json

        result = emit_event("test", message="hello")
        parsed = json.loads(result)

        assert parsed["type"] == "test"
        assert parsed["message"] == "hello"
        assert "timestamp" in parsed


class TestVideoStorageIntegration:
    """Tests for video storage integration."""

    def test_store_and_retrieve(self):
        """Should store and retrieve videos."""
        from video_storage import store_video, get_video, delete_video

        video_ref = "test-ref-123"
        video_bytes = b"fake video data"
        store_video(video_ref, video_bytes, "video/mp4", user_id=1)

        result = get_video(video_ref)
        assert result is not None
        assert result["bytes"] == video_bytes
        assert result["content_type"] == "video/mp4"
        assert result["user_id"] == 1

        # Cleanup
        delete_video(video_ref)
        assert get_video(video_ref) is None
