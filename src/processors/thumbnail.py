import subprocess
from pathlib import Path

from src.logger import get_logger


def generate_thumbnail(video_path: Path, output_jpg_path: Path, seek_seconds: float = 1.0) -> bool:
    """
    Invokes FFmpeg to extract a single high-quality JPEG frame at seek_seconds from a video.
    """
    logger = get_logger()
    cmd = [
        "ffmpeg",
        "-y",
        "-ss", str(seek_seconds),
        "-i", str(video_path),
        "-vframes", "1",
        "-q:v", "4",  # High quality jpeg scale
        str(output_jpg_path)
    ]
    try:
        subprocess.run(cmd, capture_output=True, check=True, timeout=5.0)
        logger.debug(f"Extracted thumbnail poster frame: {output_jpg_path.name}")
        return True
    except Exception as e:
        logger.warning(f"Unable to extract poster frame from {video_path.name}: {e}")
        return False
