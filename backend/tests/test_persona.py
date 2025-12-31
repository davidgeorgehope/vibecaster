"""
Tests for agents_lib/persona.py

Each test has meaningful assertions that could actually fail.
Covers edge cases: null, empty, error states.
"""
import pytest
from unittest.mock import patch, Mock
import json

from agents_lib.persona import (
    analyze_user_prompt,
    create_fallback_persona,
)


class TestCreateFallbackPersona:
    """Tests for create_fallback_persona function."""

    def test_preserves_user_prompt_in_persona(self):
        """Should include user prompt in fallback persona."""
        prompt = "Mario and Luigi teaching cloud computing"
        persona, visual = create_fallback_persona(prompt)

        assert prompt in persona
        assert "IMPORTANT" in persona or "creative direction" in persona.lower()

    def test_preserves_user_prompt_in_visual_style(self):
        """Should include user prompt in fallback visual style."""
        prompt = "anime style with bright colors"
        persona, visual = create_fallback_persona(prompt)

        assert prompt in visual

    def test_returns_tuple_of_two_strings(self):
        """Should return a tuple of exactly two strings."""
        result = create_fallback_persona("test prompt")

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], str)

    def test_handles_empty_prompt(self):
        """Should handle empty prompt without crashing."""
        persona, visual = create_fallback_persona("")

        assert isinstance(persona, str)
        assert isinstance(visual, str)

    def test_handles_special_characters(self):
        """Should handle prompts with special characters."""
        prompt = "test with @#$%^&*() and 'quotes' and \"double quotes\""
        persona, visual = create_fallback_persona(prompt)

        assert prompt in persona
        assert prompt in visual


class TestAnalyzeUserPrompt:
    """Tests for analyze_user_prompt function."""

    @patch('agents_lib.persona.client')
    def test_returns_parsed_persona_and_style(self, mock_client):
        """Should return parsed persona and visual style from LLM."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "refined_persona": "A tech-savvy anime girl",
            "visual_style": "bright anime style with pastel colors"
        })
        mock_client.models.generate_content.return_value = mock_response

        persona, visual = analyze_user_prompt("anime girl teaching AI")

        assert "anime" in persona.lower()
        assert "bright" in visual or "anime" in visual.lower()

    @patch('agents_lib.persona.client')
    def test_uses_moderate_temperature(self, mock_client):
        """Should use temperature 0.5 for faithful output."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "refined_persona": "test persona",
            "visual_style": "test style"
        })
        mock_client.models.generate_content.return_value = mock_response

        analyze_user_prompt("test prompt")

        call_args = mock_client.models.generate_content.call_args
        config = call_args.kwargs['config']
        assert config.temperature == 0.5

    @patch('agents_lib.persona.client')
    def test_uses_high_thinking_level(self, mock_client):
        """Should use HIGH thinking level for quality analysis."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "refined_persona": "test persona",
            "visual_style": "test style"
        })
        mock_client.models.generate_content.return_value = mock_response

        analyze_user_prompt("test prompt")

        call_args = mock_client.models.generate_content.call_args
        config = call_args.kwargs['config']
        assert config.thinking_config.thinking_level == "HIGH"

    @patch('agents_lib.persona.client')
    def test_requests_json_response(self, mock_client):
        """Should request JSON response format."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "refined_persona": "test persona",
            "visual_style": "test style"
        })
        mock_client.models.generate_content.return_value = mock_response

        analyze_user_prompt("test prompt")

        call_args = mock_client.models.generate_content.call_args
        config = call_args.kwargs['config']
        assert config.response_mime_type == "application/json"

    @patch('agents_lib.persona.client')
    def test_returns_fallback_on_llm_error(self, mock_client):
        """Should return fallback when LLM fails."""
        mock_client.models.generate_content.side_effect = Exception("API error")

        persona, visual = analyze_user_prompt("Gordon Ramsay teaching cooking")

        # Should return fallback that preserves original prompt
        assert "Gordon Ramsay teaching cooking" in persona
        assert "Gordon Ramsay teaching cooking" in visual

    @patch('agents_lib.persona.client')
    def test_returns_fallback_on_invalid_json(self, mock_client):
        """Should return fallback when LLM returns invalid JSON."""
        mock_response = Mock()
        mock_response.text = "not valid json {"
        mock_client.models.generate_content.return_value = mock_response

        persona, visual = analyze_user_prompt("test prompt")

        # Should return fallback
        assert "test prompt" in persona or "test prompt" in visual

    @patch('agents_lib.persona.client')
    def test_handles_missing_keys_in_response(self, mock_client):
        """Should handle missing keys in LLM response."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "refined_persona": "only persona, no visual style"
            # missing "visual_style"
        })
        mock_client.models.generate_content.return_value = mock_response

        persona, visual = analyze_user_prompt("test prompt")

        assert persona == "only persona, no visual style"
        assert visual == ""  # Should return empty string for missing key

    @patch('agents_lib.persona.client')
    def test_includes_user_prompt_in_llm_request(self, mock_client):
        """Should include user prompt in the request to LLM."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "refined_persona": "persona",
            "visual_style": "style"
        })
        mock_client.models.generate_content.return_value = mock_response

        analyze_user_prompt("Mario explaining kubernetes")

        call_args = mock_client.models.generate_content.call_args
        contents = call_args.kwargs['contents']
        assert "Mario explaining kubernetes" in contents


class TestAnalyzeUserPromptEdgeCases:
    """Tests for edge cases in analyze_user_prompt."""

    @patch('agents_lib.persona.client')
    def test_handles_empty_prompt(self, mock_client):
        """Should handle empty prompt."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "refined_persona": "general assistant",
            "visual_style": "professional"
        })
        mock_client.models.generate_content.return_value = mock_response

        persona, visual = analyze_user_prompt("")

        assert isinstance(persona, str)
        assert isinstance(visual, str)

    @patch('agents_lib.persona.client')
    def test_handles_very_long_prompt(self, mock_client):
        """Should handle very long prompts."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "refined_persona": "persona for long prompt",
            "visual_style": "style for long prompt"
        })
        mock_client.models.generate_content.return_value = mock_response

        long_prompt = "a" * 10000
        persona, visual = analyze_user_prompt(long_prompt)

        assert isinstance(persona, str)
        assert isinstance(visual, str)

    @patch('agents_lib.persona.client')
    def test_handles_unicode_characters(self, mock_client):
        """Should handle prompts with unicode characters."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "refined_persona": "persona with unicode 日本語",
            "visual_style": "anime style 漫画"
        })
        mock_client.models.generate_content.return_value = mock_response

        persona, visual = analyze_user_prompt("teach about 日本語 and тех")

        assert isinstance(persona, str)
        assert isinstance(visual, str)

    @patch('agents_lib.persona.client')
    def test_handles_json_special_characters(self, mock_client):
        """Should handle prompts that could break JSON."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "refined_persona": "persona",
            "visual_style": "style"
        })
        mock_client.models.generate_content.return_value = mock_response

        # Prompt with characters that could break JSON
        prompt = 'test with "quotes" and {braces} and \\ backslashes'
        persona, visual = analyze_user_prompt(prompt)

        assert isinstance(persona, str)
        assert isinstance(visual, str)

    @patch('agents_lib.persona.client')
    def test_handles_newlines_in_prompt(self, mock_client):
        """Should handle prompts with newlines."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "refined_persona": "persona",
            "visual_style": "style"
        })
        mock_client.models.generate_content.return_value = mock_response

        prompt = "line 1\nline 2\nline 3"
        persona, visual = analyze_user_prompt(prompt)

        assert isinstance(persona, str)
        assert isinstance(visual, str)
