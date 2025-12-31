"""
End-to-end tests for video generation pipeline.

These tests use mocks for the Veo API but test actual file handling,
database operations, and the full generation flow.
"""

import pytest
import json
import os
import sys
import tempfile
from unittest.mock import Mock, patch, MagicMock
from io import BytesIO
from PIL import Image

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def create_test_image_bytes() -> bytes:
    """Create valid PNG image bytes for testing."""
    img = Image.new('RGB', (100, 100), color='blue')
    img_bytes = BytesIO()
    img.save(img_bytes, format='PNG')
    return img_bytes.getvalue()


def create_test_video_bytes(size: int = 50000) -> bytes:
    """Create fake video bytes of specified size for testing."""
    # Create bytes that look like a minimal MP4 header
    header = b'\x00\x00\x00\x1c\x66\x74\x79\x70\x69\x73\x6f\x6d'  # ftyp box
    padding = b'\x00' * (size - len(header))
    return header + padding


@pytest.fixture
def mock_database():
    """Mock database operations."""
    with patch('database.get_author_bio') as mock_get_bio, \
         patch('database.create_video_job') as mock_create_job, \
         patch('database.update_video_job') as mock_update_job, \
         patch('database.create_video_scene') as mock_create_scene, \
         patch('database.update_video_scene') as mock_update_scene, \
         patch('database.get_video_job') as mock_get_job, \
         patch('database.get_video_scenes') as mock_get_scenes:

        mock_get_bio.return_value = None
        mock_create_job.return_value = 1
        mock_create_scene.return_value = 1

        yield {
            'get_author_bio': mock_get_bio,
            'create_video_job': mock_create_job,
            'update_video_job': mock_update_job,
            'create_video_scene': mock_create_scene,
            'update_video_scene': mock_update_scene,
            'get_video_job': mock_get_job,
            'get_video_scenes': mock_get_scenes
        }


@pytest.fixture
def mock_veo_client():
    """Mock the Veo/Gemini client for video generation."""
    with patch('video_generation.client') as mock_client:
        yield mock_client


class TestVideoGenerationFlow:
    """End-to-end tests for the full video generation pipeline."""

    def test_full_video_generation_flow(self, mock_database, mock_veo_client):
        """Test complete video generation with mocked Veo API."""
        from video_generation import generate_video_stream

        # Mock script planning response
        mock_script = {
            "title": "Test Video",
            "summary": "A test video",
            "scenes": [
                {
                    "scene_number": 1,
                    "narration": "Scene one narration",
                    "visual_description": "A test scene",
                    "image_prompt": "A blue scene",
                    "video_prompt": "Camera pans slowly",
                    "include_character": False
                }
            ],
            "total_scenes": 1,
            "estimated_duration": 8
        }

        # Setup mock for script planning (text generation)
        script_response = Mock()
        script_response.text = json.dumps(mock_script)

        # Setup mock for image generation
        mock_image_part = Mock()
        mock_image_part.inline_data = Mock()
        mock_image_part.inline_data.data = create_test_image_bytes()
        image_response = Mock()
        image_response.candidates = [Mock(content=Mock(parts=[mock_image_part]))]

        # Setup mock for video generation
        mock_video = Mock()
        mock_video.video = Mock()

        # Mock video.video.save() to write actual bytes to the temp file
        def save_video(path):
            with open(path, 'wb') as f:
                f.write(create_test_video_bytes(50000))

        mock_video.video.save = save_video

        mock_operation = Mock()
        mock_operation.done = True
        mock_operation.response = Mock()
        mock_operation.response.generated_videos = [mock_video]

        mock_veo_client.models.generate_content.side_effect = [script_response, image_response]
        mock_veo_client.models.generate_videos.return_value = mock_operation
        mock_veo_client.files.download = Mock()

        # Mock types.Image.from_file to avoid actual file operations
        with patch('video_generation.types.Image.from_file') as mock_from_file:
            mock_from_file.return_value = Mock()

            # Run the stream
            events = list(generate_video_stream(
                user_id=1,
                topic="Test Topic",
                style="educational",
                target_duration=8
            ))

        # Parse events
        event_types = [json.loads(e.strip())['type'] for e in events]

        # Verify expected events
        assert 'job_created' in event_types
        assert 'planning' in event_types
        assert 'script_ready' in event_types
        assert 'scene_image' in event_types
        assert 'scene_video' in event_types
        assert 'scene_complete' in event_types
        assert 'complete' in event_types
        assert 'error' not in event_types

        # Verify database was updated
        mock_database['update_video_job'].assert_called()
        mock_database['update_video_scene'].assert_called()

        # Verify final status is complete
        final_call_args = mock_database['update_video_job'].call_args_list[-1]
        assert 'complete' in str(final_call_args) or 'final_video' in str(final_call_args)


