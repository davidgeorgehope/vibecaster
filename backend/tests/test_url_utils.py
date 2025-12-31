"""
Tests for agents_lib/url_utils.py

Each test has meaningful assertions that could actually fail.
Covers edge cases: null, empty, boundary conditions, error states.
"""
import pytest
from unittest.mock import patch, Mock
import requests

from agents_lib.url_utils import (
    clean_url_text,
    is_youtube_url,
    extract_html_title,
    url_seems_relevant_to_topic,
    is_soft_404,
    validate_url,
    validate_and_select_url,
    resolve_redirect_url,
)


class TestCleanUrlText:
    """Tests for clean_url_text function."""

    def test_returns_none_for_none_input(self):
        """Null input should return None."""
        result = clean_url_text(None)
        assert result is None

    def test_returns_none_for_empty_string(self):
        """Empty string should return None."""
        result = clean_url_text("")
        assert result is None

    def test_returns_none_for_whitespace_only(self):
        """Whitespace-only string should return None."""
        result = clean_url_text("   \t\n  ")
        assert result is None

    def test_strips_surrounding_quotes(self):
        """Should remove surrounding quotes."""
        result = clean_url_text('"https://example.com"')
        assert result == "https://example.com"

    def test_strips_single_quotes(self):
        """Should remove surrounding single quotes."""
        result = clean_url_text("'https://example.com'")
        assert result == "https://example.com"

    def test_strips_trailing_punctuation(self):
        """Should remove trailing punctuation like ), ., ;"""
        assert clean_url_text("https://example.com)") == "https://example.com"
        assert clean_url_text("https://example.com.") == "https://example.com"
        assert clean_url_text("https://example.com;") == "https://example.com"
        assert clean_url_text("https://example.com,") == "https://example.com"

    def test_returns_none_for_null_string_literal(self):
        """'null' and 'none' strings should return None."""
        assert clean_url_text("null") is None
        assert clean_url_text("NULL") is None
        assert clean_url_text("none") is None
        assert clean_url_text("None") is None

    def test_preserves_valid_url(self):
        """Valid URLs should pass through correctly."""
        url = "https://example.com/path?query=value"
        result = clean_url_text(url)
        assert result == url


class TestIsYoutubeUrl:
    """Tests for is_youtube_url function."""

    def test_detects_youtube_com(self):
        """Should detect youtube.com URLs."""
        assert is_youtube_url("https://youtube.com/watch?v=abc123") is True
        assert is_youtube_url("http://youtube.com/watch?v=abc123") is True

    def test_detects_www_youtube_com(self):
        """Should detect www.youtube.com URLs."""
        assert is_youtube_url("https://www.youtube.com/watch?v=abc123") is True

    def test_detects_m_youtube_com(self):
        """Should detect mobile youtube URLs."""
        assert is_youtube_url("https://m.youtube.com/watch?v=abc123") is True

    def test_detects_youtu_be(self):
        """Should detect youtu.be shortlinks."""
        assert is_youtube_url("https://youtu.be/abc123") is True

    def test_rejects_non_youtube_urls(self):
        """Should reject non-YouTube URLs."""
        assert is_youtube_url("https://vimeo.com/video") is False
        assert is_youtube_url("https://example.com") is False
        assert is_youtube_url("https://google.com") is False

    def test_handles_invalid_url_gracefully(self):
        """Should return False for malformed URLs without crashing."""
        assert is_youtube_url("not a url at all") is False
        assert is_youtube_url("") is False

    def test_handles_url_with_youtube_in_path(self):
        """Should not match youtube in path, only host."""
        assert is_youtube_url("https://example.com/youtube") is False


class TestExtractHtmlTitle:
    """Tests for extract_html_title function."""

    def test_returns_empty_for_none_content(self):
        """None content should return empty string."""
        result = extract_html_title(None)
        assert result == ""

    def test_returns_empty_for_empty_content(self):
        """Empty content should return empty string."""
        result = extract_html_title("")
        assert result == ""

    def test_extracts_simple_title(self):
        """Should extract a simple title."""
        html = "<html><head><title>My Page Title</title></head></html>"
        result = extract_html_title(html)
        assert result == "My Page Title"

    def test_extracts_title_case_insensitive(self):
        """Should handle TITLE tag in any case."""
        html = "<html><head><TITLE>Upper Case Title</TITLE></head></html>"
        result = extract_html_title(html)
        assert result == "Upper Case Title"

    def test_handles_title_with_attributes(self):
        """Should handle title tags with attributes."""
        html = '<html><head><title lang="en">Title With Attrs</title></head></html>'
        result = extract_html_title(html)
        assert result == "Title With Attrs"

    def test_normalizes_whitespace(self):
        """Should collapse multiple whitespace characters."""
        html = "<title>Title   with\n\tmultiple   spaces</title>"
        result = extract_html_title(html)
        assert result == "Title with multiple spaces"

    def test_decodes_html_entities(self):
        """Should decode HTML entities like &amp;"""
        html = "<title>Tom &amp; Jerry</title>"
        result = extract_html_title(html)
        assert result == "Tom & Jerry"

    def test_returns_empty_when_no_title_tag(self):
        """Should return empty string when no title tag exists."""
        html = "<html><head></head><body>No title here</body></html>"
        result = extract_html_title(html)
        assert result == ""


