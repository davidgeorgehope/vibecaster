"""
Tests for agents_lib/intent_parser.py

Each test has meaningful assertions that could actually fail.
Covers edge cases: null, empty, malformed input, error states.
"""
import pytest
from unittest.mock import patch, Mock, MagicMock
import json

from agents_lib.intent_parser import (
    agent_intent_parser,
    is_greeting_intent,
    is_clarify_intent,
    is_generate_posts_intent,
    is_brainstorm_intent,
    is_campaign_intent,
    INTENT_GENERATE_POSTS,
    INTENT_BRAINSTORM,
    INTENT_GENERATE_CAMPAIGN,
    INTENT_GREETING,
    INTENT_CLARIFY,
    DEFAULT_PERSONA,
    DEFAULT_VISUAL_STYLE,
)


class TestIntentConstants:
    """Tests for intent constants."""

    def test_intent_constants_are_unique(self):
        """All intent constants should be unique strings."""
        intents = [
            INTENT_GENERATE_POSTS,
            INTENT_BRAINSTORM,
            INTENT_GENERATE_CAMPAIGN,
            INTENT_GREETING,
            INTENT_CLARIFY,
        ]
        assert len(intents) == len(set(intents)), "Intent constants must be unique"

    def test_intent_constants_are_strings(self):
        """All intent constants should be strings."""
        assert isinstance(INTENT_GENERATE_POSTS, str)
        assert isinstance(INTENT_BRAINSTORM, str)
        assert isinstance(INTENT_GENERATE_CAMPAIGN, str)
        assert isinstance(INTENT_GREETING, str)
        assert isinstance(INTENT_CLARIFY, str)

    def test_default_values_are_strings(self):
        """Default values should be non-empty strings."""
        assert isinstance(DEFAULT_PERSONA, str) and len(DEFAULT_PERSONA) > 0
        assert isinstance(DEFAULT_VISUAL_STYLE, str) and len(DEFAULT_VISUAL_STYLE) > 0


class TestIsIntentHelpers:
    """Tests for intent checking helper functions."""

    def test_is_greeting_intent_returns_true(self):
        """Should return True when intent is greeting."""
        result = {"intent": INTENT_GREETING}
        assert is_greeting_intent(result) is True

    def test_is_greeting_intent_returns_false(self):
        """Should return False when intent is not greeting."""
        result = {"intent": INTENT_GENERATE_POSTS}
        assert is_greeting_intent(result) is False

    def test_is_greeting_intent_handles_missing_key(self):
        """Should return False when intent key is missing."""
        assert is_greeting_intent({}) is False
        assert is_greeting_intent({"other": "value"}) is False

    def test_is_clarify_intent_returns_true(self):
        """Should return True when intent is clarify."""
        result = {"intent": INTENT_CLARIFY}
        assert is_clarify_intent(result) is True

    def test_is_clarify_intent_returns_false(self):
        """Should return False when intent is not clarify."""
        result = {"intent": INTENT_GENERATE_POSTS}
        assert is_clarify_intent(result) is False

    def test_is_generate_posts_intent_returns_true(self):
        """Should return True when intent is generate_posts."""
        result = {"intent": INTENT_GENERATE_POSTS}
        assert is_generate_posts_intent(result) is True

    def test_is_generate_posts_intent_returns_false(self):
        """Should return False when intent is not generate_posts."""
        result = {"intent": INTENT_BRAINSTORM}
        assert is_generate_posts_intent(result) is False

    def test_is_brainstorm_intent_returns_true(self):
        """Should return True when intent is brainstorm."""
        result = {"intent": INTENT_BRAINSTORM}
        assert is_brainstorm_intent(result) is True

    def test_is_brainstorm_intent_returns_false(self):
        """Should return False when intent is not brainstorm."""
        result = {"intent": INTENT_GENERATE_POSTS}
        assert is_brainstorm_intent(result) is False

    def test_is_campaign_intent_returns_true(self):
        """Should return True when intent is generate_campaign_prompt."""
        result = {"intent": INTENT_GENERATE_CAMPAIGN}
        assert is_campaign_intent(result) is True

    def test_is_campaign_intent_returns_false(self):
        """Should return False when intent is not generate_campaign_prompt."""
        result = {"intent": INTENT_GENERATE_POSTS}
        assert is_campaign_intent(result) is False