class TestVideoGenerationErrors:
    """Tests for error handling in video generation."""

    def test_timeout_logs_detailed_error(self, mock_database, mock_veo_client):
        """Test that timeout provides detailed error message."""
        from video_generation import generate_video_from_image

        # Mock operation that never completes
        mock_operation = Mock()
        mock_operation.done = False

        mock_veo_client.models.generate_videos.return_value = mock_operation
        mock_veo_client.operations.get = Mock(return_value=mock_operation)

        with patch('video_generation.time.sleep'):  # Skip actual sleep
            with patch('video_generation.types.Image.from_file') as mock_from_file:
                mock_from_file.return_value = Mock()
                with patch('video_generation.logger') as mock_logger:
                    result = generate_video_from_image(
                        first_frame_bytes=create_test_image_bytes(),
                        video_prompt="Test prompt"
                    )

        assert result is None
        # Verify timeout was logged with details
        mock_logger.error.assert_called()
        error_call = str(mock_logger.error.call_args_list[-1])
        assert 'timed out' in error_call.lower()

    def test_small_video_bytes_returns_none(self, mock_database, mock_veo_client):
        """Test that video smaller than minimum size returns None."""
        from video_generation import generate_video_from_image

        # Mock video that saves only 100 bytes (below MIN_VIDEO_SIZE)
        mock_video = Mock()
        mock_video.video = Mock()

        def save_tiny_video(path):
            with open(path, 'wb') as f:
                f.write(b'\x00' * 100)  # Only 100 bytes

        mock_video.video.save = save_tiny_video

        mock_operation = Mock()
        mock_operation.done = True
        mock_operation.response = Mock()
        mock_operation.response.generated_videos = [mock_video]

        mock_veo_client.models.generate_videos.return_value = mock_operation
        mock_veo_client.files.download = Mock()

        with patch('video_generation.time.sleep'):
            with patch('video_generation.types.Image.from_file') as mock_from_file:
                mock_from_file.return_value = Mock()
                result = generate_video_from_image(
                    first_frame_bytes=create_test_image_bytes(),
                    video_prompt="Test prompt"
                )

        assert result is None

    def test_empty_generated_videos_list_returns_none(self, mock_database, mock_veo_client):
        """Test that empty generated_videos list returns None."""
        from video_generation import generate_video_from_image

        mock_operation = Mock()
        mock_operation.done = True
        mock_operation.response = Mock()
        mock_operation.response.generated_videos = []  # Empty list

        mock_veo_client.models.generate_videos.return_value = mock_operation

        with patch('video_generation.time.sleep'):
            with patch('video_generation.types.Image.from_file') as mock_from_file:
                mock_from_file.return_value = Mock()
                result = generate_video_from_image(
                    first_frame_bytes=create_test_image_bytes(),
                    video_prompt="Test prompt"
                )

        assert result is None

    def test_video_save_failure_returns_none(self, mock_database, mock_veo_client):
        """Test that failure in video.video.save() returns None."""
        from video_generation import generate_video_from_image

        mock_video = Mock()
        mock_video.video = Mock()
        mock_video.video.save = Mock(side_effect=Exception("Save failed"))

        mock_operation = Mock()
        mock_operation.done = True
        mock_operation.response = Mock()
        mock_operation.response.generated_videos = [mock_video]

        mock_veo_client.models.generate_videos.return_value = mock_operation
        mock_veo_client.files.download = Mock()

        with patch('video_generation.time.sleep'):
            with patch('video_generation.types.Image.from_file') as mock_from_file:
                mock_from_file.return_value = Mock()
                result = generate_video_from_image(
                    first_frame_bytes=create_test_image_bytes(),
                    video_prompt="Test prompt"
                )

        assert result is None

    def test_missing_video_attribute_returns_none(self, mock_database, mock_veo_client):
        """Test that video object without .video attribute returns None."""
        from video_generation import generate_video_from_image

        mock_video = Mock(spec=[])  # Empty spec - no attributes

        mock_operation = Mock()
        mock_operation.done = True
        mock_operation.response = Mock()
        mock_operation.response.generated_videos = [mock_video]

        mock_veo_client.models.generate_videos.return_value = mock_operation

        with patch('video_generation.time.sleep'):
            with patch('video_generation.types.Image.from_file') as mock_from_file:
                mock_from_file.return_value = Mock()
                result = generate_video_from_image(
                    first_frame_bytes=create_test_image_bytes(),
                    video_prompt="Test prompt"
                )

        assert result is None


