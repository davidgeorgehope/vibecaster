"""
Tests for agents_lib/post_generator.py

Each test has meaningful assertions that could actually fail.
Covers edge cases: retry logic, URL handling, markdown stripping.
"""
import pytest
from unittest.mock import patch, Mock
import json

from agents_lib.post_generator import (
    generate_x_post,
    generate_linkedin_post,
    _generate_x_post_text,
    _generate_linkedin_post_text,
)


class TestGenerateXPostText:
    """Tests for _generate_x_post_text helper function."""

    @patch('agents_lib.post_generator.client')
    def test_generates_post_text(self, mock_client):
        """Should return generated post text from LLM."""
        mock_response = Mock()
        mock_response.text = "  Breaking news about K8s! Check out the latest updates. #kubernetes  "
        mock_client.models.generate_content.return_value = mock_response

        result = _generate_x_post_text(
            search_context="Kubernetes 1.30 released with new features",
            refined_persona="tech enthusiast",
            user_prompt="teach about kubernetes",
            source_url="https://example.com",
            recent_topics=[]
        )

        assert "Breaking news about K8s" in result
        assert result == result.strip()  # Should be stripped

    @patch('agents_lib.post_generator.client')
    def test_uses_shorter_length_when_url_provided(self, mock_client):
        """Should use 230 char limit when URL will be added."""
        mock_response = Mock()
        mock_response.text = "Short post"
        mock_client.models.generate_content.return_value = mock_response

        _generate_x_post_text(
            search_context="context",
            refined_persona="persona",
            user_prompt="prompt",
            source_url="https://example.com",
            recent_topics=[]
        )

        call_args = mock_client.models.generate_content.call_args
        prompt = call_args.kwargs['contents']
        assert "230" in prompt

    @patch('agents_lib.post_generator.client')
    def test_uses_full_length_when_no_url(self, mock_client):
        """Should use 280 char limit when no URL."""
        mock_response = Mock()
        mock_response.text = "Short post"
        mock_client.models.generate_content.return_value = mock_response

        _generate_x_post_text(
            search_context="context",
            refined_persona="persona",
            user_prompt="prompt",
            source_url=None,
            recent_topics=[]
        )

        call_args = mock_client.models.generate_content.call_args
        prompt = call_args.kwargs['contents']
        assert "280" in prompt

    @patch('agents_lib.post_generator.client')
    def test_includes_recent_topics_in_prompt(self, mock_client):
        """Should include recent topics to avoid in prompt."""
        mock_response = Mock()
        mock_response.text = "New post"
        mock_client.models.generate_content.return_value = mock_response

        _generate_x_post_text(
            search_context="context",
            refined_persona="persona",
            user_prompt="prompt",
            source_url=None,
            recent_topics=["kubernetes", "docker", "observability"]
        )

        call_args = mock_client.models.generate_content.call_args
        prompt = call_args.kwargs['contents']
        assert "kubernetes" in prompt
        assert "docker" in prompt
        assert "FRESH angle" in prompt


class TestGenerateXPost:
    """Tests for generate_x_post function."""

    @patch('agents_lib.post_generator._generate_x_post_text')
    def test_returns_post_and_url(self, mock_generate):
        """Should return tuple of (post_text, source_url)."""
        mock_generate.return_value = "Great post about tech!"

        post, url = generate_x_post(
            search_context="context",
            refined_persona="persona",
            user_prompt="prompt",
            source_url="https://example.com",
            recent_topics=[]
        )

        assert "Great post about tech!" in post
        assert url == "https://example.com"

    @patch('agents_lib.post_generator._generate_x_post_text')
    def test_appends_url_to_post(self, mock_generate):
        """Should append URL if not already in post."""
        mock_generate.return_value = "Post without URL"

        post, url = generate_x_post(
            search_context="context",
            refined_persona="persona",
            user_prompt="prompt",
            source_url="https://example.com",
            recent_topics=[]
        )

        assert "https://example.com" in post
        assert post.endswith("https://example.com")

    @patch('agents_lib.post_generator._generate_x_post_text')
    def test_does_not_duplicate_url(self, mock_generate):
        """Should not add URL if already in post."""
        mock_generate.return_value = "Post with https://example.com included"

        post, url = generate_x_post(
            search_context="context",
            refined_persona="persona",
            user_prompt="prompt",
            source_url="https://example.com",
            recent_topics=[]
        )

        # Should only appear once
        assert post.count("https://example.com") == 1

    @patch('agents_lib.post_generator.time.sleep')
    @patch('agents_lib.post_generator._generate_x_post_text')
    def test_retries_on_failure(self, mock_generate, mock_sleep):
        """Should retry with exponential backoff on failure."""
        mock_generate.side_effect = [
            Exception("First fail"),
            Exception("Second fail"),
            "Success on third try!"
        ]

        post, url = generate_x_post(
            search_context="context",
            refined_persona="persona",
            user_prompt="prompt",
            source_url=None,
            recent_topics=[],
            max_retries=3
        )

        assert "Success on third try!" in post
        assert mock_generate.call_count == 3
        assert mock_sleep.call_count == 2  # Sleep before retry 2 and 3

    @patch('agents_lib.post_generator._generate_x_post_text')
    def test_raises_after_all_retries_fail(self, mock_generate):
        """Should raise exception when all retries fail."""
        mock_generate.side_effect = Exception("Always fails")

        with pytest.raises(Exception):
            generate_x_post(
                search_context="context",
                refined_persona="persona",
                user_prompt="prompt",
                source_url=None,
                recent_topics=[],
                max_retries=3
            )

        assert mock_generate.call_count == 3


