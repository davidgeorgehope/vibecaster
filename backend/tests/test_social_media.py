"""
Tests for agents_lib/social_media.py

Each test has meaningful assertions that could actually fail.
Covers edge cases: missing tokens, API errors, image upload failures.
"""
import pytest
from unittest.mock import patch, Mock, MagicMock
from io import BytesIO

from agents_lib.social_media import (
    post_to_twitter,
    post_to_linkedin,
    _upload_twitter_media,
    _get_linkedin_author_urn,
    _upload_linkedin_image,
    _build_linkedin_post_data,
)


class TestBuildLinkedInPostData:
    """Tests for _build_linkedin_post_data helper function."""

    def test_builds_text_only_post(self):
        """Should build correct structure for text-only post."""
        result = _build_linkedin_post_data(
            author_urn="urn:li:person:123",
            post_text="Hello LinkedIn!"
        )

        assert result["author"] == "urn:li:person:123"
        assert result["lifecycleState"] == "PUBLISHED"
        assert result["specificContent"]["com.linkedin.ugc.ShareContent"]["shareCommentary"]["text"] == "Hello LinkedIn!"
        assert result["specificContent"]["com.linkedin.ugc.ShareContent"]["shareMediaCategory"] == "NONE"
        assert "media" not in result["specificContent"]["com.linkedin.ugc.ShareContent"]

    def test_builds_post_with_image(self):
        """Should build correct structure for post with image."""
        result = _build_linkedin_post_data(
            author_urn="urn:li:person:123",
            post_text="Check out this image!",
            image_urn="urn:li:digitalmediaAsset:456"
        )

        assert result["specificContent"]["com.linkedin.ugc.ShareContent"]["shareMediaCategory"] == "IMAGE"
        assert len(result["specificContent"]["com.linkedin.ugc.ShareContent"]["media"]) == 1
        assert result["specificContent"]["com.linkedin.ugc.ShareContent"]["media"][0]["media"] == "urn:li:digitalmediaAsset:456"
        assert result["specificContent"]["com.linkedin.ugc.ShareContent"]["media"][0]["status"] == "READY"

    def test_visibility_is_public(self):
        """Should set visibility to PUBLIC."""
        result = _build_linkedin_post_data("urn:li:person:123", "test")

        assert result["visibility"]["com.linkedin.ugc.MemberNetworkVisibility"] == "PUBLIC"


