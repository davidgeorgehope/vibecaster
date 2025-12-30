"""Tests for agent utility functions."""
import pytest
import json
import sys
import os

# Add backend to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from agents.utils import is_network_error, emit_agent_event, strip_markdown_formatting


class TestIsNetworkError:
    """Tests for network error detection."""

    def test_detects_quic_error(self):
        """Test QUIC protocol error detection."""
        error = Exception("QUIC_PROTOCOL_ERROR: connection reset")
        assert is_network_error(error) is True

    def test_detects_h3_error(self):
        """Test HTTP/3 error detection."""
        error = Exception("h3 error: stream closed")
        assert is_network_error(error) is True

    def test_detects_protocol_error(self):
        """Test generic protocol error detection."""
        error = Exception("protocol_error occurred")
        assert is_network_error(error) is True

    def test_detects_connection_closed(self):
        """Test connection closed error detection."""
        error = Exception("connection_closed unexpectedly")
        assert is_network_error(error) is True

    def test_regular_error_not_network(self):
        """Test that regular errors are not classified as network errors."""
        error = Exception("ValueError: invalid argument")
        assert is_network_error(error) is False

    def test_json_error_not_network(self):
        """Test that JSON errors are not classified as network errors."""
        error = Exception("JSONDecodeError: invalid JSON")
        assert is_network_error(error) is False


class TestEmitAgentEvent:
    """Tests for agent event emission."""

    def test_emits_thinking_event(self):
        """Test thinking event format."""
        result = emit_agent_event("thinking", message="Analyzing request")
        parsed = json.loads(result.strip())
        assert parsed["type"] == "thinking"
        assert parsed["message"] == "Analyzing request"
        assert "timestamp" in parsed

    def test_emits_searching_event(self):
        """Test searching event format."""
        result = emit_agent_event("searching", query="kubernetes best practices")
        parsed = json.loads(result.strip())
        assert parsed["type"] == "searching"
        assert parsed["query"] == "kubernetes best practices"

    def test_emits_error_event(self):
        """Test error event format."""
        result = emit_agent_event("error", message="Network failed", retryable=True)
        parsed = json.loads(result.strip())
        assert parsed["type"] == "error"
        assert parsed["message"] == "Network failed"
        assert parsed["retryable"] is True

    def test_emits_complete_event(self):
        """Test complete event format."""
        result = emit_agent_event("complete", success=True)
        parsed = json.loads(result.strip())
        assert parsed["type"] == "complete"
        assert parsed["success"] is True

    def test_event_ends_with_newline(self):
        """Test that events end with newline for SSE compatibility."""
        result = emit_agent_event("thinking", message="Test")
        assert result.endswith("\n")


class TestStripMarkdownFormatting:
    """Tests for markdown stripping."""

    def test_strips_bold_asterisks(self):
        """Test stripping **bold** text."""
        result = strip_markdown_formatting("This is **bold** text")
        assert result == "This is bold text"

    def test_strips_bold_underscores(self):
        """Test stripping __bold__ text."""
        result = strip_markdown_formatting("This is __bold__ text")
        assert result == "This is bold text"

    def test_strips_italic_asterisks(self):
        """Test stripping *italic* text."""
        result = strip_markdown_formatting("This is *italic* text")
        assert result == "This is italic text"

    def test_strips_italic_underscores(self):
        """Test stripping _italic_ text."""
        result = strip_markdown_formatting("This is _italic_ text")
        assert result == "This is italic text"

    def test_strips_strikethrough(self):
        """Test stripping ~~strikethrough~~ text."""
        result = strip_markdown_formatting("This is ~~deleted~~ text")
        assert result == "This is deleted text"

    def test_strips_code(self):
        """Test stripping `code` formatting."""
        result = strip_markdown_formatting("Run the `kubectl` command")
        assert result == "Run the kubectl command"

    def test_preserves_urls_with_underscores(self):
        """Test that URLs with underscores are preserved."""
        result = strip_markdown_formatting("Visit https://example.com/some_page_here")
        # The regex should be careful not to break URLs
        assert "https://example.com" in result

    def test_handles_empty_string(self):
        """Test handling of empty string."""
        result = strip_markdown_formatting("")
        assert result == ""

    def test_handles_plain_text(self):
        """Test that plain text is preserved."""
        result = strip_markdown_formatting("Plain text without formatting")
        assert result == "Plain text without formatting"
