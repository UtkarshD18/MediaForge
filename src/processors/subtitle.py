from pathlib import Path

from src.logger import get_logger


def generate_subtitles(video_path: Path, output_srt_path: Path) -> bool:
    """
    Placeholder/Stub for subtitle transcription tasks.
    """
    logger = get_logger()
    logger.debug("Subtitle post-processor triggered (No-op in V1).")
    return True