class TestAgentIntentParser:
    """Tests for agent_intent_parser function."""

    @patch('agents_lib.intent_parser.client')
    def test_returns_parsed_intent_from_llm(self, mock_client):
        """Should return parsed intent from LLM response."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "intent": "generate_posts",
            "persona": "Gordon Ramsay",
            "topic": "cloud computing",
            "search_query": "cloud computing trends 2024",
            "visual_style": "chef in kitchen with laptop"
        })
        mock_client.models.generate_content.return_value = mock_response

        result = agent_intent_parser("gordon ramsay explains cloud computing")

        assert result["intent"] == "generate_posts"
        assert result["persona"] == "Gordon Ramsay"
        assert result["topic"] == "cloud computing"
        assert "cloud" in result["search_query"].lower()

    @patch('agents_lib.intent_parser.client')
    def test_includes_history_in_context(self, mock_client):
        """Should include conversation history in context."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "intent": "generate_posts",
            "persona": "tech expert",
            "topic": "AI",
            "search_query": "AI trends",
            "visual_style": "modern"
        })
        mock_client.models.generate_content.return_value = mock_response

        history = [
            {"role": "user", "content": "I want to talk about AI"},
            {"role": "assistant", "content": "Great topic! What angle?"},
        ]

        agent_intent_parser("latest developments", history=history)

        # Verify the call was made with context containing history
        call_args = mock_client.models.generate_content.call_args
        contents = call_args.kwargs['contents']
        assert "Previous conversation" in contents
        assert "I want to talk about AI" in contents

    @patch('agents_lib.intent_parser.client')
    def test_limits_history_to_last_6_messages(self, mock_client):
        """Should only include last 6 messages from history."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "intent": "generate_posts",
            "persona": "expert",
            "topic": "topic",
            "search_query": "query",
            "visual_style": "style"
        })
        mock_client.models.generate_content.return_value = mock_response

        # Create 10 messages
        history = [{"role": "user", "content": f"message {i}"} for i in range(10)]

        agent_intent_parser("latest", history=history)

        call_args = mock_client.models.generate_content.call_args
        contents = call_args.kwargs['contents']
        # Should include messages 4-9 (last 6), not 0-3
        assert "message 9" in contents
        assert "message 4" in contents
        assert "message 3" not in contents

    @patch('agents_lib.intent_parser.client')
    def test_truncates_long_history_content(self, mock_client):
        """Should truncate history content longer than 500 chars."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "intent": "generate_posts",
            "persona": "expert",
            "topic": "topic",
            "search_query": "query",
            "visual_style": "style"
        })
        mock_client.models.generate_content.return_value = mock_response

        long_content = "x" * 1000  # 1000 char message
        history = [{"role": "user", "content": long_content}]

        agent_intent_parser("test", history=history)

        call_args = mock_client.models.generate_content.call_args
        contents = call_args.kwargs['contents']
        # The full 1000-char message should NOT appear
        assert long_content not in contents
        # But truncated version (500 chars) should
        assert "x" * 500 in contents

    @patch('agents_lib.intent_parser.client')
    def test_returns_fallback_on_llm_error(self, mock_client):
        """Should return fallback values when LLM fails."""
        mock_client.models.generate_content.side_effect = Exception("API error")

        result = agent_intent_parser("make posts about kubernetes")

        assert result["intent"] == INTENT_GENERATE_POSTS
        assert result["persona"] == DEFAULT_PERSONA
        assert result["topic"] == "make posts about kubernetes"
        assert result["search_query"] == "make posts about kubernetes"
        assert result["visual_style"] == DEFAULT_VISUAL_STYLE

    @patch('agents_lib.intent_parser.client')
    def test_returns_fallback_on_invalid_json(self, mock_client):
        """Should return fallback values when LLM returns invalid JSON."""
        mock_response = Mock()
        mock_response.text = "not valid json {"
        mock_client.models.generate_content.return_value = mock_response

        result = agent_intent_parser("create posts")

        assert result["intent"] == INTENT_GENERATE_POSTS
        assert result["persona"] == DEFAULT_PERSONA

    @patch('agents_lib.intent_parser.client')
    def test_works_with_empty_history(self, mock_client):
        """Should work correctly with empty history list."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "intent": "greeting",
            "persona": "friendly assistant",
            "topic": "",
            "search_query": "",
            "visual_style": ""
        })
        mock_client.models.generate_content.return_value = mock_response

        result = agent_intent_parser("hello", history=[])

        assert result["intent"] == "greeting"

    @patch('agents_lib.intent_parser.client')
    def test_works_with_none_history(self, mock_client):
        """Should work correctly with None history."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "intent": "generate_posts",
            "persona": "expert",
            "topic": "AI",
            "search_query": "AI trends",
            "visual_style": "modern"
        })
        mock_client.models.generate_content.return_value = mock_response

        result = agent_intent_parser("posts about AI", history=None)

        assert result["intent"] == "generate_posts"

    @patch('agents_lib.intent_parser.client')
    def test_uses_low_temperature_for_consistency(self, mock_client):
        """Should use low temperature (0.2) for consistent parsing."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "intent": "generate_posts",
            "persona": "expert",
            "topic": "topic",
            "search_query": "query",
            "visual_style": "style"
        })
        mock_client.models.generate_content.return_value = mock_response

        agent_intent_parser("test message")

        call_args = mock_client.models.generate_content.call_args
        config = call_args.kwargs['config']
        assert config.temperature == 0.2

    @patch('agents_lib.intent_parser.client')
    def test_requests_json_response_format(self, mock_client):
        """Should request JSON response format from LLM."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "intent": "generate_posts",
            "persona": "expert",
            "topic": "topic",
            "search_query": "query",
            "visual_style": "style"
        })
        mock_client.models.generate_content.return_value = mock_response

        agent_intent_parser("test message")

        call_args = mock_client.models.generate_content.call_args
        config = call_args.kwargs['config']
        assert config.response_mime_type == "application/json"


