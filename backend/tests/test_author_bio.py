"""
Tests for author_bio module.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestGenerateCharacterReference:
    """Tests for generate_character_reference function."""

    @patch('author_bio.client')
    def test_generates_image_from_description(self, mock_client):
        """Test that character reference is generated from description."""
        from author_bio import generate_character_reference

        # Mock response with inline_data
        mock_part = Mock()
        mock_part.inline_data = Mock()
        mock_part.inline_data.data = b'fake_image_bytes'

        mock_candidate = Mock()
        mock_candidate.content.parts = [mock_part]

        mock_response = Mock()
        mock_response.candidates = [mock_candidate]

        mock_client.models.generate_content.return_value = mock_response

        result = generate_character_reference(
            description="A friendly tech educator in their 30s",
            style="real_person"
        )

        assert result == b'fake_image_bytes'
        mock_client.models.generate_content.assert_called_once()

    @patch('author_bio.client')
    def test_handles_different_styles(self, mock_client):
        """Test that different styles modify the prompt."""
        from author_bio import generate_character_reference

        mock_part = Mock()
        mock_part.inline_data = Mock()
        mock_part.inline_data.data = b'cartoon_image'

        mock_response = Mock()
        mock_response.candidates = [Mock(content=Mock(parts=[mock_part]))]

        mock_client.models.generate_content.return_value = mock_response

        result = generate_character_reference(
            description="A funny character",
            style="cartoon"
        )

        assert result == b'cartoon_image'

        # Verify prompt contains cartoon style
        call_args = mock_client.models.generate_content.call_args
        prompt = call_args.kwargs['contents']
        assert 'cartoon' in prompt.lower()

    @patch('author_bio.client')
    def test_returns_none_on_error(self, mock_client):
        """Test that None is returned when generation fails."""
        from author_bio import generate_character_reference

        mock_client.models.generate_content.side_effect = Exception("API error")

        result = generate_character_reference(
            description="Test description",
            style="real_person"
        )

        assert result is None


class TestGenerateImageWithReference:
    """Tests for generate_image_with_reference function."""

    @patch('author_bio.client')
    def test_includes_reference_in_contents(self, mock_client):
        """Test that reference image is included in generation request."""
        from author_bio import generate_image_with_reference
        from PIL import Image
        from io import BytesIO

        # Create a minimal valid PNG
        img = Image.new('RGB', (10, 10), color='red')
        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')
        reference_bytes = img_bytes.getvalue()

        mock_part = Mock()
        mock_part.inline_data = Mock()
        mock_part.inline_data.data = b'generated_scene'
        # Also set as_image to None to avoid fallback
        mock_part.as_image = None

        mock_response = Mock()
        mock_response.candidates = [Mock(content=Mock(parts=[mock_part]))]

        mock_client.models.generate_content.return_value = mock_response

        result = generate_image_with_reference(
            prompt="A scene with the character",
            reference_image=reference_bytes,
            style="real_person"
        )

        assert result == b'generated_scene'

        # Verify call was made
        mock_client.models.generate_content.assert_called_once()


class TestSearchAuthorImages:
    """Tests for search_author_images function."""

    @patch('author_bio.client')
    def test_returns_search_results(self, mock_client):
        """Test that search returns structured results."""
        from author_bio import search_author_images

        mock_response = Mock()
        mock_response.text = '[{"url": "http://example.com/img.jpg", "title": "Author Photo"}]'
        mock_response.candidates = []

        mock_client.models.generate_content.return_value = mock_response

        results = search_author_images("John Doe", limit=5)

        assert len(results) == 1
        assert results[0]['url'] == "http://example.com/img.jpg"

    @patch('author_bio.client')
    def test_handles_empty_results(self, mock_client):
        """Test that empty search returns empty list."""
        from author_bio import search_author_images

        mock_response = Mock()
        mock_response.text = '[]'
        mock_response.candidates = []

        mock_client.models.generate_content.return_value = mock_response

        results = search_author_images("Unknown Person")

        assert results == []


class TestValidateImage:
    """Tests for validate_image function."""

    def test_validates_valid_png(self):
        """Test that valid PNG is validated correctly."""
        from author_bio import validate_image
        from PIL import Image
        from io import BytesIO

        # Create valid PNG
        img = Image.new('RGB', (100, 100), color='blue')
        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')

        result = validate_image(img_bytes.getvalue())

        assert result['valid'] is True
        assert result['width'] == 100
        assert result['height'] == 100
        assert result['format'] == 'PNG'
        assert result['mime_type'] == 'image/png'

    def test_validates_valid_jpeg(self):
        """Test that valid JPEG is validated correctly."""
        from author_bio import validate_image
        from PIL import Image
        from io import BytesIO

        # Create valid JPEG
        img = Image.new('RGB', (50, 50), color='green')
        img_bytes = BytesIO()
        img.save(img_bytes, format='JPEG')

        result = validate_image(img_bytes.getvalue())

        assert result['valid'] is True
        assert result['format'] == 'JPEG'
        assert result['mime_type'] == 'image/jpeg'

    def test_rejects_invalid_data(self):
        """Test that invalid image data is rejected."""
        from author_bio import validate_image

        result = validate_image(b'not an image')

        assert result['valid'] is False
        assert 'error' in result


class TestDownloadImageFromUrl:
    """Tests for download_image_from_url function."""

    def test_downloads_valid_image(self):
        """Test that valid image is downloaded."""
        import requests as real_requests
        from author_bio import download_image_from_url
        from PIL import Image as PILImage
        from io import BytesIO

        with patch.object(real_requests, 'get') as mock_get:
            # Create valid image
            img = PILImage.new('RGB', (10, 10), color='white')
            img_bytes = BytesIO()
            img.save(img_bytes, format='PNG')

            mock_response = Mock()
            mock_response.headers = {'content-type': 'image/png'}
            mock_response.content = img_bytes.getvalue()
            mock_response.raise_for_status = Mock()

            mock_get.return_value = mock_response

            result = download_image_from_url("http://example.com/image.png")

            assert result is not None
            assert len(result) > 0

    def test_returns_none_for_non_image(self):
        """Test that non-image content returns None."""
        import requests as real_requests
        from author_bio import download_image_from_url

        with patch.object(real_requests, 'get') as mock_get:
            mock_response = Mock()
            mock_response.headers = {'content-type': 'text/html'}
            mock_response.raise_for_status = Mock()

            mock_get.return_value = mock_response

            result = download_image_from_url("http://example.com/page.html")

            assert result is None
