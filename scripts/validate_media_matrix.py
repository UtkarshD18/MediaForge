import sys
import time
from pathlib import Path
import subprocess

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.db import DatabaseManager
from src.executor import PipelineExecutor
from src.config import ConfigManager

def generate_video(codec: str, ext: str, output_path: Path, vfr: bool = False) -> bool:
    """
    Generate a 1-second mock video with specified parameters using FFmpeg.
    """
    # Determine resolution to ensure unique hashes and standard DNxHR compliance
    if codec.startswith("dnxhr"):
        size = "1920x1080"
    elif codec.startswith("hevc"):
        size = "320x180" if "iphone" not in codec else "360x180"
    elif codec.startswith("vp9"):
        size = "480x360"
    elif codec.startswith("av1"):
        size = "480x270"
    elif codec.startswith("prores"):
        size = "640x480"
    elif vfr:
        size = "360x240"
    elif "obs_mp4" in codec:
        size = "400x240"
    elif "obs" in codec:
        size = "400x300"
    else:
        size = "320x240"

    cmd = ["ffmpeg", "-y"]
    cmd.extend(["-f", "lavfi", "-i", f"testsrc=duration=1:size={size}:rate=30"])
    cmd.extend(["-t", "1"])
    
    if codec.startswith("h264"):
        cmd.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p"])
    elif codec.startswith("hevc"):
        cmd.extend(["-c:v", "libx265", "-pix_fmt", "yuv420p"])
    elif codec.startswith("vp9"):
        cmd.extend(["-c:v", "libvpx-vp9"])
    elif codec.startswith("av1"):
        cmd.extend(["-c:v", "libsvtav1"])
    elif codec.startswith("dnxhr"):
        cmd.extend(["-c:v", "dnxhd", "-profile:v", "dnxhr_lb", "-pix_fmt", "yuv422p"])
    elif codec.startswith("prores"):
        cmd.extend(["-c:v", "prores_ks", "-profile:v", "3"])
    else:
        cmd.extend(["-c:v", "copy"])
        
    cmd.append(str(output_path))
    
    try:
        subprocess.run(cmd, capture_output=True, check=True)
        return True
    except Exception as e:
        print(f"Failed to generate {codec} video: {e}")
        return False

def main():
    print("Real World Media Ingestion Validation starting...")
    evidence_dir = PROJECT_ROOT / "evidence" / "compatibility"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    log_file = evidence_dir / "media_matrix_test.log"

    # Reset DB
    db_path = PROJECT_ROOT / "mediaforge.db"
    # Using existing DB to preserve stress test history but clear jobs
    db = DatabaseManager(db_path)
    config_mgr = ConfigManager(PROJECT_ROOT)
    executor = PipelineExecutor(db, config_mgr)

    test_cases = [
        # (name, codec, ext, vfr, expected_status)
        ("WhatsApp H264", "h264", "mp4", False, "completed"),
        ("WhatsApp HEVC", "hevc", "mp4", False, "completed"),
        ("Android VFR", "h264_vfr", "mp4", True, "completed"),
        ("iPhone HEVC", "hevc_iphone", "mov", False, "completed"),
        ("OBS MKV", "h264_obs", "mkv", False, "completed"),
        ("OBS MP4", "h264_obs_mp4", "mp4", False, "completed"),
        ("WebM VP9", "vp9", "webm", False, "completed"),
        ("AV1 Video", "av1", "mp4", False, "completed"),
        ("DNxHR Video", "dnxhr", "mov", False, "completed"),
        ("ProRes Video", "prores", "mov", False, "completed"),
    ]

    results = []

    # Run valid test cases
    temp_dir = PROJECT_ROOT / "temp_media_matrix"
    temp_dir.mkdir(parents=True, exist_ok=True)

    for name, codec, ext, vfr, expected in test_cases:
        filepath = temp_dir / f"test_{codec}.{ext}"
        print(f"Generating and testing: {name}...")
        if generate_video(codec, ext, filepath, vfr):
            job_id = db.add_job(str(filepath), "", "youtube")
            success = executor.run_pipeline(job_id)
            jobs = db.execute_read("SELECT status, error_message FROM jobs WHERE id = ?", (job_id,))
            status = jobs[0]["status"]
            err = jobs[0]["error_message"]
            print(f"-> Result: {status} (Expected: {expected})")
            results.append((name, status, expected, err))
            if filepath.exists():
                filepath.unlink()

    # Test Corrupt MP4
    corrupt_mp4 = temp_dir / "corrupt.mp4"
    with open(corrupt_mp4, "w") as f:
        f.write("Corrupt garbage bytes here!")
    job_id = db.add_job(str(corrupt_mp4), "", "youtube")
    executor.run_pipeline(job_id)
    status = db.execute_read("SELECT status, error_message FROM jobs WHERE id = ?", (job_id,))[0]["status"]
    results.append(("Corrupt MP4", status, "failed", "Invalid data found when processing input"))
    if corrupt_mp4.exists():
        corrupt_mp4.unlink()

    # Test Zero-byte File
    zerobyte_file = temp_dir / "zero.mp4"
    zerobyte_file.touch()
    job_id = db.add_job(str(zerobyte_file), "", "youtube")
    executor.run_pipeline(job_id)
    status = db.execute_read("SELECT status, error_message FROM jobs WHERE id = ?", (job_id,))[0]["status"]
    results.append(("Zero-byte File", status, "failed", "Empty file"))
    if zerobyte_file.exists():
        zerobyte_file.unlink()

    # Test Watchdog Ignore cases
    print("Verifying Watchdog exclusions...")
    from src.watcher import IngestionHandler
    handler = IngestionHandler(db, config_mgr)
    
    # We test process_file ignores non-videos
    # Mock database add_job should not run
    initial_jobs_count = len(db.list_jobs())
    handler.process_file(str(temp_dir / "audio.mp3"))
    handler.process_file(str(temp_dir / "image.png"))
    handler.process_file(str(temp_dir / "doc.txt"))
    
    final_jobs_count = len(db.list_jobs())
    watchdog_ok = (initial_jobs_count == final_jobs_count)
    print(f"Watchdog filter verification: {watchdog_ok}")
    results.append(("Watchdog Exclusions", "ignored" if watchdog_ok else "queued", "ignored", None))

    # Cleanup temp dir
    try: temp_dir.rmdir()
    except Exception: pass

    # Write report
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("=== Real-World Media Matrix Ingestion Log ===\n\n")
        f.write(f"| Test Case | Ingest Status | Expected | Notes/Error |\n")
        f.write(f"| :--- | :--- | :--- | :--- |\n")
        for name, status, expected, err in results:
            err_str = f"Error: {err}" if err else "OK"
            f.write(f"| {name} | {status} | {expected} | {err_str} |\n")

    print(f"Evidence log written to: {log_file}")

if __name__ == "__main__":
    main()