class TestSceneFailureHandling:
    """Tests for handling scene-level failures."""

    def test_scene_image_failure_continues_to_next_scene(self, mock_database, mock_veo_client):
        """Test that image generation failure doesn't stop entire pipeline."""
        from video_generation import generate_video_stream

        # Mock script with 2 scenes
        mock_script = {
            "title": "Test Video",
            "summary": "A test video",
            "scenes": [
                {"scene_number": 1, "narration": "Scene 1", "image_prompt": "Scene 1",
                 "video_prompt": "Motion 1", "include_character": False},
                {"scene_number": 2, "narration": "Scene 2", "image_prompt": "Scene 2",
                 "video_prompt": "Motion 2", "include_character": False}
            ],
            "total_scenes": 2,
            "estimated_duration": 16
        }

        script_response = Mock()
        script_response.text = json.dumps(mock_script)

        # First image fails, second succeeds
        failed_image_response = Mock()
        failed_image_response.candidates = []

        mock_image_part = Mock()
        mock_image_part.inline_data = Mock()
        mock_image_part.inline_data.data = create_test_image_bytes()
        success_image_response = Mock()
        success_image_response.candidates = [Mock(content=Mock(parts=[mock_image_part]))]

        # Video generation succeeds
        mock_video = Mock()
        mock_video.video = Mock()
        mock_video.video.save = lambda path: open(path, 'wb').write(create_test_video_bytes())

        mock_operation = Mock()
        mock_operation.done = True
        mock_operation.response = Mock()
        mock_operation.response.generated_videos = [mock_video]

        mock_veo_client.models.generate_content.side_effect = [
            script_response,
            failed_image_response,  # Scene 1 image fails
            success_image_response  # Scene 2 image succeeds
        ]
        mock_veo_client.models.generate_videos.return_value = mock_operation
        mock_veo_client.files.download = Mock()

        with patch('video_generation.types.Image.from_file') as mock_from_file:
            mock_from_file.return_value = Mock()
            events = list(generate_video_stream(
                user_id=1,
                topic="Test Topic",
                style="educational",
                target_duration=16
            ))

        event_types = [json.loads(e.strip())['type'] for e in events]

        # Should have error for scene 1 but continue to scene 2
        assert 'scene_error' in event_types
        assert 'scene_complete' in event_types
        # Should still complete (with partial success)
        assert 'complete' in event_types or 'stitching' in event_types

    def test_all_scenes_fail_returns_error(self, mock_database, mock_veo_client):
        """Test that if all scenes fail, pipeline returns error."""
        from video_generation import generate_video_stream

        mock_script = {
            "title": "Test Video",
            "summary": "A test video",
            "scenes": [
                {"scene_number": 1, "narration": "Scene 1", "image_prompt": "Scene 1",
                 "video_prompt": "Motion 1", "include_character": False}
            ],
            "total_scenes": 1,
            "estimated_duration": 8
        }

        script_response = Mock()
        script_response.text = json.dumps(mock_script)

        # Image generation fails
        failed_image_response = Mock()
        failed_image_response.candidates = []

        mock_veo_client.models.generate_content.side_effect = [
            script_response,
            failed_image_response
        ]

        events = list(generate_video_stream(
            user_id=1,
            topic="Test Topic",
            style="educational",
            target_duration=8
        ))

        event_types = [json.loads(e.strip())['type'] for e in events]

        # Should have error event
        assert 'error' in event_types
        # Should not have complete
        assert 'complete' not in event_types

        # Verify database was updated with error
        update_calls = mock_database['update_video_job'].call_args_list
        error_call = [c for c in update_calls if 'error' in str(c)]
        assert len(error_call) > 0


