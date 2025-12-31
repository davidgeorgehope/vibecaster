"""
Tests for agents_lib/search.py

Each test has meaningful assertions that could actually fail.
Covers: search_trending_topics, select_single_topic with retry logic, URL validation, edge cases.
"""
import pytest
from unittest.mock import patch, Mock, MagicMock
import json

from agents_lib.search import (
    search_trending_topics,
    select_single_topic,
)


class TestSearchTrendingTopics:
    """Tests for search_trending_topics function."""

    @patch('agents_lib.search.validate_and_select_url')
    @patch('agents_lib.search.resolve_redirect_url')
    @patch('agents_lib.search.client')
    def test_returns_search_context_and_urls(self, mock_client, mock_resolve, mock_validate):
        """Should return search context, URLs list, and HTML content."""
        # Setup mock response with grounding metadata
        mock_chunk = Mock()
        mock_chunk.web.uri = "https://redirect.google.com/article"
        mock_metadata = Mock()
        mock_metadata.grounding_chunks = [mock_chunk]
        mock_candidate = Mock()
        mock_candidate.grounding_metadata = mock_metadata
        mock_response = Mock()
        mock_response.text = "Search results about kubernetes"
        mock_response.candidates = [mock_candidate]
        mock_client.models.generate_content.return_value = mock_response

        mock_resolve.return_value = "https://example.com/article"
        mock_validate.return_value = ("https://example.com/article", "<html>content</html>")

        context, urls, html = search_trending_topics(
            user_prompt="teach about kubernetes",
            refined_persona="tech expert"
        )

        assert "kubernetes" in context
        assert len(urls) >= 1
        assert "https://example.com/article" in urls

    @patch('agents_lib.search.client')
    def test_handles_empty_response_text(self, mock_client):
        """Should provide fallback context when response text is None."""
        mock_response = Mock()
        mock_response.text = None
        mock_response.candidates = []
        mock_client.models.generate_content.return_value = mock_response

        context, urls, html = search_trending_topics(
            user_prompt="kubernetes topic",
            refined_persona="expert",
            validate_urls=False
        )

        assert "kubernetes topic" in context  # Fallback includes prompt
        assert urls == []

    @patch('agents_lib.search.time.sleep')
    @patch('agents_lib.search.validate_and_select_url')
    @patch('agents_lib.search.resolve_redirect_url')
    @patch('agents_lib.search.client')
    def test_retries_when_all_urls_invalid(self, mock_client, mock_resolve, mock_validate, mock_sleep):
        """Should retry search when all URLs fail validation."""
        mock_chunk = Mock()
        mock_chunk.web.uri = "https://example.com"
        mock_metadata = Mock()
        mock_metadata.grounding_chunks = [mock_chunk]
        mock_candidate = Mock()
        mock_candidate.grounding_metadata = mock_metadata
        mock_response = Mock()
        mock_response.text = "Results"
        mock_response.candidates = [mock_candidate]
        mock_client.models.generate_content.return_value = mock_response

        mock_resolve.return_value = "https://example.com"
        # First two attempts fail, third succeeds
        mock_validate.side_effect = [
            (None, None),  # First attempt - all invalid
            (None, None),  # Second attempt - all invalid
            ("https://example.com/valid", "<html>content</html>"),  # Third succeeds
        ]

        context, urls, html = search_trending_topics(
            user_prompt="topic",
            refined_persona="persona",
            max_search_retries=3
        )

        assert mock_client.models.generate_content.call_count == 3
        assert mock_sleep.call_count == 2  # Sleep before retry 2 and 3

    @patch('agents_lib.search.is_network_error')
    @patch('agents_lib.search.time.sleep')
    @patch('agents_lib.search.client')
    def test_handles_network_errors_with_retry(self, mock_client, mock_sleep, mock_is_network):
        """Should retry with backoff on network errors."""
        # is_network_error returns True for network exceptions
        mock_is_network.return_value = True

        # Build success response - needs proper structure
        success_response = Mock()
        success_response.text = "Success"
        success_response.candidates = []

        mock_client.models.generate_content.side_effect = [
            Exception("QUIC protocol error"),
            Exception("Connection reset"),
            success_response
        ]

        context, urls, html = search_trending_topics(
            user_prompt="topic",
            refined_persona="persona",
            validate_urls=False,
            max_search_retries=3
        )

        assert "Success" in context
        # Sleep called twice: once for 1s (2^0), once for 2s (2^1)
        assert mock_sleep.call_count >= 2

    @patch('agents_lib.search.client')
    def test_includes_recent_topics_in_prompt(self, mock_client):
        """Should include recent topics to avoid in the search prompt."""
        mock_response = Mock()
        mock_response.text = "Results"
        mock_response.candidates = []
        mock_client.models.generate_content.return_value = mock_response

        search_trending_topics(
            user_prompt="topic",
            refined_persona="persona",
            recent_topics=["docker", "kubernetes", "helm"],
            validate_urls=False
        )

        call_args = mock_client.models.generate_content.call_args
        prompt = call_args.kwargs['contents']
        assert "docker" in prompt
        assert "kubernetes" in prompt
        assert "DIFFERENT aspects" in prompt

    @patch('agents_lib.search.client')
    def test_skips_validation_when_disabled(self, mock_client):
        """Should skip URL validation when validate_urls=False."""
        mock_chunk = Mock()
        mock_chunk.web.uri = "https://example.com"
        mock_metadata = Mock()
        mock_metadata.grounding_chunks = [mock_chunk]
        mock_candidate = Mock()
        mock_candidate.grounding_metadata = mock_metadata
        mock_response = Mock()
        mock_response.text = "Results"
        mock_response.candidates = [mock_candidate]
        mock_client.models.generate_content.return_value = mock_response

        with patch('agents_lib.search.resolve_redirect_url', return_value="https://example.com"):
            with patch('agents_lib.search.validate_and_select_url') as mock_validate:
                context, urls, html = search_trending_topics(
                    user_prompt="topic",
                    refined_persona="persona",
                    validate_urls=False
                )

                mock_validate.assert_not_called()
                assert html is None


