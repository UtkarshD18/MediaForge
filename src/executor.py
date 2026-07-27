import shutil
import threading
import time
from pathlib import Path

from src.config import ConfigManager
from src.db import DatabaseManager
from src.events import Events, get_event_bus
from src.logger import get_logger
from src.metadata import get_metadata_with_cache
from src.processors.converter import ConversionJob, detect_gpu_support, run_conversion
from src.utils import get_file_sha256, preserve_timestamps, wait_for_file_copy


class PipelineExecutor:
    """
    Executes a single media ingestion job through the multi-stage processing pipeline.
    """

    def __init__(self, db: DatabaseManager, config_mgr: ConfigManager) -> None:
        self.db = db
        self.config_mgr = config_mgr
        self.logger = get_logger()
        self.bus = get_event_bus()
        self.cancel_event = threading.Event()
        self._current_job_id: int | None = None
        self._current_process_start: float = 0.0

    def cancel_active_job(self) -> None:
        """
        Interrupts the active job by setting the cancel event.
        """
        self.cancel_event.set()

    def run_pipeline(self, job_id: int) -> bool:
        """
        Starts sequential multi-stage execution of a job.
        Returns True if successful, False if failed.
        """
        self._current_job_id = job_id
        self._current_process_start = time.time()
        self.cancel_event.clear()

        # Load job details
        jobs = self.db.execute_read("SELECT * FROM jobs WHERE id = ?", (job_id,))
        if not jobs:
            self.logger.error(f"Job ID {job_id} not found in database.")
            return False

        job_row = jobs[0]
        filepath = Path(job_row["filepath"])
        profile_name = job_row["profile_name"]

        try:
            # 1. Analyze / Wait for transfer
            self.logger.info(f"Starting pipeline for job {job_id}: {filepath.name}")
            self.db.update_job_status(job_id, "analyzing")

            # Wait for file copy to stabilize
            stability = self.config_mgr.config.stability_duration if self.config_mgr.config else 2.0
            if not wait_for_file_copy(filepath, stability_duration=stability):
                raise FileNotFoundError(f"Source file {filepath} was not copied completely or was removed.")

            if self.cancel_event.is_set():
                raise InterruptedError("Cancelled during transfer monitoring.")

            # Compute SHA256
            sha256 = get_file_sha256(filepath)

            # Update hash in jobs table
            self.db.execute_write("UPDATE jobs SET sha256 = ? WHERE id = ?", (sha256, job_id))

            # Query metadata
            meta = get_metadata_with_cache(filepath, sha256, self.db)
            duration = meta["duration"]
            codec = meta["codec"]

            # Publish event
            self.bus.publish(
                Events.JOB_STARTED,
                {"job_id": job_id, "filepath": str(filepath), "profile_name": profile_name, "metadata": meta},
            )

            # 2. Check Duplicate Detection
            history_match = self.db.execute_read(
                "SELECT * FROM history WHERE sha256 = ? AND status IN ('completed', 'duplicate') ORDER BY id DESC LIMIT 1",
                (sha256,),
            )
            if history_match:
                prev_path = Path(history_match[0]["converted_path"])
                if prev_path.exists():
                    self.logger.info(
                        f"Duplicate detected: {filepath.name} matches completed ingestion {prev_path.name}. Skipping conversion."
                    )

                    # Still clean up incoming directory
                    self.db.update_job_status(job_id, "moving")
                    originals_dir = self.config_mgr.get_resolved_path("originals_folder")
                    moved_original = self._move_file_with_collision(filepath, originals_dir)

                    # Update jobs & history
                    self.db.update_job_status(job_id, "duplicate", reason="sha256_match")
                    self.db.add_history_record(
                        job_id=job_id,
                        original_name=filepath.name,
                        original_path=str(moved_original),
                        converted_path=str(prev_path),
                        sha256=sha256,
                        original_size=moved_original.stat().st_size,
                        converted_size=prev_path.stat().st_size,
                        duration=duration,
                        conversion_time=0.0,
                        avg_speed=0.0,
                        status="duplicate",
                        reason="sha256_match",
                    )
                    self.bus.publish(
                        Events.JOB_FINISHED,
                        {"job_id": job_id, "original_name": filepath.name, "converted_path": str(prev_path)},
                    )
                    return True

            # 3. Determine action based on profile
            profile = self.config_mgr.profiles.get(profile_name)
            if not profile:
                raise ValueError(f"Ingestion profile '{profile_name}' is not defined.")

            # Directories
            clips_dir = self.config_mgr.get_resolved_path("resolve_clips_folder")
            originals_dir = self.config_mgr.get_resolved_path("originals_folder")
            clips_dir.mkdir(parents=True, exist_ok=True)
            originals_dir.mkdir(parents=True, exist_ok=True)

            # Check if codec is already edit-ready
            is_edit_ready = codec.lower() in ("prores", "dnxhr", "dnxhd")

            # Destination path naming
            target_ext = profile.ext
            dest_filename = f"{filepath.stem}.{target_ext}"
            temp_dest_file = clips_dir / f"{filepath.stem}._tmp.{target_ext}"
            final_dest_file = clips_dir / dest_filename

            if is_edit_ready or profile.video_codec == "copy":
                self.logger.info(
                    f"Skipping compression re-encode for {filepath.name} (Codec: {codec}). Remuxing/copying to clips folder."
                )
                self.db.update_job_status(job_id, "converting")

                # Check if we can do a simple direct copy (if extensions match) or need ffmpeg remux
                if filepath.suffix.lower() == f".{target_ext}".lower():
                    # Direct filesystem copy
                    self.logger.debug(f"Direct copying {filepath.name} to temp path {temp_dest_file.name}")
                    shutil.copy2(filepath, temp_dest_file)
                else:
                    # Remux container via ffmpeg without re-encoding
                    remux_job = ConversionJob(
                        input_path=filepath,
                        output_path=temp_dest_file,
                        video_codec="copy",
                        audio_codec="copy",
                        duration=duration,
                        hwaccel=None,
                    )
                    run_conversion(
                        remux_job, lambda p, e, s: self.db.update_job_progress(job_id, p, e), self.cancel_event
                    )
            else:
                # Run full conversion with hardware acceleration detection
                self.db.update_job_status(job_id, "converting")
                gpu = detect_gpu_support()

                conv_job = ConversionJob(
                    input_path=filepath,
                    output_path=temp_dest_file,
                    video_codec=profile.video_codec,
                    profile=profile.profile,
                    audio_codec=profile.audio_codec,
                    duration=duration,
                    hwaccel=gpu,
                )

                try:
                    # Define update progress callback
                    def on_progress(percent: float, eta: float, speed: float) -> None:
                        self.db.update_job_progress(job_id, percent, eta)
                        self.bus.publish(
                            Events.JOB_PROGRESS,
                            {
                                "job_id": job_id,
                                "filename": filepath.name,
                                "progress": percent,
                                "eta": eta,
                                "speed": speed,
                            },
                        )

                    run_conversion(conv_job, on_progress, self.cancel_event)
                except Exception as e:
                    if gpu:
                        self.logger.warning(
                            f"GPU conversion failed for {filepath.name} with error: {e}. Falling back to CPU decoding..."
                        )
                        if temp_dest_file.exists():
                            temp_dest_file.unlink()

                        conv_job.hwaccel = None
                        run_conversion(conv_job, on_progress, self.cancel_event)
                    else:
                        raise e

            # 5. Move output & original
            self.db.update_job_status(job_id, "moving")

            # Resolve collision for final destination
            final_dest_file = self._resolve_collision(final_dest_file)

            # Move temp converted to final
            shutil.move(temp_dest_file, final_dest_file)

            # Preserve modification times
            preserve_timestamps(filepath, final_dest_file)

            # Move original to Originals folder
            moved_original = self._move_file_with_collision(filepath, originals_dir)

            # 4. Post-processing (using final file name)
            if self.cancel_event.is_set():
                raise InterruptedError("Cancelled prior to post-processing.")

            self.db.update_job_status(job_id, "post_processing")
            self._run_post_processors(final_dest_file, duration)

            # 6. Complete Ingestion Record
            self.db.update_job_status(job_id, "completed")

            duration_time = time.time() - self._current_process_start
            avg_speed_val = (duration / duration_time) if duration_time > 0 else 1.0

            self.db.add_history_record(
                job_id=job_id,
                original_name=filepath.name,
                original_path=str(moved_original),
                converted_path=str(final_dest_file),
                sha256=sha256,
                original_size=moved_original.stat().st_size,
                converted_size=final_dest_file.stat().st_size,
                duration=duration,
                conversion_time=duration_time,
                avg_speed=round(avg_speed_val, 2),
                status="completed",
            )

            self.bus.publish(
                Events.JOB_FINISHED,
                {"job_id": job_id, "original_name": filepath.name, "converted_path": str(final_dest_file)},
            )

            return True

        except Exception as e:
            self.logger.error(f"Pipeline execution failed for job {job_id}: {e}")
            self.db.update_job_status(job_id, "failed", str(e))

            # Attempt to clean up temp file if present
            try:
                temp_ext = profile.ext if ("profile" in locals() and profile is not None) else "mov"
                temp_path = (
                    Path(self.config_mgr.get_resolved_path("resolve_clips_folder")) / f"{filepath.stem}._tmp.{temp_ext}"
                )
                if temp_path.exists():
                    temp_path.unlink()
            except Exception as cleanup_err:
                self.logger.error(f"Failed to clean up temp converted file: {cleanup_err}")

            self.bus.publish(Events.JOB_FAILED, {"job_id": job_id, "original_name": filepath.name, "error": str(e)})
            return False

        finally:
            self._current_job_id = None

    def _run_post_processors(self, converted_file: Path, duration: float = 0.0) -> None:
        """
        Runs post-processing steps like thumbnail generators.
        """
        # Call processor/thumbnail generator safely
        if self.config_mgr.config and not self.config_mgr.config.features.get("thumbnails", True):
            self.logger.debug("Thumbnail post-processing feature disabled by configuration.")
            return

        try:
            from src.processors.thumbnail import generate_thumbnail

            cache_dir = Path(self.config_mgr.get_resolved_path("resolve_clips_folder")).parent / "cache"
            if cache_dir.exists():
                thumb_path = cache_dir / f"{converted_file.stem}.jpg"
                seek_time = min(1.0, duration / 2.0) if duration > 0 else 0.0
                generate_thumbnail(converted_file, thumb_path, seek_seconds=seek_time)
        except Exception as e:
            self.logger.warning(f"Post-processing thumbnail generation skipped: {e}")

    def _resolve_collision(self, target_path: Path) -> Path:
        """
        Appends suffix increment (e.g. file_1.mov) if target_path file exists.
        """
        if not target_path.exists():
            return target_path

        parent = target_path.parent
        stem = target_path.stem
        suffix = target_path.suffix
        counter = 1

        while True:
            new_path = parent / f"{stem}_{counter}{suffix}"
            if not new_path.exists():
                return new_path
            counter += 1

    def _move_file_with_collision(self, source_path: Path, dest_dir: Path) -> Path:
        """
        Moves source_path file into dest_dir, handling collisions.
        Returns final destination Path.
        """
        target_dest = dest_dir / source_path.name
        target_dest = self._resolve_collision(target_dest)
        shutil.move(source_path, target_dest)
        return target_dest
