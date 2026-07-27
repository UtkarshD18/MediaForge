import re
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from src.logger import get_logger


@dataclass
class ConversionJob:
    """
    Structured model for a media conversion request.
    """

    input_path: Path
    output_path: Path
    video_codec: str
    profile: str | None = None
    audio_codec: str | None = None
    duration: float = 0.0
    hwaccel: str | None = None


class FFmpegBuilder:
    """
    Compiles list of commands to run FFmpeg with custom profiles and accelerators.
    """

    @staticmethod
    def build(job: ConversionJob) -> list[str]:
        cmd = ["ffmpeg", "-y"]

        # Hardware acceleration must be specified BEFORE the input file
        if job.hwaccel:
            cmd.extend(["-hwaccel", job.hwaccel])

        cmd.extend(["-i", str(job.input_path)])

        # Map video stream and optional audio stream to avoid failures on silent clips
        cmd.extend(["-map", "0:v", "-map", "0:a?"])

        # Compile Video parameters
        if job.video_codec == "prores":
            cmd.extend(["-c:v", "prores_ks"])
            if job.profile is not None:
                cmd.extend(["-profile:v", str(job.profile)])
        elif job.video_codec == "h264":
            cmd.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p"])
        elif job.video_codec == "copy":
            cmd.extend(["-c:v", "copy"])
        else:
            # Fallback to copy if unknown
            cmd.extend(["-c:v", "copy"])

        # Compile Audio parameters
        if job.audio_codec == "pcm_s16le":
            cmd.extend(["-c:a", "pcm_s16le"])
        elif job.audio_codec == "aac":
            cmd.extend(["-c:a", "aac"])
        elif job.audio_codec == "copy":
            cmd.extend(["-c:a", "copy"])
        else:
            cmd.extend(["-c:a", "copy"])

        # Enable stdout reporting for process loop
        cmd.extend(["-progress", "pipe:1", "-nostats"])
        cmd.append(str(job.output_path))
        return cmd


def detect_gpu_support() -> str | None:
    """
    Query ffmpeg to discover supported hardware decoding features.
    Prefers: nvidia (cuda) > intel (qsv) > amd (vaapi) > CPU (None).
    """
    logger = get_logger()
    try:
        result = subprocess.run(["ffmpeg", "-hwaccels"], capture_output=True, text=True, check=True, timeout=5.0)
        output = result.stdout.lower()

        # Check matching drivers in order of speed
        if "cuda" in output:
            logger.info("NVIDIA CUDA hardware decoding detected.")
            return "cuda"
        elif "qsv" in output:
            logger.info("Intel QuickSync hardware decoding detected.")
            return "qsv"
        elif "vaapi" in output:
            logger.info("AMD VAAPI hardware decoding detected.")
            return "vaapi"

        logger.info("No supported GPU acceleration method found. Using CPU decoding.")
        return None
    except Exception as e:
        logger.warning(f"Error checking GPU support via ffmpeg -hwaccels: {e}. Defaulting to CPU.")
        return None


def run_conversion(
    job: ConversionJob, progress_callback: Callable[[float, float, float], None], cancel_event: threading.Event
) -> None:
    """
    Runs FFmpeg, parses its stdout real-time progress flags, handles ETAs,
    and supports immediate cancellation via cancel_event.
    """
    logger = get_logger()
    cmd = FFmpegBuilder.build(job)
    logger.info(f"Compiling FFmpeg execution command: {' '.join(cmd)}")

    # Startup process
    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, universal_newlines=True
    )

    # Track metrics
    current_percent = 0.0
    current_speed = 1.0
    current_eta = 0.0

    # Matcher regexes
    us_pattern = re.compile(r"out_time_us=(\d+)")
    speed_pattern = re.compile(r"speed=\s*([\d\.]+)x")

    # Loop reader thread
    def monitor_cancel():
        while process.poll() is None:
            if cancel_event.is_set():
                logger.warning(f"Conversion job cancelled by user. Terminating FFmpeg pid={process.pid}...")
                process.terminate()
                try:
                    process.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                break
            cancel_event.wait(timeout=0.2)

    cancel_thread = threading.Thread(target=monitor_cancel, daemon=True)
    cancel_thread.start()

    try:
        # Read line by line from progress pipe stdout
        stdout = process.stdout
        if stdout:
            for line in stdout:
                line = line.strip()
                if not line:
                    continue

                # Check microseconds timestamp
                us_match = us_pattern.match(line)
                if us_match and job.duration > 0:
                    us = int(us_match.group(1))
                    sec = us / 1_000_000.0
                    current_percent = min((sec / job.duration) * 100.0, 100.0)

                # Check speed ratio
                speed_match = speed_pattern.match(line)
                if speed_match:
                    try:
                        current_speed = float(speed_match.group(1))
                    except ValueError:
                        current_speed = 1.0

                    # Calculate dynamic ETA
                    if current_percent < 100.0 and current_speed > 0:
                        remaining_seconds = (job.duration - (current_percent * job.duration / 100.0)) / current_speed
                        current_eta = max(remaining_seconds, 0.0)
                    else:
                        current_eta = 0.0

                    progress_callback(current_percent, current_eta, current_speed)

        # Wait for finish
        stdout_data, stderr_data = process.communicate()
        return_code = process.returncode

        if cancel_event.is_set():
            # Clean up partial output file
            if job.output_path.exists():
                try:
                    job.output_path.unlink()
                except Exception as e:
                    logger.error(f"Failed to delete incomplete file {job.output_path}: {e}")
            raise InterruptedError("Job cancelled by user.")

        if return_code != 0:
            err_msg = stderr_data or "FFmpeg exited with non-zero status"
            # Extract main error line
            err_lines = [line for line in err_msg.splitlines() if line.strip()]
            main_err = err_lines[-1] if err_lines else err_msg
            logger.error(f"FFmpeg error output: {err_msg}")
            raise RuntimeError(f"FFmpeg conversion failed: {main_err}")

    except Exception as e:
        # Guarantee cleanup on errors
        if process.poll() is None:
            process.kill()
        raise e
