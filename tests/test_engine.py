import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Add project root to python path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import ConfigManager
from src.db import DatabaseManager
from src.events import Events, get_event_bus
from src.processors.converter import ConversionJob, FFmpegBuilder


class TestMediaForge(unittest.TestCase):
    def setUp(self) -> None:
        # Create a temp directory for configurations and DBs
        self.test_dir = Path(tempfile.mkdtemp())
        self.config_dir = self.test_dir / "config"
        self.config_dir.mkdir()
        self.profiles_dir = self.config_dir / "profiles"
        self.profiles_dir.mkdir()

        # Write dummy config
        self.config_file = self.config_dir / "config.yaml"
        with open(self.config_file, "w", encoding="utf-8") as f:
            f.write("""
version: 1
incoming_folder: "~/Videos/Incoming"
originals_folder: "~/Videos/Originals"
resolve_clips_folder: "~/Videos/DaVinci/clips"
active_profile: "youtube"
overwrite_existing: false
notification_toggle: false
logging_level: "INFO"
""")

        # Write dummy profile
        self.profile_file = self.profiles_dir / "youtube.yaml"
        with open(self.profile_file, "w", encoding="utf-8") as f:
            f.write("""
video_codec: "prores"
profile: "3"
audio_codec: "pcm_s16le"
ext: "mov"
""")

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir)

    def test_config_manager(self) -> None:
        """
        Verify that ConfigManager parses paths and profile files correctly.
        """
        cm = ConfigManager(self.test_dir)
        self.assertIsNotNone(cm.config)
        self.assertEqual(cm.config.version, 1)
        self.assertEqual(cm.config.active_profile, "youtube")

        self.assertIn("youtube", cm.profiles)
        prof = cm.get_active_profile()
        self.assertEqual(prof.video_codec, "prores")
        self.assertEqual(prof.profile, "3")

    def test_event_bus(self) -> None:
        """
        Verify event publishing and thread-safe callbacks.
        """
        bus = get_event_bus()
        received_data = []

        def listener(data):
            received_data.append(data)

        bus.subscribe(Events.JOB_ADDED, listener)
        bus.publish(Events.JOB_ADDED, {"job_id": 42})

        self.assertEqual(len(received_data), 1)
        self.assertEqual(received_data[0]["job_id"], 42)

        bus.unsubscribe(Events.JOB_ADDED, listener)
        bus.publish(Events.JOB_ADDED, {"job_id": 99})
        self.assertEqual(len(received_data), 1)  # unchanged

    def test_database_manager(self) -> None:
        """
        Test SQLite creation, queue pushes, metadata caching, and analytics loops.
        """
        db_path = self.test_dir / "test_mediaforge.db"
        db = DatabaseManager(db_path)

        # Test add job
        job_id = db.add_job("/home/shadow/video.mp4", "hash123", "youtube")
        self.assertTrue(job_id > 0)

        next_job = db.get_next_queued_job()
        self.assertIsNotNone(next_job)
        self.assertEqual(next_job["id"], job_id)
        self.assertEqual(next_job["status"], "queued")

        # Test update job status
        db.update_job_status(job_id, "converting")
        active = db.get_active_job()
        self.assertIsNotNone(active)
        self.assertEqual(active["id"], job_id)
        self.assertEqual(active["status"], "converting")

        # Test metadata cache
        db.cache_metadata("hash123", "/home/shadow/video.mp4", "h264", 1920, 1080, 24.0, 10.5)
        meta = db.get_metadata("hash123")
        self.assertIsNotNone(meta)
        self.assertEqual(meta["codec"], "h264")
        self.assertEqual(meta["width"], 1920)

        # Test history & stats
        db.update_job_status(job_id, "completed")
        db.add_history_record(
            job_id=job_id,
            original_name="video.mp4",
            original_path="/home/shadow/video.mp4",
            converted_path="/home/shadow/video.mov",
            sha256="hash123",
            original_size=1000000,
            converted_size=5000000,
            duration=10.5,
            conversion_time=2.5,
            avg_speed=4.2,
            status="completed",
        )

        hist = db.get_history(limit=5)
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["original_name"], "video.mp4")

        analytics = db.get_analytics()
        self.assertEqual(analytics["total_count"], 1)
        self.assertEqual(analytics["total_size_bytes"], 1000000)

    def test_ffmpeg_builder(self) -> None:
        """
        Verify FFmpegBuilder produces standard arguments.
        """
        job = ConversionJob(
            input_path=Path("/tmp/input.mp4"),
            output_path=Path("/tmp/output.mov"),
            video_codec="prores",
            profile="3",
            audio_codec="pcm_s16le",
            duration=10.0,
            hwaccel="cuda",
        )
        cmd = FFmpegBuilder.build(job)

        # Assertions
        self.assertEqual(cmd[0], "ffmpeg")
        self.assertEqual(cmd[1], "-y")
        self.assertEqual(cmd[2], "-hwaccel")
        self.assertEqual(cmd[3], "cuda")
        self.assertIn("-i", cmd)
        self.assertIn("prores_ks", cmd)
        self.assertIn("-profile:v", cmd)
        self.assertIn("pcm_s16le", cmd)


if __name__ == "__main__":
    unittest.main()