class TestGetLinkedInAuthorUrn:
    """Tests for _get_linkedin_author_urn helper function."""

    @patch('agents_lib.social_media.requests.get')
    def test_returns_author_urn(self, mock_get):
        """Should return correctly formatted author URN."""
        mock_response = Mock()
        mock_response.json.return_value = {"sub": "abc123xyz"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = _get_linkedin_author_urn({"Authorization": "Bearer token"})

        assert result == "urn:li:person:abc123xyz"

    @patch('agents_lib.social_media.requests.get')
    def test_returns_none_on_api_error(self, mock_get):
        """Should return None when API call fails."""
        mock_get.side_effect = Exception("API error")

        result = _get_linkedin_author_urn({"Authorization": "Bearer token"})

        assert result is None

    @patch('agents_lib.social_media.requests.get')
    def test_calls_correct_endpoint(self, mock_get):
        """Should call the correct LinkedIn API endpoint."""
        mock_response = Mock()
        mock_response.json.return_value = {"sub": "123"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        _get_linkedin_author_urn({"Authorization": "Bearer token123"})

        mock_get.assert_called_once()
        call_url = mock_get.call_args[0][0]
        assert "api.linkedin.com" in call_url
        assert "userinfo" in call_url


class TestUploadTwitterMedia:
    """Tests for _upload_twitter_media helper function."""

    @patch('agents_lib.social_media.tweepy.API')
    @patch('agents_lib.social_media.tweepy.OAuth1UserHandler')
    def test_returns_media_id_on_success(self, mock_auth_handler, mock_api_class):
        """Should return media ID on successful upload."""
        mock_api = Mock()
        mock_media = Mock()
        mock_media.media_id = 12345
        mock_api.media_upload.return_value = mock_media
        mock_api_class.return_value = mock_api

        result = _upload_twitter_media(
            b"image bytes",
            "consumer_key",
            "consumer_secret",
            "access_token",
            "access_token_secret"
        )

        assert result == 12345

    @patch('agents_lib.social_media.tweepy.API')
    @patch('agents_lib.social_media.tweepy.OAuth1UserHandler')
    def test_returns_none_on_error(self, mock_auth_handler, mock_api_class):
        """Should return None when upload fails."""
        mock_api = Mock()
        mock_api.media_upload.side_effect = Exception("Upload failed")
        mock_api_class.return_value = mock_api

        result = _upload_twitter_media(
            b"image bytes",
            "consumer_key",
            "consumer_secret",
            "access_token",
            "access_token_secret"
        )

        assert result is None


class TestUploadLinkedInImage:
    """Tests for _upload_linkedin_image helper function."""

    @patch('agents_lib.social_media.requests.put')
    @patch('agents_lib.social_media.requests.post')
    def test_returns_asset_id_on_success(self, mock_post, mock_put):
        """Should return asset ID on successful upload."""
        # Mock register upload response
        mock_register_response = Mock()
        mock_register_response.json.return_value = {
            "value": {
                "uploadMechanism": {
                    "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest": {
                        "uploadUrl": "https://upload.linkedin.com/..."
                    }
                },
                "asset": "urn:li:digitalmediaAsset:xyz789"
            }
        }
        mock_register_response.raise_for_status = Mock()
        mock_post.return_value = mock_register_response

        # Mock upload response
        mock_upload_response = Mock()
        mock_upload_response.raise_for_status = Mock()
        mock_put.return_value = mock_upload_response

        result = _upload_linkedin_image(
            b"image bytes",
            "urn:li:person:123",
            {"Authorization": "Bearer token"},
            {"access_token": "token"}
        )

        assert result == "urn:li:digitalmediaAsset:xyz789"

    @patch('agents_lib.social_media.requests.post')
    def test_returns_none_on_register_error(self, mock_post):
        """Should return None when register upload fails."""
        mock_post.side_effect = Exception("Register failed")

        result = _upload_linkedin_image(
            b"image bytes",
            "urn:li:person:123",
            {"Authorization": "Bearer token"},
            {"access_token": "token"}
        )

        assert result is None


class TestPostToTwitter:
    """Tests for post_to_twitter function."""

    @patch('agents_lib.social_media.get_oauth_tokens')
    def test_returns_false_when_no_tokens(self, mock_get_tokens):
        """Should return False when user has no Twitter tokens."""
        mock_get_tokens.return_value = None

        result = post_to_twitter(user_id=123, post_text="Hello Twitter!")

        assert result is False

    @patch('agents_lib.social_media.os.getenv')
    @patch('agents_lib.social_media.tweepy.Client')
    @patch('agents_lib.social_media.get_oauth_tokens')
    def test_returns_true_on_successful_post(self, mock_get_tokens, mock_client_class, mock_getenv):
        """Should return True when tweet is posted successfully."""
        mock_get_tokens.return_value = {
            "access_token": "token",
            "refresh_token": "secret"
        }
        mock_getenv.return_value = "api_key"

        mock_client = Mock()
        mock_client.create_tweet.return_value = Mock(data={"id": "12345"})
        mock_client_class.return_value = mock_client

        result = post_to_twitter(user_id=123, post_text="Hello Twitter!")

        assert result is True
        mock_client.create_tweet.assert_called_once_with(text="Hello Twitter!")

    @patch('agents_lib.social_media.os.getenv')
    @patch('agents_lib.social_media.tweepy.Client')
    @patch('agents_lib.social_media.get_oauth_tokens')
    def test_returns_false_on_api_error(self, mock_get_tokens, mock_client_class, mock_getenv):
        """Should return False when Twitter API fails."""
        mock_get_tokens.return_value = {
            "access_token": "token",
            "refresh_token": "secret"
        }
        mock_getenv.return_value = "api_key"

        mock_client = Mock()
        mock_client.create_tweet.side_effect = Exception("API error")
        mock_client_class.return_value = mock_client

        result = post_to_twitter(user_id=123, post_text="Hello Twitter!")

        assert result is False

    @patch('agents_lib.social_media._upload_twitter_media')
    @patch('agents_lib.social_media.os.getenv')
    @patch('agents_lib.social_media.tweepy.Client')
    @patch('agents_lib.social_media.get_oauth_tokens')
    def test_uploads_image_when_provided(self, mock_get_tokens, mock_client_class, mock_getenv, mock_upload):
        """Should upload image and attach to tweet when provided."""
        mock_get_tokens.return_value = {
            "access_token": "token",
            "refresh_token": "secret"
        }
        mock_getenv.return_value = "api_key"
        mock_upload.return_value = 99999

        mock_client = Mock()
        mock_client.create_tweet.return_value = Mock(data={"id": "12345"})
        mock_client_class.return_value = mock_client

        result = post_to_twitter(
            user_id=123,
            post_text="With image!",
            image_bytes=b"fake image"
        )

        assert result is True
        mock_upload.assert_called_once()
        mock_client.create_tweet.assert_called_once_with(text="With image!", media_ids=[99999])


class TestPostToLinkedIn:
    """Tests for post_to_linkedin function."""

    @patch('agents_lib.social_media.get_oauth_tokens')
    def test_returns_false_when_no_tokens(self, mock_get_tokens):
        """Should return False when user has no LinkedIn tokens."""
        mock_get_tokens.return_value = None

        result = post_to_linkedin(user_id=123, post_text="Hello LinkedIn!")

        assert result is False

    @patch('agents_lib.social_media.requests.post')
    @patch('agents_lib.social_media._get_linkedin_author_urn')
    @patch('agents_lib.social_media.get_oauth_tokens')
    def test_returns_true_on_successful_post(self, mock_get_tokens, mock_get_urn, mock_post):
        """Should return True when post is created successfully."""
        mock_get_tokens.return_value = {"access_token": "token"}
        mock_get_urn.return_value = "urn:li:person:123"

        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {"id": "post_123"}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        result = post_to_linkedin(user_id=123, post_text="Hello LinkedIn!")

        assert result is True

    @patch('agents_lib.social_media._get_linkedin_author_urn')
    @patch('agents_lib.social_media.get_oauth_tokens')
    def test_returns_false_when_urn_fetch_fails(self, mock_get_tokens, mock_get_urn):
        """Should return False when author URN cannot be retrieved."""
        mock_get_tokens.return_value = {"access_token": "token"}
        mock_get_urn.return_value = None

        result = post_to_linkedin(user_id=123, post_text="Hello LinkedIn!")

        assert result is False

    @patch('agents_lib.social_media.requests.post')
    @patch('agents_lib.social_media._get_linkedin_author_urn')
    @patch('agents_lib.social_media.get_oauth_tokens')
    def test_returns_false_on_api_error(self, mock_get_tokens, mock_get_urn, mock_post):
        """Should return False when LinkedIn API fails."""
        mock_get_tokens.return_value = {"access_token": "token"}
        mock_get_urn.return_value = "urn:li:person:123"
        mock_post.side_effect = Exception("API error")

        result = post_to_linkedin(user_id=123, post_text="Hello LinkedIn!")

        assert result is False

    @patch('agents_lib.social_media.requests.post')
    @patch('agents_lib.social_media._upload_linkedin_image')
    @patch('agents_lib.social_media._get_linkedin_author_urn')
    @patch('agents_lib.social_media.get_oauth_tokens')
    def test_uploads_image_when_provided(self, mock_get_tokens, mock_get_urn, mock_upload, mock_post):
        """Should upload image when provided."""
        mock_get_tokens.return_value = {"access_token": "token"}
        mock_get_urn.return_value = "urn:li:person:123"
        mock_upload.return_value = "urn:li:digitalmediaAsset:789"

        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {"id": "post_123"}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        result = post_to_linkedin(
            user_id=123,
            post_text="With image!",
            image_bytes=b"fake image"
        )

        assert result is True
        mock_upload.assert_called_once()


class TestEdgeCases:
    """Tests for edge cases in social media posting."""

    @patch('agents_lib.social_media.os.getenv')
    @patch('agents_lib.social_media.tweepy.Client')
    @patch('agents_lib.social_media.get_oauth_tokens')
    def test_twitter_handles_empty_post_text(self, mock_get_tokens, mock_client_class, mock_getenv):
        """Should handle empty post text (API might reject it)."""
        mock_get_tokens.return_value = {
            "access_token": "token",
            "refresh_token": "secret"
        }
        mock_getenv.return_value = "api_key"

        mock_client = Mock()
        mock_client.create_tweet.side_effect = Exception("Tweet text cannot be empty")
        mock_client_class.return_value = mock_client

        result = post_to_twitter(user_id=123, post_text="")

        assert result is False

    @patch('agents_lib.social_media.requests.post')
    @patch('agents_lib.social_media._get_linkedin_author_urn')
    @patch('agents_lib.social_media.get_oauth_tokens')
    def test_linkedin_handles_very_long_post(self, mock_get_tokens, mock_get_urn, mock_post):
        """Should handle very long post text."""
        mock_get_tokens.return_value = {"access_token": "token"}
        mock_get_urn.return_value = "urn:li:person:123"

        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {"id": "post_123"}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        long_text = "a" * 5000
        result = post_to_linkedin(user_id=123, post_text=long_text)

        assert result is True
        # Verify the long text was passed through
        call_json = mock_post.call_args.kwargs['json']
        assert len(call_json['specificContent']['com.linkedin.ugc.ShareContent']['shareCommentary']['text']) == 5000