class TestUrlSeemsRelevantToTopic:
    """Tests for url_seems_relevant_to_topic function."""

    def test_returns_true_for_empty_topic(self):
        """Empty topic should always be considered relevant."""
        assert url_seems_relevant_to_topic("", "https://example.com", None) is True
        assert url_seems_relevant_to_topic(None, "https://example.com", None) is True

    def test_matches_topic_in_url(self):
        """Should match when topic keyword appears in URL."""
        result = url_seems_relevant_to_topic(
            "kubernetes deployment",
            "https://example.com/kubernetes-best-practices",
            None
        )
        assert result is True

    def test_matches_topic_in_html_title(self):
        """Should match when topic keyword appears in HTML title."""
        html = "<title>Understanding Kubernetes Deployments</title>"
        result = url_seems_relevant_to_topic(
            "kubernetes deployment",
            "https://example.com/article/123",
            html
        )
        assert result is True

    def test_rejects_unrelated_content(self):
        """Should reject when no topic keywords match."""
        html = "<title>Best Recipes for Summer</title>"
        result = url_seems_relevant_to_topic(
            "kubernetes deployment",
            "https://recipes.com/summer-salad",
            html
        )
        assert result is False

    def test_ignores_stopwords_in_topic(self):
        """Should ignore common stopwords when matching."""
        # "the" and "in" are stopwords, so only "cloud" should be checked
        result = url_seems_relevant_to_topic(
            "the cloud in computing",
            "https://aws.amazon.com/cloud-services",
            "<title>Cloud Computing Guide</title>"
        )
        assert result is True


class TestIsSoft404:
    """Tests for is_soft_404 function."""

    def test_returns_false_for_empty_content(self):
        """Empty content is not a soft 404."""
        result = is_soft_404("", "https://example.com")
        assert result is False

    def test_detects_page_not_found_text(self):
        """Should detect 'page not found' as soft 404."""
        html = "<html><body><h1>Page not found</h1></body></html>"
        result = is_soft_404(html, "https://example.com/missing")
        assert result is True

    def test_detects_404_in_title(self):
        """Should detect '404' in title as soft 404."""
        html = "<html><head><title>404 - Not Found</title></head></html>"
        result = is_soft_404(html, "https://example.com/missing")
        assert result is True

    def test_detects_error_404_text(self):
        """Should detect 'error 404' text."""
        html = "<html><body>Error 404: The page you requested does not exist</body></html>"
        result = is_soft_404(html, "https://example.com/missing")
        assert result is True

    def test_detects_elastic_specific_pattern(self):
        """Should detect Elastic's specific 404 pattern."""
        html = "<html><body>Hmmm… something's amiss. We couldn't find that page.</body></html>"
        result = is_soft_404(html, "https://elastic.co/missing")
        assert result is True

    def test_accepts_valid_article_page(self):
        """Should accept a normal article page."""
        html = """
        <html>
        <head><title>How to Use Kubernetes</title></head>
        <body>
        <article class="post">
            <h1>How to Use Kubernetes</h1>
            <p>Kubernetes is a container orchestration platform...</p>
            """ + "x" * 6000 + """
        </article>
        </body>
        </html>
        """
        result = is_soft_404(html, "https://example.com/kubernetes")
        assert result is False

    def test_detects_suspiciously_short_page(self):
        """Should flag very short pages without article content."""
        html = "<html><body>Loading...</body></html>"
        result = is_soft_404(html, "https://example.com/page")
        assert result is True