class TestDatabaseStateTransitions:
    """Tests for proper database state management."""

    def test_job_status_transitions(self, mock_database, mock_veo_client):
        """Test that job status transitions correctly through pipeline."""
        from video_generation import generate_video_stream

        mock_script = {
            "title": "Test Video",
            "summary": "A test",
            "scenes": [],
            "total_scenes": 0,
            "estimated_duration": 0
        }

        script_response = Mock()
        script_response.text = json.dumps(mock_script)

        mock_veo_client.models.generate_content.return_value = script_response

        list(generate_video_stream(
            user_id=1,
            topic="Test",
            style="educational",
            target_duration=8
        ))

        # Verify status transitions
        update_calls = mock_database['update_video_job'].call_args_list
        statuses = [str(call) for call in update_calls]

        # Should have planning status
        assert any('planning' in s for s in statuses)

    def test_scene_status_updated_on_image_failure(self, mock_database, mock_veo_client):
        """Test that scene status is set to error when image fails."""
        from video_generation import generate_video_stream

        mock_script = {
            "title": "Test Video",
            "summary": "A test",
            "scenes": [
                {"scene_number": 1, "narration": "Scene 1", "image_prompt": "Scene 1",
                 "video_prompt": "Motion 1", "include_character": False}
            ],
            "total_scenes": 1,
            "estimated_duration": 8
        }

        script_response = Mock()
        script_response.text = json.dumps(mock_script)

        failed_image_response = Mock()
        failed_image_response.candidates = []

        mock_veo_client.models.generate_content.side_effect = [
            script_response,
            failed_image_response
        ]

        list(generate_video_stream(
            user_id=1,
            topic="Test",
            style="educational",
            target_duration=8
        ))

        # Verify scene was updated with error
        scene_update_calls = mock_database['update_video_scene'].call_args_list
        error_calls = [c for c in scene_update_calls if 'error' in str(c)]
        assert len(error_calls) > 0


class TestValidVideoBytes:
    """Tests for video bytes validation."""

    def test_valid_video_bytes_returned(self, mock_database, mock_veo_client):
        """Test that valid video bytes are returned successfully."""
        from video_generation import generate_video_from_image

        video_bytes = create_test_video_bytes(50000)

        mock_video = Mock()
        mock_video.video = Mock()
        mock_video.video.save = lambda path: open(path, 'wb').write(video_bytes)

        mock_operation = Mock()
        mock_operation.done = True
        mock_operation.response = Mock()
        mock_operation.response.generated_videos = [mock_video]

        mock_veo_client.models.generate_videos.return_value = mock_operation
        mock_veo_client.files.download = Mock()

        with patch('video_generation.time.sleep'):
            with patch('video_generation.types.Image.from_file') as mock_from_file:
                mock_from_file.return_value = Mock()
                result = generate_video_from_image(
                    first_frame_bytes=create_test_image_bytes(),
                    video_prompt="Test prompt"
                )

        assert result is not None
        assert len(result) == 50000

    def test_minimum_size_boundary(self, mock_database, mock_veo_client):
        """Test video at exactly minimum size boundary."""
        from video_generation import generate_video_from_image

        # Exactly 10000 bytes (MIN_VIDEO_SIZE)
        video_bytes = create_test_video_bytes(10000)

        mock_video = Mock()
        mock_video.video = Mock()
        mock_video.video.save = lambda path: open(path, 'wb').write(video_bytes)

        mock_operation = Mock()
        mock_operation.done = True
        mock_operation.response = Mock()
        mock_operation.response.generated_videos = [mock_video]

        mock_veo_client.models.generate_videos.return_value = mock_operation
        mock_veo_client.files.download = Mock()

        with patch('video_generation.time.sleep'):
            with patch('video_generation.types.Image.from_file') as mock_from_file:
                mock_from_file.return_value = Mock()
                result = generate_video_from_image(
                    first_frame_bytes=create_test_image_bytes(),
                    video_prompt="Test prompt"
                )

        # 10000 bytes is exactly at minimum, should pass
        assert result is not None

    def test_below_minimum_size_fails(self, mock_database, mock_veo_client):
        """Test video below minimum size fails."""
        from video_generation import generate_video_from_image

        # 9999 bytes (below MIN_VIDEO_SIZE of 10000)
        video_bytes = create_test_video_bytes(9999)

        mock_video = Mock()
        mock_video.video = Mock()
        mock_video.video.save = lambda path: open(path, 'wb').write(video_bytes)

        mock_operation = Mock()
        mock_operation.done = True
        mock_operation.response = Mock()
        mock_operation.response.generated_videos = [mock_video]

        mock_veo_client.models.generate_videos.return_value = mock_operation
        mock_veo_client.files.download = Mock()

        with patch('video_generation.time.sleep'):
            with patch('video_generation.types.Image.from_file') as mock_from_file:
                mock_from_file.return_value = Mock()
                result = generate_video_from_image(
                    first_frame_bytes=create_test_image_bytes(),
                    video_prompt="Test prompt"
                )

        assert result is None