class TestIntentParserEdgeCases:
    """Tests for edge cases in intent parsing."""

    @patch('agents_lib.intent_parser.client')
    def test_handles_empty_message(self, mock_client):
        """Should handle empty message gracefully."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "intent": "clarify",
            "persona": DEFAULT_PERSONA,
            "topic": "",
            "search_query": "",
            "visual_style": DEFAULT_VISUAL_STYLE
        })
        mock_client.models.generate_content.return_value = mock_response

        result = agent_intent_parser("")

        # Should not crash and should return something
        assert "intent" in result

    @patch('agents_lib.intent_parser.client')
    def test_handles_very_long_message(self, mock_client):
        """Should handle very long messages."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "intent": "generate_posts",
            "persona": "expert",
            "topic": "long topic",
            "search_query": "query",
            "visual_style": "style"
        })
        mock_client.models.generate_content.return_value = mock_response

        long_message = "a" * 10000  # Very long message

        result = agent_intent_parser(long_message)

        # Should not crash
        assert "intent" in result

    @patch('agents_lib.intent_parser.client')
    def test_handles_special_characters(self, mock_client):
        """Should handle messages with special characters."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "intent": "generate_posts",
            "persona": "expert",
            "topic": "kubernetes",
            "search_query": "kubernetes",
            "visual_style": "modern"
        })
        mock_client.models.generate_content.return_value = mock_response

        result = agent_intent_parser("create posts about k8s! @#$%^&*()")

        assert "intent" in result

    @patch('agents_lib.intent_parser.client')
    def test_handles_unicode_characters(self, mock_client):
        """Should handle messages with unicode characters."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "intent": "generate_posts",
            "persona": "expert",
            "topic": "technology",
            "search_query": "technology",
            "visual_style": "modern"
        })
        mock_client.models.generate_content.return_value = mock_response

        result = agent_intent_parser("create posts about 技術 and тех")

        assert "intent" in result

    @patch('agents_lib.intent_parser.client')
    def test_handles_history_with_missing_fields(self, mock_client):
        """Should handle history entries with missing fields."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "intent": "generate_posts",
            "persona": "expert",
            "topic": "AI",
            "search_query": "AI",
            "visual_style": "modern"
        })
        mock_client.models.generate_content.return_value = mock_response

        # History with missing 'content' and 'role' fields
        history = [
            {"role": "user"},  # Missing content
            {"content": "hello"},  # Missing role
            {},  # Missing both
        ]

        result = agent_intent_parser("test", history=history)

        # Should not crash
        assert "intent" in result
