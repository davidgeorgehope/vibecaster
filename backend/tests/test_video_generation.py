"""
Tests for video_generation module.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import json
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestEmitEvent:
    """Tests for emit_event function."""

    def test_creates_valid_json(self):
        """Test that event is valid JSON with timestamp."""
        from video_generation import emit_event

        result = emit_event("test_event", message="Hello")
        parsed = json.loads(result.strip())

        assert parsed['type'] == "test_event"
        assert parsed['message'] == "Hello"
        assert 'timestamp' in parsed
        assert result.endswith('\n')

    def test_includes_all_kwargs(self):
        """Test that all kwargs are included in event."""
        from video_generation import emit_event

        result = emit_event("scene_complete", scene=3, total=5, status="done")
        parsed = json.loads(result.strip())

        assert parsed['scene'] == 3
        assert parsed['total'] == 5
        assert parsed['status'] == "done"


class TestPlanVideoScript:
    """Tests for plan_video_script function."""

    @patch('video_generation.client')
    def test_returns_valid_script_structure(self, mock_client):
        """Test that script planning returns correct structure."""
        from video_generation import plan_video_script

        mock_script = {
            "title": "Understanding Kubernetes",
            "summary": "A quick explainer on container orchestration",
            "scenes": [
                {
                    "scene_number": 1,
                    "narration": "Kubernetes is a container orchestrator",
                    "visual_description": "Animated containers",
                    "image_prompt": "Colorful containers being organized",
                    "video_prompt": "Containers moving and organizing",
                    "include_character": False
                }
            ],
            "total_scenes": 1,
            "estimated_duration": 8
        }

        mock_response = Mock()
        mock_response.text = json.dumps(mock_script)

        mock_client.models.generate_content.return_value = mock_response

        result = plan_video_script(
            topic="Kubernetes basics",
            style="educational",
            target_duration=8
        )

        assert result['title'] == "Understanding Kubernetes"
        assert len(result['scenes']) == 1
        assert result['scenes'][0]['scene_number'] == 1

    @patch('video_generation.client')
    def test_includes_character_context(self, mock_client):
        """Test that author bio is included in prompt."""
        from video_generation import plan_video_script

        mock_response = Mock()
        mock_response.text = json.dumps({
            "title": "Test",
            "summary": "Test",
            "scenes": [],
            "total_scenes": 0,
            "estimated_duration": 0
        })

        mock_client.models.generate_content.return_value = mock_response

        plan_video_script(
            topic="Test topic",
            style="educational",
            target_duration=16,
            author_bio={
                "name": "Dr. Smith",
                "description": "A friendly educator",
                "style": "real_person"
            }
        )

        # Verify prompt includes author info
        call_args = mock_client.models.generate_content.call_args
        prompt = call_args.kwargs['contents']
        assert 'Dr. Smith' in prompt


class TestGenerateSceneImage:
    """Tests for generate_scene_image function."""

    @patch('video_generation.client')
    def test_generates_image_from_prompt(self, mock_client):
        """Test that scene image is generated."""
        from video_generation import generate_scene_image

        mock_part = Mock()
        mock_part.inline_data = Mock()
        mock_part.inline_data.data = b'scene_image_bytes'

        mock_response = Mock()
        mock_response.candidates = [Mock(content=Mock(parts=[mock_part]))]

        mock_client.models.generate_content.return_value = mock_response

        result = generate_scene_image(
            image_prompt="A colorful scene",
            style="cartoon"
        )

        assert result == b'scene_image_bytes'

    @patch('video_generation.client')
    def test_includes_character_reference(self, mock_client):
        """Test that character reference is included when provided."""
        from video_generation import generate_scene_image
        from PIL import Image
        from io import BytesIO

        # Create reference image
        img = Image.new('RGB', (10, 10), color='red')
        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')
        reference = img_bytes.getvalue()

        mock_part = Mock()
        mock_part.inline_data = Mock()
        mock_part.inline_data.data = b'scene_with_character'

        mock_response = Mock()
        mock_response.candidates = [Mock(content=Mock(parts=[mock_part]))]

        mock_client.models.generate_content.return_value = mock_response

        result = generate_scene_image(
            image_prompt="Character in a scene",
            character_reference=reference,
            style="real_person"
        )

        assert result == b'scene_with_character'

        # Verify contents includes reference
        call_args = mock_client.models.generate_content.call_args
        contents = call_args.kwargs['contents']
        assert len(contents) > 1  # Prompt + reference


class TestGenerateVideoFromImage:
    """Tests for generate_video_from_image function."""

    @patch('video_generation.types.Image')
    @patch('video_generation.client')
    @patch('video_generation.time.sleep')
    def test_generates_video_from_first_frame(self, mock_sleep, mock_client, mock_image_type):
        """Test successful video generation from first frame."""
        from video_generation import generate_video_from_image
        from PIL import Image
        from io import BytesIO

        # Create first frame
        img = Image.new('RGB', (100, 100), color='blue')
        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')
        first_frame = img_bytes.getvalue()

        # Create mock video response with proper video data (> 10KB)
        mock_video_bytes = b'x' * 15000  # 15KB - above MIN_VIDEO_SIZE threshold

        # Mock types.Image.from_file to return a mock image
        mock_image_type.from_file.return_value = Mock()

        # Mock the video object
        mock_video = Mock()
        mock_video.video = Mock()

        # Mock operation
        mock_operation = Mock()
        mock_operation.done = True
        mock_operation.response = Mock()
        mock_operation.response.generated_videos = [mock_video]

        mock_client.models.generate_videos.return_value = mock_operation
        mock_client.files.download = Mock()

        # Mock video.save to write our mock bytes
        def mock_save(path):
            with open(path, 'wb') as f:
                f.write(mock_video_bytes)

        mock_video.video.save = mock_save

        result = generate_video_from_image(
            first_frame_bytes=first_frame,
            video_prompt="Test motion prompt"
        )

        assert result is not None
        assert len(result) == len(mock_video_bytes)
        mock_client.models.generate_videos.assert_called_once()

    @patch('video_generation.types.Image')
    @patch('video_generation.client')
    @patch('video_generation.time.sleep')
    def test_polls_until_complete(self, mock_sleep, mock_client, mock_image_type):
        """Test that operation is polled until done."""
        from video_generation import generate_video_from_image
        from PIL import Image
        from io import BytesIO

        # Create first frame
        img = Image.new('RGB', (100, 100), color='green')
        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')
        first_frame = img_bytes.getvalue()

        # Mock types.Image.from_file
        mock_image_type.from_file.return_value = Mock()

        # Mock operation that completes after 2 polls
        poll_count = [0]
        mock_video_bytes = b'v' * 20000

        mock_video = Mock()
        mock_video.video = Mock()

        def mock_save(path):
            with open(path, 'wb') as f:
                f.write(mock_video_bytes)

        mock_video.video.save = mock_save

        mock_operation = Mock()
        mock_operation.done = False
        mock_operation.response = Mock()
        mock_operation.response.generated_videos = [mock_video]

        def get_operation(op):
            poll_count[0] += 1
            if poll_count[0] >= 2:
                op.done = True
            return op

        mock_client.models.generate_videos.return_value = mock_operation
        mock_client.operations.get = get_operation
        mock_client.files.download = Mock()

        result = generate_video_from_image(
            first_frame_bytes=first_frame,
            video_prompt="Motion test"
        )

        assert result is not None
        assert poll_count[0] == 2  # Polled exactly 2 times
        assert mock_sleep.call_count >= 1  # Sleep was called during polling

    @patch('video_generation.types.Image')
    @patch('video_generation.client')
    @patch('video_generation.time.sleep')
    def test_returns_none_on_timeout(self, mock_sleep, mock_client, mock_image_type):
        """Test that None is returned when operation times out.

        Note: This test uses a smaller max_polls value to avoid long test times.
        In production, max_polls=60 gives up to 10 minutes of polling.
        """
        from video_generation import generate_video_from_image
        from PIL import Image
        from io import BytesIO

        # Create first frame
        img = Image.new('RGB', (100, 100), color='red')
        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')
        first_frame = img_bytes.getvalue()

        # Mock types.Image.from_file
        mock_image_type.from_file.return_value = Mock()

        # Mock operation that never completes
        poll_count = [0]

        mock_operation = Mock()
        mock_operation.done = False

        def get_operation(op):
            poll_count[0] += 1
            return op

        mock_client.models.generate_videos.return_value = mock_operation
        mock_client.operations.get = get_operation

        # The function has max_polls=60, so this will run 60 iterations
        # with mocked time.sleep that returns immediately
        result = generate_video_from_image(
            first_frame_bytes=first_frame,
            video_prompt="Timeout test"
        )

        assert result is None
        assert poll_count[0] == 60  # Reached max polls

    @patch('video_generation.types.Image')
    @patch('video_generation.client')
    @patch('video_generation.time.sleep')
    def test_returns_none_when_video_object_missing_data(self, mock_sleep, mock_client, mock_image_type):
        """Test that None is returned when Veo returns video object without video data.

        This is a common production failure mode where the API returns a response
        but the video.video attribute is None.
        """
        from video_generation import generate_video_from_image
        from PIL import Image
        from io import BytesIO

        # Create first frame
        img = Image.new('RGB', (100, 100), color='yellow')
        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')
        first_frame = img_bytes.getvalue()

        # Mock types.Image.from_file
        mock_image_type.from_file.return_value = Mock()

        # Mock video object with video=None (production failure scenario)
        mock_video = Mock()
        mock_video.video = None  # This is the failure mode

        mock_operation = Mock()
        mock_operation.done = True
        mock_operation.response = Mock()
        mock_operation.response.generated_videos = [mock_video]

        mock_client.models.generate_videos.return_value = mock_operation

        result = generate_video_from_image(
            first_frame_bytes=first_frame,
            video_prompt="Missing video data test"
        )

        assert result is None

    @patch('video_generation.types.Image')
    @patch('video_generation.client')
    @patch('video_generation.time.sleep')
    def test_returns_none_when_download_fails(self, mock_sleep, mock_client, mock_image_type):
        """Test that None is returned when video download/save fails.

        This covers the production failure where Veo returns success but
        the actual video file cannot be downloaded or saved.
        """
        from video_generation import generate_video_from_image
        from PIL import Image
        from io import BytesIO

        # Create first frame
        img = Image.new('RGB', (100, 100), color='purple')
        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')
        first_frame = img_bytes.getvalue()

        # Mock types.Image.from_file
        mock_image_type.from_file.return_value = Mock()

        # Mock video that raises exception on save
        mock_video = Mock()
        mock_video.video = Mock()
        mock_video.video.save = Mock(side_effect=Exception("Network error during download"))

        mock_operation = Mock()
        mock_operation.done = True
        mock_operation.response = Mock()
        mock_operation.response.generated_videos = [mock_video]

        mock_client.models.generate_videos.return_value = mock_operation
        mock_client.files.download = Mock()

        result = generate_video_from_image(
            first_frame_bytes=first_frame,
            video_prompt="Download failure test"
        )

        assert result is None

    @patch('video_generation.types.Image')
    @patch('video_generation.client')
    @patch('video_generation.time.sleep')
    def test_returns_none_when_video_too_small(self, mock_sleep, mock_client, mock_image_type):
        """Test that None is returned when video file is too small (< 10KB).

        This covers the production failure where Veo generates a corrupt
        or empty video file that passes initial validation but is unusable.
        """
        from video_generation import generate_video_from_image
        from PIL import Image
        from io import BytesIO

        # Create first frame
        img = Image.new('RGB', (100, 100), color='orange')
        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')
        first_frame = img_bytes.getvalue()

        # Mock types.Image.from_file
        mock_image_type.from_file.return_value = Mock()

        # Mock video that produces a tiny file (< 10KB MIN_VIDEO_SIZE threshold)
        mock_video_bytes = b'tiny'  # Only 4 bytes - way below threshold

        mock_video = Mock()
        mock_video.video = Mock()

        def mock_save(path):
            with open(path, 'wb') as f:
                f.write(mock_video_bytes)

        mock_video.video.save = mock_save

        mock_operation = Mock()
        mock_operation.done = True
        mock_operation.response = Mock()
        mock_operation.response.generated_videos = [mock_video]

        mock_client.models.generate_videos.return_value = mock_operation
        mock_client.files.download = Mock()

        result = generate_video_from_image(
            first_frame_bytes=first_frame,
            video_prompt="Small video test"
        )

        assert result is None

    @patch('video_generation.types.Image')
    @patch('video_generation.client')
    @patch('video_generation.time.sleep')
    def test_returns_none_when_generated_videos_empty(self, mock_sleep, mock_client, mock_image_type):
        """Test that None is returned when generated_videos list is empty.

        This covers the production failure where the API returns success
        but the generated_videos list is empty.
        """
        from video_generation import generate_video_from_image
        from PIL import Image
        from io import BytesIO

        # Create first frame
        img = Image.new('RGB', (100, 100), color='cyan')
        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')
        first_frame = img_bytes.getvalue()

        # Mock types.Image.from_file
        mock_image_type.from_file.return_value = Mock()

        # Mock operation with empty generated_videos list
        mock_operation = Mock()
        mock_operation.done = True
        mock_operation.response = Mock()
        mock_operation.response.generated_videos = []  # Empty list

        mock_client.models.generate_videos.return_value = mock_operation

        result = generate_video_from_image(
            first_frame_bytes=first_frame,
            video_prompt="Empty videos test"
        )

        assert result is None


class TestGenerateVideoStream:
    """Tests for generate_video_stream function."""

    def test_emits_planning_events(self):
        """Test that planning events are emitted."""
        from video_generation import generate_video_stream

        # Patch at the database module level, not video_generation
        with patch('database.get_author_bio') as mock_get_bio, \
             patch('database.create_video_job') as mock_create_job, \
             patch('database.update_video_job') as mock_update_job, \
             patch('video_generation.plan_video_script') as mock_plan:

            mock_get_bio.return_value = None
            mock_create_job.return_value = 1
            mock_plan.return_value = {
                "title": "Test Video",
                "summary": "A test",
                "scenes": [],
                "total_scenes": 0,
                "estimated_duration": 0
            }

            events = list(generate_video_stream(
                user_id=1,
                topic="Test",
                style="educational",
                target_duration=8
            ))

            event_types = [json.loads(e.strip())['type'] for e in events]

            assert 'job_created' in event_types
            assert 'planning' in event_types
            assert 'script_ready' in event_types


class TestGetVideoJobStatus:
    """Tests for get_video_job_status function."""

    def test_returns_job_with_scenes(self):
        """Test that job status includes scenes."""
        from video_generation import get_video_job_status

        # Patch at the database module level
        with patch('database.get_video_job') as mock_get_job, \
             patch('database.get_video_scenes') as mock_get_scenes:

            mock_get_job.return_value = {
                'id': 1,
                'job_id': 'abc123',
                'status': 'generating',
                'title': 'Test Video',
                'created_at': 1234567890,
                'updated_at': 1234567890
            }

            mock_get_scenes.return_value = [
                {'scene_number': 1, 'status': 'complete'},
                {'scene_number': 2, 'status': 'generating_video'}
            ]

            result = get_video_job_status(1, 1)

            assert result['id'] == 1
            assert result['status'] == 'generating'
            assert len(result['scenes']) == 2

    def test_returns_none_for_missing_job(self):
        """Test that None is returned for non-existent job."""
        from video_generation import get_video_job_status

        with patch('database.get_video_job') as mock_get_job:
            mock_get_job.return_value = None

            result = get_video_job_status(999, 1)

            assert result is None


# ===== LIVE API INTEGRATION TESTS =====
# These tests call the actual Veo API and are marked with pytest.mark.integration
# Run with: pytest -m integration tests/test_video_generation.py -v
# These tests cost API credits and may take 1-5 minutes to complete

@pytest.mark.integration
class TestVeoApiIntegration:
    """
    Integration tests that call the live Veo API.

    These tests are designed to catch production failures like:
    - API returning video object without video data
    - Video files being too small/corrupt
    - Timeout issues
    - Download failures

    Skip these in CI by not passing -m integration.
    """

    def test_live_video_generation_success(self):
        """
        End-to-end test: Generate actual video from image using Veo API.

        This test exercises the full production path and validates:
        1. Image is created from first frame bytes
        2. Video is generated from the image
        3. Video file is downloaded and has valid size

        Expected runtime: 30-120 seconds
        """
        from video_generation import generate_video_from_image
        from PIL import Image
        from io import BytesIO
        import os

        # Skip if no API key
        if not os.getenv("GEMINI_API_KEY"):
            pytest.skip("GEMINI_API_KEY not set")

        # Create a simple test image (solid color to minimize API complexity)
        img = Image.new('RGB', (512, 512), color=(100, 150, 200))
        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')
        first_frame = img_bytes.getvalue()

        # Call the actual API
        result = generate_video_from_image(
            first_frame_bytes=first_frame,
            video_prompt="Subtle camera zoom, gentle motion, professional quality"
        )

        # Validate result
        assert result is not None, "Veo API returned None - check logs for failure reason"
        assert len(result) > 10000, f"Video too small ({len(result)} bytes), likely corrupt"

        # Basic MP4 header validation
        # MP4 files start with 'ftyp' atom (within first 12 bytes)
        assert b'ftyp' in result[:32], "Video doesn't appear to be valid MP4"

    def test_live_video_with_complex_prompt(self):
        """
        Test video generation with a more complex motion prompt.

        This tests whether complex prompts cause failures.
        """
        from video_generation import generate_video_from_image
        from PIL import Image
        from io import BytesIO
        import os

        if not os.getenv("GEMINI_API_KEY"):
            pytest.skip("GEMINI_API_KEY not set")

        # Create test image with some variation (gradient)
        img = Image.new('RGB', (512, 512))
        for x in range(512):
            for y in range(512):
                img.putpixel((x, y), (x // 2, y // 2, 128))

        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')
        first_frame = img_bytes.getvalue()

        result = generate_video_from_image(
            first_frame_bytes=first_frame,
            video_prompt="Cinematic slow motion, smooth camera pan from left to right, "
                        "professional lighting, subtle depth of field effect"
        )

        assert result is not None, "Complex prompt caused generation failure"
        assert len(result) > 10000, f"Video too small ({len(result)} bytes)"

    # NOTE: reference_images test removed - Veo API doesn't support
    # reference_images with image-to-video mode (they're mutually exclusive)


@pytest.mark.integration
class TestGenerateSceneImageIntegration:
    """Live API tests for scene image generation."""

    def test_live_image_generation(self):
        """Test actual image generation from prompt."""
        from video_generation import generate_scene_image
        import os

        if not os.getenv("GEMINI_API_KEY"):
            pytest.skip("GEMINI_API_KEY not set")

        result = generate_scene_image(
            image_prompt="A simple abstract background with geometric shapes",
            style="cartoon"
        )

        assert result is not None, "Image generation returned None"
        assert len(result) > 1000, f"Image too small ({len(result)} bytes)"

        # Basic PNG validation
        assert result[:8] == b'\x89PNG\r\n\x1a\n', "Not a valid PNG"


@pytest.mark.integration
class TestFullVideoStreamIntegration:
    """End-to-end test of the full video generation stream."""

    def test_live_single_scene_video_stream(self):
        """
        Full integration test: Generate a complete single-scene video.

        This tests the entire pipeline:
        1. Script planning
        2. Scene image generation
        3. Video generation from image
        4. (No stitching needed for single scene)

        Expected runtime: 2-5 minutes
        """
        from video_generation import generate_video_stream, emit_event
        from database import get_db
        import os
        import json

        if not os.getenv("GEMINI_API_KEY"):
            pytest.skip("GEMINI_API_KEY not set")

        # Create test user for the video job
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO users (id, email, hashed_password, created_at)
                VALUES (99999, 'video_integration_test@test.com', 'hashed', 1234567890)
            """)
            conn.commit()

        try:
            events = []
            for event in generate_video_stream(
                user_id=99999,
                topic="Simple test topic",
                style="educational",
                target_duration=8  # Single 8-second scene
            ):
                parsed = json.loads(event.strip())
                events.append(parsed)
                print(f"Event: {parsed['type']}")  # Show progress

            # Verify key events occurred
            event_types = [e['type'] for e in events]

            assert 'job_created' in event_types, "Job was not created"
            assert 'planning' in event_types, "Planning did not start"
            assert 'script_ready' in event_types, "Script was not generated"

            # Check if we got a complete or error status
            if 'complete' in event_types:
                complete_event = next(e for e in events if e['type'] == 'complete')
                assert 'video_base64' in complete_event, "Complete event missing video data"
            elif 'error' in event_types:
                error_event = next(e for e in events if e['type'] == 'error')
                pytest.fail(f"Video generation failed: {error_event.get('message', 'Unknown error')}")
            else:
                pytest.fail(f"Neither complete nor error event found. Events: {event_types}")

        finally:
            # Cleanup test data
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM video_scenes WHERE job_id IN (SELECT id FROM video_jobs WHERE user_id = 99999)")
                cursor.execute("DELETE FROM video_jobs WHERE user_id = 99999")
                cursor.execute("DELETE FROM users WHERE id = 99999")
                conn.commit()
