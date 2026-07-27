import hashlib
import os
import time
from pathlib import Path

from src.logger import get_logger


def wait_for_file_copy(
    file_path: Path,
    check_interval: float = 0.5,
    stability_duration: float = 2.0
) -> bool:
    """
    Polls a file's size and modification timestamp.
    Blocks until the values stop changing, indicating that the copy is complete.
    """
    logger = get_logger()
    path = Path(file_path)
    if not path.exists():
        return False
        
    last_size = -1
    last_mtime = -1.0
    stable_since = None
    
    logger.info(f"Checking transfer status for: {path.name}...")
    
    while True:
        try:
            if not path.exists():
                logger.warning(f"File vanished during copy monitoring: {path.name}")
                return False
                
            stat = path.stat()
            current_size = stat.st_size
            current_mtime = stat.st_mtime
            
            # Check if sizes match
            if current_size == last_size and current_mtime == last_mtime:
                if stable_since is None:
                    stable_since = time.time()
                elif time.time() - stable_since >= stability_duration:
                    logger.info(f"File transfer finalized for {path.name} (Size: {current_size} bytes)")
                    return True
            else:
                # Reset stability window
                stable_since = None
                last_size = current_size
                last_mtime = current_mtime
                
            time.sleep(check_interval)
        except Exception as e:
            logger.error(f"Error checking copy state for {file_path}: {e}")
            time.sleep(check_interval)

def get_file_sha256(file_path: Path) -> str:
    """
    Computes SHA256 checksum of a file in 64KB chunks to prevent high memory usage.
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            sha256.update(chunk)
    return sha256.hexdigest()

def preserve_timestamps(source_path: Path, target_path: Path) -> None:
    """
    Clones file creation/modification timestamps from source_path to target_path.
    """
    logger = get_logger()
    try:
        src_stat = source_path.stat()
        os.utime(target_path, (src_stat.st_atime, src_stat.st_mtime))
        logger.debug(f"Preserved modification timestamps from {source_path.name} to {target_path.name}")
    except Exception as e:
        logger.warning(f"Unable to clone timestamps from {source_path.name}: {e}")
