import json
import subprocess
from pathlib import Path
from typing import Any

from src.db import DatabaseManager
from src.logger import get_logger


def get_video_metadata(file_path: Path) -> dict[str, Any]:
    """
    Directly queries ffprobe to extract video stream characteristics.
    """
    logger = get_logger()
    path = Path(file_path).resolve()
    
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_format",
        "-show_streams",
        "-of", "json",
        str(path)
    ]
    
    logger.debug(f"Running ffprobe: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10.0)
    
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    format_data = data.get("format", {})
    
    # Locate first video stream
    video_stream = None
    for stream in streams:
        if stream.get("codec_type") == "video":
            video_stream = stream
            break
            
    if not video_stream:
        raise ValueError(f"No video stream found in file: {file_path.name}")
        
    codec = video_stream.get("codec_name", "unknown")
    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)
    
    # Parse Frame Rate (r_frame_rate e.g. "30/1" or "30000/1001")
    fps = 0.0
    r_fps = video_stream.get("r_frame_rate", "0/0")
    if "/" in r_fps:
        try:
            num, den = r_fps.split("/")
            if float(den) > 0:
                fps = float(num) / float(den)
        except (ValueError, ZeroDivisionError):
            fps = 0.0
            
    # Parse Duration
    duration = 0.0
    dur_str = video_stream.get("duration") or format_data.get("duration")
    if dur_str:
        try:
            duration = float(dur_str)
        except ValueError:
            duration = 0.0
            
    # Check Rotation metadata (detecting portrait smartphone video tags)
    rotation = 0
    tags = video_stream.get("tags", {})
    if "rotate" in tags:
        try:
            rotation = int(tags["rotate"])
        except ValueError:
            pass
            
    for side_data in video_stream.get("side_data_list", []):
        if "rotation" in side_data:
            try:
                rotation = int(side_data["rotation"])
            except ValueError:
                pass
                
    # Normalize rotation
    rotation = abs(rotation) % 360

    return {
        "codec": codec,
        "width": width,
        "height": height,
        "fps": round(fps, 3),
        "duration": round(duration, 2),
        "rotation": rotation
    }

def get_metadata_with_cache(
    file_path: Path,
    sha256: str,
    db: DatabaseManager
) -> dict[str, Any]:
    """
    Checks the SQLite database for cached metadata.
    If absent, queries ffprobe and populates the cache.
    """
    logger = get_logger()
    cached = db.get_metadata(sha256)
    if cached:
        logger.info(f"Loaded cached metadata for {file_path.name} from DB")
        return {
            "codec": cached["codec"],
            "width": cached["width"],
            "height": cached["height"],
            "fps": cached["fps"],
            "duration": cached["duration"],
            "rotation": cached["rotation"]
        }
        
    # Analyze and cache
    meta = get_video_metadata(file_path)
    db.cache_metadata(
        sha256=sha256,
        filepath=str(file_path),
        codec=meta["codec"],
        width=meta["width"],
        height=meta["height"],
        fps=meta["fps"],
        duration=meta["duration"],
        rotation=meta["rotation"]
    )
    logger.info(f"Analyzed and cached metadata for {file_path.name}")
    return meta