class TestGenerateLinkedInPostText:
    """Tests for _generate_linkedin_post_text helper function."""

    @patch('agents_lib.post_generator.client')
    def test_generates_professional_post(self, mock_client):
        """Should return generated LinkedIn post text."""
        mock_response = Mock()
        mock_response.text = "  Professional insight about observability...  "
        mock_client.models.generate_content.return_value = mock_response

        result = _generate_linkedin_post_text(
            search_context="OpenTelemetry best practices",
            refined_persona="observability expert",
            user_prompt="teach about OTEL",
            recent_topics=[]
        )

        assert "Professional insight" in result
        assert result == result.strip()

    @patch('agents_lib.post_generator.client')
    def test_uses_lower_temperature(self, mock_client):
        """Should use temperature 0.7 for professional tone."""
        mock_response = Mock()
        mock_response.text = "Post"
        mock_client.models.generate_content.return_value = mock_response

        _generate_linkedin_post_text("context", "persona", "prompt", [])

        call_args = mock_client.models.generate_content.call_args
        config = call_args.kwargs['config']
        assert config.temperature == 0.7


class TestGenerateLinkedInPost:
    """Tests for generate_linkedin_post function."""

    @patch('agents_lib.post_generator._generate_linkedin_post_text')
    def test_returns_post_text(self, mock_generate):
        """Should return LinkedIn post text."""
        mock_generate.return_value = "Professional LinkedIn content"

        post = generate_linkedin_post(
            search_context="context",
            refined_persona="persona",
            user_prompt="prompt",
            source_url=None,
            recent_topics=[]
        )

        assert "Professional LinkedIn content" in post

    @patch('agents_lib.post_generator._generate_linkedin_post_text')
    def test_appends_url(self, mock_generate):
        """Should append source URL to post."""
        mock_generate.return_value = "Post content"

        post = generate_linkedin_post(
            search_context="context",
            refined_persona="persona",
            user_prompt="prompt",
            source_url="https://example.com/article",
            recent_topics=[]
        )

        assert "https://example.com/article" in post

    @patch('agents_lib.post_generator._generate_linkedin_post_text')
    def test_strips_markdown(self, mock_generate):
        """Should strip markdown formatting from post."""
        mock_generate.return_value = "**Bold** and _italic_ text"

        post = generate_linkedin_post(
            search_context="context",
            refined_persona="persona",
            user_prompt="prompt",
            source_url=None,
            recent_topics=[]
        )

        assert "**" not in post
        assert "_italic_" not in post
        assert "Bold" in post
        assert "italic" in post

    @patch('agents_lib.post_generator.time.sleep')
    @patch('agents_lib.post_generator._generate_linkedin_post_text')
    def test_retries_on_failure(self, mock_generate, mock_sleep):
        """Should retry with exponential backoff on failure."""
        mock_generate.side_effect = [
            Exception("First fail"),
            "Success!"
        ]

        post = generate_linkedin_post(
            search_context="context",
            refined_persona="persona",
            user_prompt="prompt",
            source_url=None,
            recent_topics=[],
            max_retries=2
        )

        assert "Success!" in post
        assert mock_generate.call_count == 2

    @patch('agents_lib.post_generator._generate_linkedin_post_text')
    def test_raises_after_all_retries_fail(self, mock_generate):
        """Should raise exception when all retries fail."""
        mock_generate.side_effect = Exception("Always fails")

        with pytest.raises(Exception):
            generate_linkedin_post(
                search_context="context",
                refined_persona="persona",
                user_prompt="prompt",
                source_url=None,
                recent_topics=[],
                max_retries=2
            )


class TestEdgeCases:
    """Tests for edge cases in post generation."""

    @patch('agents_lib.post_generator._generate_x_post_text')
    def test_handles_empty_recent_topics(self, mock_generate):
        """Should work with empty recent topics list."""
        mock_generate.return_value = "Post"

        post, url = generate_x_post(
            search_context="context",
            refined_persona="persona",
            user_prompt="prompt",
            source_url=None,
            recent_topics=[]
        )

        assert post is not None

    @patch('agents_lib.post_generator._generate_x_post_text')
    def test_handles_none_source_url(self, mock_generate):
        """Should work without source URL."""
        mock_generate.return_value = "Post without link"

        post, url = generate_x_post(
            search_context="context",
            refined_persona="persona",
            user_prompt="prompt",
            source_url=None,
            recent_topics=[]
        )

        assert url is None
        assert "Post without link" in post

    @patch('agents_lib.post_generator._generate_linkedin_post_text')
    def test_handles_very_long_post(self, mock_generate):
        """Should handle very long generated posts."""
        long_post = "a" * 5000
        mock_generate.return_value = long_post

        post = generate_linkedin_post(
            search_context="context",
            refined_persona="persona",
            user_prompt="prompt",
            source_url=None,
            recent_topics=[]
        )

        assert len(post) == 5000
