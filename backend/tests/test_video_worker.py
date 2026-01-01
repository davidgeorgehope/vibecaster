"""
Tests for video_worker module - background video generation.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import json
import sys
import os
import time
import threading

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestVideoWorkerStartJob:
    """Tests for start_video_job function."""

    def test_starts_job_successfully(self):
        """Test that start_video_job returns True and starts thread."""
        from video_worker import start_video_job, is_job_running, _active_jobs, _lock

        # Clean up any existing jobs
        with _lock:
            _active_jobs.clear()

        # Mock the entire _run_video_job to do nothing
        with patch('video_worker._run_video_job'):
            result = start_video_job(
                job_id=999,
                user_id=1,
                topic="Test topic",
                style="educational",
                target_duration=30,
                user_prompt=""
            )

            assert result is True
            # Give thread time to start
            time.sleep(0.1)

        # Clean up
        with _lock:
            _active_jobs.pop(999, None)

    def test_rejects_duplicate_job(self):
        """Test that start_video_job returns False for already running job."""
        from video_worker import start_video_job, _active_jobs, _lock

        # Set up a fake running job
        with _lock:
            _active_jobs[888] = threading.Thread()

        try:
            result = start_video_job(
                job_id=888,
                user_id=1,
                topic="Test topic",
                style="educational",
                target_duration=30,
                user_prompt=""
            )

            assert result is False
        finally:
            # Clean up
            with _lock:
                _active_jobs.pop(888, None)


class TestVideoWorkerIsJobRunning:
    """Tests for is_job_running function."""

    def test_returns_true_for_active_job(self):
        """Test that is_job_running returns True for active job."""
        from video_worker import is_job_running, _active_jobs, _lock

        with _lock:
            _active_jobs[777] = threading.Thread()

        try:
            assert is_job_running(777) is True
        finally:
            with _lock:
                _active_jobs.pop(777, None)

    def test_returns_false_for_inactive_job(self):
        """Test that is_job_running returns False for non-existent job."""
        from video_worker import is_job_running

        assert is_job_running(99999) is False


class TestVideoWorkerGetRunningJobs:
    """Tests for get_running_jobs function."""

    def test_returns_list_of_job_ids(self):
        """Test that get_running_jobs returns list of active job IDs."""
        from video_worker import get_running_jobs, _active_jobs, _lock

        with _lock:
            _active_jobs.clear()
            _active_jobs[111] = threading.Thread()
            _active_jobs[222] = threading.Thread()

        try:
            result = get_running_jobs()
            assert set(result) == {111, 222}
        finally:
            with _lock:
                _active_jobs.clear()

    def test_returns_empty_list_when_no_jobs(self):
        """Test that get_running_jobs returns empty list when no jobs."""
        from video_worker import get_running_jobs, _active_jobs, _lock

        with _lock:
            _active_jobs.clear()

        result = get_running_jobs()
        assert result == []


class TestDatabaseJobEvents:
    """Tests for video_job_events database functions."""

    @pytest.fixture
    def test_db(self, tmp_path):
        """Create a temporary test database."""
        import sqlite3
        db_path = tmp_path / "test.db"

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Create required tables
        cursor.execute("""
            CREATE TABLE video_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                job_id TEXT UNIQUE,
                status TEXT DEFAULT 'pending',
                title TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE video_job_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                event_json TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (job_id) REFERENCES video_jobs(id) ON DELETE CASCADE
            )
        """)

        # Create a test job
        cursor.execute("""
            INSERT INTO video_jobs (user_id, status, title, created_at, updated_at)
            VALUES (1, 'generating', 'Test Job', ?, ?)
        """, (int(time.time()), int(time.time())))

        conn.commit()
        conn.close()

        return db_path

    def test_save_job_event(self, test_db):
        """Test that save_job_event inserts event into database."""
        with patch('database.DB_PATH', str(test_db)):
            from database import save_job_event

            event_json = json.dumps({"type": "test", "message": "hello"})
            event_id = save_job_event(job_id=1, event_json=event_json)

            assert event_id is not None
            assert event_id > 0

    def test_get_job_events_since(self, test_db):
        """Test that get_job_events_since retrieves events after given ID."""
        with patch('database.DB_PATH', str(test_db)):
            from database import save_job_event, get_job_events_since

            # Save multiple events
            event1 = json.dumps({"type": "event1"})
            event2 = json.dumps({"type": "event2"})
            event3 = json.dumps({"type": "event3"})

            id1 = save_job_event(job_id=1, event_json=event1)
            id2 = save_job_event(job_id=1, event_json=event2)
            id3 = save_job_event(job_id=1, event_json=event3)

            # Get events after first one
            events = get_job_events_since(job_id=1, last_event_id=id1)

            assert len(events) == 2
            assert events[0][0] == id2
            assert events[1][0] == id3

    def test_get_job_events_since_returns_empty_when_none(self, test_db):
        """Test that get_job_events_since returns empty list when no events."""
        with patch('database.DB_PATH', str(test_db)):
            from database import get_job_events_since

            events = get_job_events_since(job_id=1, last_event_id=0)
            assert events == []

    def test_cleanup_job_events(self, test_db):
        """Test that cleanup_job_events deletes events for a job."""
        with patch('database.DB_PATH', str(test_db)):
            from database import save_job_event, get_job_events_since, cleanup_job_events

            # Save some events
            save_job_event(job_id=1, event_json='{"type": "test1"}')
            save_job_event(job_id=1, event_json='{"type": "test2"}')

            # Verify they exist
            events = get_job_events_since(job_id=1, last_event_id=0)
            assert len(events) == 2

            # Clean them up
            deleted = cleanup_job_events(job_id=1)
            assert deleted == 2

            # Verify they're gone
            events = get_job_events_since(job_id=1, last_event_id=0)
            assert len(events) == 0

    def test_cleanup_old_job_events(self, test_db):
        """Test that cleanup_old_job_events deletes old events."""
        import sqlite3

        with patch('database.DB_PATH', str(test_db)):
            from database import cleanup_old_job_events

            # Insert an old event directly
            old_time = int(time.time()) - (25 * 3600)  # 25 hours ago
            conn = sqlite3.connect(str(test_db))
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO video_job_events (job_id, event_json, created_at)
                VALUES (1, '{"type": "old"}', ?)
            """, (old_time,))
            conn.commit()
            conn.close()

            # Clean up events older than 24 hours
            deleted = cleanup_old_job_events(hours=24)
            assert deleted == 1