class TestValidateUrl:
    """Tests for validate_url function."""

    @patch('agents_lib.url_utils.requests.get')
    def test_returns_valid_for_200_status(self, mock_get):
        """Should return valid for HTTP 200 with good content."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.url = "https://example.com/page"
        mock_response.text = "<html><article>Real content here</article>" + "x" * 6000
        mock_get.return_value = mock_response

        is_valid, html, status, final_url = validate_url("https://example.com/page")

        assert is_valid is True
        assert status == 200
        assert html is not None
        assert final_url == "https://example.com/page"

    @patch('agents_lib.url_utils.requests.get')
    def test_returns_invalid_for_404_status(self, mock_get):
        """Should return invalid for HTTP 404."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.url = "https://example.com/missing"
        mock_get.return_value = mock_response

        is_valid, html, status, final_url = validate_url("https://example.com/missing")

        assert is_valid is False
        assert status == 404

    @patch('agents_lib.url_utils.requests.get')
    def test_returns_invalid_for_soft_404(self, mock_get):
        """Should detect soft 404 and return invalid."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.url = "https://example.com/missing"
        mock_response.text = "<html><body>Page not found</body></html>"
        mock_get.return_value = mock_response

        is_valid, html, status, final_url = validate_url("https://example.com/missing")

        assert is_valid is False
        assert status == 404  # Treated as 404

    @patch('agents_lib.url_utils.requests.get')
    def test_handles_timeout(self, mock_get):
        """Should handle request timeout gracefully."""
        mock_get.side_effect = requests.exceptions.Timeout("Connection timed out")

        is_valid, html, status, final_url = validate_url("https://slow-server.com/page")

        assert is_valid is False
        assert status is None
        assert html is None

    @patch('agents_lib.url_utils.requests.get')
    def test_handles_connection_error(self, mock_get):
        """Should handle connection errors gracefully."""
        mock_get.side_effect = requests.exceptions.ConnectionError("Failed to connect")

        is_valid, html, status, final_url = validate_url("https://unreachable.com/page")

        assert is_valid is False
        assert status is None

    @patch('agents_lib.url_utils.requests.head')
    def test_head_request_when_fetch_content_false(self, mock_head):
        """Should use HEAD request when fetch_content=False."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.url = "https://example.com/page"
        mock_head.return_value = mock_response

        is_valid, html, status, final_url = validate_url(
            "https://example.com/page",
            fetch_content=False
        )

        assert is_valid is True
        assert html is None  # No content fetched
        assert status == 200
        mock_head.assert_called_once()


class TestValidateAndSelectUrl:
    """Tests for validate_and_select_url function."""

    @patch('agents_lib.url_utils.validate_url')
    def test_returns_first_valid_url(self, mock_validate):
        """Should return the first valid URL from the list."""
        mock_validate.side_effect = [
            (False, None, 404, "https://bad.com"),
            (True, "<html>content</html>", 200, "https://good.com"),
            (True, "<html>other</html>", 200, "https://also-good.com"),
        ]

        url, html = validate_and_select_url([
            "https://bad.com",
            "https://good.com",
            "https://also-good.com",
        ])

        assert url == "https://good.com"
        assert html == "<html>content</html>"
        # Should stop after finding first valid
        assert mock_validate.call_count == 2

    @patch('agents_lib.url_utils.validate_url')
    def test_returns_none_when_all_invalid(self, mock_validate):
        """Should return None, None when all URLs are invalid."""
        mock_validate.return_value = (False, None, 404, "url")

        url, html = validate_and_select_url([
            "https://bad1.com",
            "https://bad2.com",
        ])

        assert url is None
        assert html is None

    def test_handles_empty_list(self):
        """Should handle empty URL list gracefully."""
        url, html = validate_and_select_url([])
        assert url is None
        assert html is None


class TestResolveRedirectUrl:
    """Tests for resolve_redirect_url function."""

    @patch('agents_lib.url_utils.requests.head')
    def test_returns_final_url_after_redirect(self, mock_head):
        """Should return final URL after following redirects."""
        mock_response = Mock()
        mock_response.url = "https://final-destination.com/page"
        mock_head.return_value = mock_response

        result = resolve_redirect_url("https://redirect.com/short")

        assert result == "https://final-destination.com/page"

    @patch('agents_lib.url_utils.requests.head')
    @patch('agents_lib.url_utils.requests.get')
    def test_falls_back_to_get_when_head_fails(self, mock_get, mock_head):
        """Should fall back to GET if HEAD fails."""
        mock_head.side_effect = Exception("HEAD not supported")

        mock_response = Mock()
        mock_response.url = "https://final.com/page"
        mock_response.close = Mock()
        mock_get.return_value = mock_response

        result = resolve_redirect_url("https://redirect.com/link")

        assert result == "https://final.com/page"
        mock_get.assert_called_once()

    @patch('agents_lib.url_utils.requests.head')
    @patch('agents_lib.url_utils.requests.get')
    def test_returns_original_url_on_complete_failure(self, mock_get, mock_head):
        """Should return original URL if both HEAD and GET fail."""
        mock_head.side_effect = Exception("HEAD failed")
        mock_get.side_effect = Exception("GET failed")

        result = resolve_redirect_url("https://unreachable.com/link")

        assert result == "https://unreachable.com/link"

    @patch('agents_lib.url_utils.requests.head')
    def test_returns_original_when_no_redirect(self, mock_head):
        """Should return original URL when there's no redirect."""
        mock_response = Mock()
        mock_response.url = "https://example.com/page"  # Same as input
        mock_head.return_value = mock_response

        result = resolve_redirect_url("https://example.com/page")

        assert result == "https://example.com/page"
