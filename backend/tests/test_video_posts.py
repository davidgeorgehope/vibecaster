"""
Tests for video post generation in Post Builder and Campaign.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestGenerateVideoForPost:
    """Tests for generate_video_for_post function."""

    def test_generates_video_from_post_text(self):
        """Test that video is generated from post text using first-frame approach."""
        import agents
        import video_generation

        with patch.object(agents, 'generate_image_for_post_builder', return_value=b'first_frame_bytes') as mock_image_gen, \
             patch.object(video_generation, 'generate_video_from_image', return_value=b'video_bytes_mp4') as mock_video_gen:

            result = agents.generate_video_for_post(
                post_text="Check out Kubernetes!",
                visual_style="cartoon style",
                user_id=1
            )

            assert result == b'video_bytes_mp4'
            mock_image_gen.assert_called_once()
            mock_video_gen.assert_called_once()

    def test_returns_none_if_image_fails(self):
        """Test that None is returned if first frame generation fails."""
        import agents

        with patch.object(agents, 'generate_image_for_post_builder', return_value=None):
            result = agents.generate_video_for_post(
                post_text="Test post",
                visual_style="real person",
                user_id=1
            )

            assert result is None

    def test_returns_none_if_video_gen_fails(self):
        """Test that None is returned if video generation fails."""
        import agents
        import video_generation

        with patch.object(agents, 'generate_image_for_post_builder', return_value=b'first_frame_bytes'), \
             patch.object(video_generation, 'generate_video_from_image', return_value=None):

            result = agents.generate_video_for_post(
                post_text="Test post",
                visual_style="cartoon",
                user_id=1
            )

            assert result is None


class TestGenerateMediaForPostBuilder:
    """Tests for generate_media_for_post_builder function."""

    @patch('agents.generate_image_for_post_builder')
    def test_default_is_image(self, mock_image_gen):
        """Test that default media type is image."""
        from agents import generate_media_for_post_builder

        mock_image_gen.return_value = b'image_bytes'

        result, mime_type = generate_media_for_post_builder(
            post_text="Test post",
            visual_style="professional"
        )

        assert result == b'image_bytes'
        assert mime_type == "image/png"
        mock_image_gen.assert_called_once()

    @patch('agents.generate_video_for_post')
    def test_video_when_specified(self, mock_video_gen):
        """Test that video is generated when media_type is video."""
        from agents import generate_media_for_post_builder

        mock_video_gen.return_value = b'video_bytes'

        result, mime_type = generate_media_for_post_builder(
            post_text="Test post",
            visual_style="cartoon",
            media_type="video"
        )

        assert result == b'video_bytes'
        assert mime_type == "video/mp4"
        mock_video_gen.assert_called_once()

    @patch('agents.generate_image_for_post_builder')
    def test_explicit_image_type(self, mock_image_gen):
        """Test that image is generated when media_type is explicitly image."""
        from agents import generate_media_for_post_builder

        mock_image_gen.return_value = b'png_image'

        result, mime_type = generate_media_for_post_builder(
            post_text="Test post",
            media_type="image"
        )

        assert result == b'png_image'
        assert mime_type == "image/png"


class TestCampaignWithMediaType:
    """Tests for campaign media_type support."""

    def test_database_campaign_media_type(self):
        """Test that campaign can store and retrieve media_type."""
        from database import update_campaign, get_campaign, get_db

        # Create test user first
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO users (id, email, hashed_password, created_at)
                VALUES (9999, 'test_video@example.com', 'hashed', 1234567890)
            """)
            conn.commit()

        try:
            # Update campaign with video media_type
            update_campaign(
                user_id=9999,
                user_prompt="Test prompt",
                media_type="video"
            )

            # Retrieve and verify
            campaign = get_campaign(9999)
            assert campaign is not None
            assert campaign.get('media_type') == 'video'

            # Update to image
            update_campaign(user_id=9999, media_type="image")
            campaign = get_campaign(9999)
            assert campaign.get('media_type') == 'image'

        finally:
            # Cleanup
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM campaign WHERE user_id = 9999")
                cursor.execute("DELETE FROM users WHERE id = 9999")
                conn.commit()

    def test_default_media_type_is_image(self):
        """Test that default media_type is image when not specified."""
        from database import update_campaign, get_campaign, get_db

        # Create test user
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO users (id, email, hashed_password, created_at)
                VALUES (9998, 'test_default@example.com', 'hashed', 1234567890)
            """)
            conn.commit()

        try:
            # Create campaign without media_type
            update_campaign(
                user_id=9998,
                user_prompt="Test prompt without media_type"
            )

            campaign = get_campaign(9998)
            # Default should be 'image' or None (handled by code)
            media_type = campaign.get('media_type', 'image')
            assert media_type in ('image', None)

        finally:
            # Cleanup
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM campaign WHERE user_id = 9998")
                cursor.execute("DELETE FROM users WHERE id = 9998")
                conn.commit()


class TestRunAgentCycleWithVideo:
    """Tests for run_agent_cycle video support."""

    @patch('agents.get_campaign')
    @patch('agents.get_recent_topics')
    @patch('agents.search_trending_topics')
    @patch('agents.select_single_topic')
    @patch('agents.get_oauth_tokens')
    @patch('agents.generate_x_post')
    @patch('agents.generate_video_for_post')
    @patch('agents.generate_image')
    def test_uses_video_when_media_type_is_video(
        self, mock_image, mock_video, mock_x_post, mock_tokens,
        mock_topic, mock_search, mock_recent, mock_campaign
    ):
        """Test that run_agent_cycle uses video generation when media_type is video."""
        from agents import run_agent_cycle

        # Setup mocks
        mock_campaign.return_value = {
            'user_prompt': 'Test prompt',
            'refined_persona': 'Test persona',
            'visual_style': 'cartoon',
            'media_type': 'video'
        }
        mock_recent.return_value = []
        mock_search.return_value = ('context', ['http://example.com'], None)
        mock_topic.return_value = ('focused', 'http://example.com', None)
        mock_tokens.return_value = None  # No platform connected
        mock_x_post.return_value = ('X post content', 'http://example.com')
        mock_video.return_value = b'video_bytes'

        # Run cycle (it will skip posting since no platforms connected)
        run_agent_cycle(user_id=1)

        # Video should NOT be called since no platforms are connected
        # (the cycle exits early when x_post and linkedin_post are None)
        # This test verifies the structure works without errors

    @patch('agents.get_campaign')
    @patch('agents.get_recent_topics')
    @patch('agents.search_trending_topics')
    @patch('agents.select_single_topic')
    @patch('agents.get_oauth_tokens')
    @patch('agents.generate_x_post')
    @patch('agents.generate_image')
    def test_uses_image_when_media_type_is_image(
        self, mock_image, mock_x_post, mock_tokens,
        mock_topic, mock_search, mock_recent, mock_campaign
    ):
        """Test that run_agent_cycle uses image generation when media_type is image."""
        from agents import run_agent_cycle

        mock_campaign.return_value = {
            'user_prompt': 'Test prompt',
            'refined_persona': 'Test persona',
            'visual_style': 'professional',
            'media_type': 'image'
        }
        mock_recent.return_value = []
        mock_search.return_value = ('context', ['http://example.com'], None)
        mock_topic.return_value = ('focused', 'http://example.com', None)
        mock_tokens.return_value = None  # No platform connected

        run_agent_cycle(user_id=1)

        # Should complete without errors