class TestJobStatusPolling:
    """Tests for job status polling (for frontend resume functionality)."""

    def test_get_job_status_returns_scene_statuses(self, mock_database):
        """Test that get_video_job_status returns scene statuses for polling."""
        from video_generation import get_video_job_status

        # Mock job data
        mock_database['get_video_job'].return_value = {
            'id': 1,
            'job_id': 'test-job-123',
            'status': 'generating',
            'title': 'Test Video',
            'script': '{}',
            'error_message': None,
            'created_at': 1000000,
            'updated_at': 1000001,
            'final_video': None
        }

        # Mock scene data with various statuses
        mock_database['get_video_scenes'].return_value = [
            {'scene_number': 1, 'status': 'complete', 'narration': 'Scene 1'},
            {'scene_number': 2, 'status': 'generating_video', 'narration': 'Scene 2'},
            {'scene_number': 3, 'status': 'pending', 'narration': 'Scene 3'}
        ]

        result = get_video_job_status(job_id=1, user_id=1)

        assert result is not None
        assert result['status'] == 'generating'
        assert result['scenes'] is not None
        assert len(result['scenes']) == 3
        assert result['scenes'][0]['status'] == 'complete'
        assert result['scenes'][1]['status'] == 'generating_video'
        assert result['scenes'][2]['status'] == 'pending'

    def test_get_job_status_complete_includes_video(self, mock_database):
        """Test that completed job includes video base64."""
        from video_generation import get_video_job_status

        mock_database['get_video_job'].return_value = {
            'id': 1,
            'job_id': 'test-job-123',
            'status': 'complete',
            'title': 'Test Video',
            'script': '{}',
            'error_message': None,
            'created_at': 1000000,
            'updated_at': 1000001,
            'final_video': b'fake video bytes here',
            'final_video_mime': 'video/mp4'
        }
        mock_database['get_video_scenes'].return_value = []

        result = get_video_job_status(job_id=1, user_id=1)

        assert result is not None
        assert result['status'] == 'complete'
        assert result['has_final_video'] == True
        assert 'final_video_base64' in result
        assert result['final_video_mime'] == 'video/mp4'

    def test_get_job_status_partial_includes_video(self, mock_database):
        """Test that partial job (some scenes failed) includes video."""
        from video_generation import get_video_job_status

        mock_database['get_video_job'].return_value = {
            'id': 1,
            'job_id': 'test-job-123',
            'status': 'partial',
            'title': 'Test Video',
            'script': '{}',
            'error_message': None,
            'created_at': 1000000,
            'updated_at': 1000001,
            'final_video': b'partial video bytes',
            'final_video_mime': 'video/mp4'
        }
        mock_database['get_video_scenes'].return_value = [
            {'scene_number': 1, 'status': 'complete', 'narration': 'Scene 1'},
            {'scene_number': 2, 'status': 'error', 'narration': 'Scene 2'}
        ]

        result = get_video_job_status(job_id=1, user_id=1)

        assert result is not None
        assert result['status'] == 'partial'
        assert result['has_final_video'] == True
        # Partial status should still include video for download
        assert 'final_video_base64' in result

    def test_get_job_status_error_no_video(self, mock_database):
        """Test that error job doesn't include video."""
        from video_generation import get_video_job_status

        mock_database['get_video_job'].return_value = {
            'id': 1,
            'job_id': 'test-job-123',
            'status': 'error',
            'title': 'Test Video',
            'script': '{}',
            'error_message': 'Generation failed',
            'created_at': 1000000,
            'updated_at': 1000001,
            'final_video': None
        }
        mock_database['get_video_scenes'].return_value = []

        result = get_video_job_status(job_id=1, user_id=1)

        assert result is not None
        assert result['status'] == 'error'
        assert result['error_message'] == 'Generation failed'
        assert result['has_final_video'] == False
        assert 'final_video_base64' not in result

    def test_get_job_status_not_found(self, mock_database):
        """Test that non-existent job returns None."""
        from video_generation import get_video_job_status

        mock_database['get_video_job'].return_value = None

        result = get_video_job_status(job_id=999, user_id=1)

        assert result is None

    def test_get_job_status_wrong_user(self, mock_database):
        """Test that job for different user returns None."""
        from video_generation import get_video_job_status

        # get_video_job should filter by user_id and return None
        mock_database['get_video_job'].return_value = None

        result = get_video_job_status(job_id=1, user_id=999)

        assert result is None
        # Verify user_id was passed to query
        mock_database['get_video_job'].assert_called_with(1, 999)