class TestVideoStreamWithJobId:
    """Tests for generate_video_stream with job_id parameter."""

    @patch('database.get_author_bio')
    @patch('database.create_video_job')
    @patch('database.update_video_job')
    @patch('database.create_video_scene')
    @patch('database.update_video_scene')
    @patch('video_generation.plan_video_script')
    @patch('video_generation.generate_scene_image')
    @patch('video_generation.generate_video_from_image_stream')
    @patch('video_generation.stitch_videos')
    def test_skips_job_creation_when_job_id_provided(
        self,
        mock_stitch,
        mock_video_stream,
        mock_image,
        mock_plan,
        mock_update_scene,
        mock_create_scene,
        mock_update_job,
        mock_create_job,
        mock_author_bio
    ):
        """Test that generate_video_stream skips job creation when job_id is provided."""
        from video_generation import generate_video_stream

        # Setup mocks
        mock_author_bio.return_value = None
        mock_plan.return_value = {
            "title": "Test",
            "scenes": [{"scene_number": 1, "narration": "test", "video_prompt": "test"}],
            "summary": "test"
        }
        mock_create_scene.return_value = 1
        mock_image.return_value = b"fake_image"
        mock_video_stream.return_value = iter([("complete", b"fake_video")])
        mock_stitch.return_value = b"final_video"

        # Run with job_id provided
        events = list(generate_video_stream(
            user_id=1,
            topic="Test",
            job_id=123  # Pre-created job ID
        ))

        # Should NOT have called create_video_job
        mock_create_job.assert_not_called()

        # Should NOT have emitted job_created event
        event_types = [json.loads(e.strip())['type'] for e in events]
        assert 'job_created' not in event_types

    @patch('database.get_author_bio')
    @patch('database.create_video_job')
    @patch('database.update_video_job')
    @patch('video_generation.plan_video_script')
    def test_creates_job_when_no_job_id_provided(
        self,
        mock_plan,
        mock_update_job,
        mock_create_job,
        mock_author_bio
    ):
        """Test that generate_video_stream creates job when no job_id provided."""
        from video_generation import generate_video_stream

        # Setup mocks
        mock_author_bio.return_value = None
        mock_create_job.return_value = 456
        mock_plan.side_effect = Exception("Stop early")  # Stop after job creation

        # Run without job_id
        events = []
        try:
            for e in generate_video_stream(user_id=1, topic="Test"):
                events.append(e)
        except Exception:
            pass

        # Should have called create_video_job
        mock_create_job.assert_called_once()

        # Should have emitted job_created event
        if events:
            first_event = json.loads(events[0].strip())
            assert first_event['type'] == 'job_created'
            assert first_event['job_id'] == 456