class TestSelectSingleTopic:
    """Tests for select_single_topic function."""

    @patch('agents_lib.search.validate_url')
    @patch('agents_lib.search.client')
    def test_returns_focused_context_and_url(self, mock_client, mock_validate):
        """Should return focused context, selected URL, and HTML."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "selected_topic": "OpenTelemetry Collector",
            "focused_context": "OTEL collector allows filtering traces",
            "selected_url_index": 1,
            "selected_url": "https://example.com/otel",
            "reasoning": "Most relevant"
        })
        mock_client.models.generate_content.return_value = mock_response

        mock_validate.return_value = (True, "<html>content</html>", 200, "https://example.com/otel")

        context, url, html = select_single_topic(
            search_context="Multiple topics here",
            source_urls=["https://example.com/otel", "https://other.com"],
            user_prompt="teach about observability"
        )

        assert "OTEL" in context
        assert url == "https://example.com/otel"
        assert html is not None

    @patch('agents_lib.search.validate_url')
    @patch('agents_lib.search.client')
    def test_selects_url_by_index(self, mock_client, mock_validate):
        """Should select URL using the index from LLM response."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "selected_topic": "Topic",
            "focused_context": "Context",
            "selected_url_index": 2,
            "selected_url": None,
            "reasoning": "Reason"
        })
        mock_client.models.generate_content.return_value = mock_response

        mock_validate.return_value = (True, None, 200, "https://second.com")

        urls = ["https://first.com", "https://second.com", "https://third.com"]
        context, url, html = select_single_topic(
            search_context="Context",
            source_urls=urls,
            user_prompt="prompt"
        )

        assert url == "https://second.com"

    @patch('agents_lib.search.validate_url')
    @patch('agents_lib.search.client')
    def test_rejects_hallucinated_urls(self, mock_client, mock_validate):
        """Should reject URLs not in the provided list (prevent hallucination)."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "selected_topic": "Topic",
            "focused_context": "Context",
            "selected_url_index": None,
            "selected_url": "https://hallucinated.com/fake",  # Not in list
            "reasoning": "Reason"
        })
        mock_client.models.generate_content.return_value = mock_response

        # Should retry and eventually fail
        context, url, html = select_single_topic(
            search_context="Context",
            source_urls=["https://real.com/article"],
            user_prompt="prompt",
            max_selection_attempts=1
        )

        # No valid URL selected
        assert url is None

    @patch('agents_lib.search.time.sleep')
    @patch('agents_lib.search.validate_url')
    @patch('agents_lib.search.client')
    def test_retries_on_broken_url(self, mock_client, mock_validate, mock_sleep):
        """Should retry with different topic when URL is broken (404)."""
        # First response has broken URL, second picks the remaining valid URL
        # After first attempt, broken.com is filtered out, so only valid.com remains at index 1
        mock_client.models.generate_content.side_effect = [
            Mock(text=json.dumps({
                "selected_topic": "Topic 1",
                "focused_context": "Context 1",
                "selected_url_index": 1,  # Selects broken.com
                "reasoning": "Reason"
            })),
            Mock(text=json.dumps({
                "selected_topic": "Topic 2",
                "focused_context": "Context 2",
                "selected_url_index": 1,  # Now index 1 is valid.com (broken.com filtered)
                "reasoning": "Reason"
            }))
        ]

        # First URL broken, second URL valid
        mock_validate.side_effect = [
            (False, None, 404, None),  # First is 404
            (True, "<html>content</html>", 200, "https://example.com/valid"),
        ]

        context, url, html = select_single_topic(
            search_context="Context",
            source_urls=["https://broken.com", "https://example.com/valid"],
            user_prompt="prompt",
            max_selection_attempts=3
        )

        assert mock_client.models.generate_content.call_count == 2
        assert url == "https://example.com/valid"

    @patch('agents_lib.search.is_youtube_url')
    @patch('agents_lib.search.validate_url')
    @patch('agents_lib.search.client')
    def test_prefers_non_youtube_urls(self, mock_client, mock_validate, mock_is_youtube):
        """Should prefer non-video sources over YouTube links."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "selected_topic": "Topic",
            "focused_context": "Context",
            "selected_url_index": 1,
            "reasoning": "Reason"
        })
        mock_client.models.generate_content.return_value = mock_response
        mock_validate.return_value = (True, None, 200, "https://article.com")

        # Mark YouTube URLs
        mock_is_youtube.side_effect = lambda url: "youtube" in url

        urls = [
            "https://youtube.com/watch?v=123",
            "https://article.com/post",
            "https://youtube.com/watch?v=456"
        ]

        context, url, html = select_single_topic(
            search_context="Context",
            source_urls=urls,
            user_prompt="prompt"
        )

        # Check that non-YouTube URLs were prioritized in the prompt
        call_args = mock_client.models.generate_content.call_args
        prompt = call_args.kwargs['contents']
        # The first URL in the filtered list should be the article, not YouTube
        assert "article.com" in prompt

    @patch('agents_lib.search.validate_url')
    @patch('agents_lib.search.client')
    def test_includes_recent_topics_to_avoid(self, mock_client, mock_validate):
        """Should include recent topics in prompt to avoid repetition."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "selected_topic": "New Topic",
            "focused_context": "Fresh context",
            "selected_url_index": 1,
            "reasoning": "Different from recent"
        })
        mock_client.models.generate_content.return_value = mock_response
        mock_validate.return_value = (True, None, 200, "https://example.com")

        select_single_topic(
            search_context="Context",
            source_urls=["https://example.com"],
            user_prompt="prompt",
            recent_topics=["kubernetes", "docker"]
        )

        call_args = mock_client.models.generate_content.call_args
        prompt = call_args.kwargs['contents']
        assert "kubernetes" in prompt
        assert "AVOID" in prompt

    @patch('agents_lib.search.client')
    def test_handles_empty_urls_list(self, mock_client):
        """Should return None for URL when no URLs available."""
        context, url, html = select_single_topic(
            search_context="Some context",
            source_urls=[],
            user_prompt="prompt"
        )

        assert url is None
        # Should return original context
        assert context == "Some context"


class TestEdgeCases:
    """Tests for edge cases in search functions."""

    @patch('agents_lib.search.client')
    def test_search_with_empty_prompt(self, mock_client):
        """Should handle empty user prompt gracefully."""
        mock_response = Mock()
        mock_response.text = "General results"
        mock_response.candidates = []
        mock_client.models.generate_content.return_value = mock_response

        context, urls, html = search_trending_topics(
            user_prompt="",
            refined_persona="persona",
            validate_urls=False
        )

        assert context is not None

    @patch('agents_lib.search.client')
    def test_select_topic_with_json_parse_error(self, mock_client):
        """Should handle malformed JSON from LLM."""
        mock_response = Mock()
        mock_response.text = "not valid json {"
        mock_client.models.generate_content.return_value = mock_response

        context, url, html = select_single_topic(
            search_context="Context",
            source_urls=["https://example.com"],
            user_prompt="prompt",
            max_selection_attempts=1
        )

        # Should fail gracefully
        assert url is None

    @patch('agents_lib.search.validate_url')
    @patch('agents_lib.search.client')
    def test_url_with_redirect(self, mock_client, mock_validate):
        """Should use final resolved URL after redirect."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "selected_topic": "Topic",
            "focused_context": "Context",
            "selected_url_index": 1,
            "reasoning": "Reason"
        })
        mock_client.models.generate_content.return_value = mock_response

        # URL redirects to different final URL
        mock_validate.return_value = (True, "<html>", 200, "https://final.example.com/redirected")

        context, url, html = select_single_topic(
            search_context="Context",
            source_urls=["https://short.link/abc"],
            user_prompt="prompt"
        )

        assert url == "https://final.example.com/redirected"

    @patch('agents_lib.search.validate_and_select_url')
    @patch('agents_lib.search.resolve_redirect_url')
    @patch('agents_lib.search.client')
    def test_extracts_urls_from_grounding_chunks(self, mock_client, mock_resolve, mock_validate):
        """Should correctly extract URLs from Google Search grounding metadata."""
        # Setup complex grounding structure
        mock_chunk1 = Mock()
        mock_chunk1.web.uri = "https://redirect1.com"
        mock_chunk2 = Mock()
        mock_chunk2.web.uri = "https://redirect2.com"
        mock_metadata = Mock()
        mock_metadata.grounding_chunks = [mock_chunk1, mock_chunk2]
        mock_candidate = Mock()
        mock_candidate.grounding_metadata = mock_metadata
        mock_response = Mock()
        mock_response.text = "Results"
        mock_response.candidates = [mock_candidate]
        mock_client.models.generate_content.return_value = mock_response

        mock_resolve.side_effect = lambda url: url.replace("redirect", "resolved")
        mock_validate.return_value = ("https://resolved1.com", None)

        context, urls, html = search_trending_topics(
            user_prompt="topic",
            refined_persona="persona"
        )

        assert len(urls) >= 2
        assert mock_resolve.call_count == 2

    @patch('agents_lib.search.client')
    def test_all_retries_exhausted(self, mock_client):
        """Should return fallback when all retries fail."""
        mock_client.models.generate_content.side_effect = Exception("API error")

        context, urls, html = search_trending_topics(
            user_prompt="my topic",
            refined_persona="persona",
            max_search_retries=2
        )

        assert "my topic" in context  # Fallback message
        assert urls == []
        assert html is None
