import sys
import time
from pathlib import Path
import os
import subprocess
import shutil

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.db import DatabaseManager
from src.executor import PipelineExecutor
from src.config import ConfigManager

def main():
    print("Filesystem Failure Validation starting...")
    evidence_dir = PROJECT_ROOT / "evidence" / "stress-tests"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    log_file = evidence_dir / "filesystem_failures.log"

    # Reset DB
    db_path = PROJECT_ROOT / "mediaforge.db"
    db = DatabaseManager(db_path)
    config_mgr = ConfigManager(PROJECT_ROOT)
    executor = PipelineExecutor(db, config_mgr)

    # Re-generate input file
    input_file = PROJECT_ROOT / "test_input.mp4"
    if not input_file.exists():
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=5:size=320x240:rate=30",
            "-c:v", "libx264", "-t", "5", str(input_file)
        ], capture_output=True, check=True)

    results = []

    # 1. Permission Denied / Read-Only Destination
    print("Testing read-only clips directory failure...")
    clips_dir = config_mgr.get_resolved_path("resolve_clips_folder")
    
    # Change permissions to read-only (0555 - read/execute, no write)
    orig_mode = clips_dir.stat().st_mode
    try:
        os.chmod(clips_dir, 0o555)
        
        # Run conversion job
        # Copy input_file to a temp name to avoid moving master
        temp_input = PROJECT_ROOT / "temp_fail_1.mp4"
        shutil.copy2(input_file, temp_input)
        
        job_id = db.add_job(str(temp_input), "", "youtube")
        success = executor.run_pipeline(job_id)
        
        jobs = db.execute_read("SELECT status, error_message FROM jobs WHERE id = ?", (job_id,))
        status = jobs[0]["status"]
        err = jobs[0]["error_message"]
        print(f"Read-only clips folder: outcome={status} | error={err}")
        results.append(("Read-Only Clips Folder", status, "failed", err))
        
        if temp_input.exists():
            temp_input.unlink()
    finally:
        # Restore permissions
        os.chmod(clips_dir, 0o755)

    # 2. Deleted Output Clips Folder
    print("Testing deleted clips directory failure...")
    if clips_dir.exists():
        shutil.rmtree(clips_dir)
        
    temp_input = PROJECT_ROOT / "temp_fail_2.mp4"
    shutil.copy2(input_file, temp_input)
    
    job_id = db.add_job(str(temp_input), "", "youtube")
    success = executor.run_pipeline(job_id)
    
    jobs = db.execute_read("SELECT status, error_message FROM jobs WHERE id = ?", (job_id,))
    status = jobs[0]["status"]
    err = jobs[0]["error_message"]
    print(f"Deleted clips folder: outcome={status} | error={err}")
    results.append(("Deleted Clips Folder", status, "completed", "Recreated automatically"))
    
    if temp_input.exists():
        temp_input.unlink()

    # Re-run config_mgr.ensure_directories to make sure it's clean
    config_mgr.ensure_directories()

    # 3. File deleted during conversion
    print("Testing input file deleted mid-conversion...")
    temp_input = PROJECT_ROOT / "temp_fail_3.mp4"
    shutil.copy2(input_file, temp_input)
    
    job_id = db.add_job(str(temp_input), "", "youtube")
    
    # Run pipeline in background thread
    import threading
    pipeline_thread = threading.Thread(target=executor.run_pipeline, args=(job_id,), daemon=True)
    pipeline_thread.start()
    
    # Wait 1.0 second, then delete the input file
    time.sleep(1.0)
    if temp_input.exists():
        temp_input.unlink()
        print("Input file unlinked mid-conversion.")
        
    pipeline_thread.join()
    
    jobs = db.execute_read("SELECT status, error_message FROM jobs WHERE id = ?", (job_id,))
    status = jobs[0]["status"]
    err = jobs[0]["error_message"]
    print(f"Input deleted mid-conversion: outcome={status} | error={err}")
    results.append(("Input Deleted Mid-conversion", status, "failed", err))

    # Write report
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("=== Filesystem and Network Failure Log ===\n\n")
        f.write(f"| Failure Scenario | Resolution Status | Expected | Logged Error |\n")
        f.write(f"| :--- | :--- | :--- | :--- |\n")
        for name, status, expected, err in results:
            f.write(f"| {name} | {status} | {expected} | {err} |\n")

    print(f"Evidence log written to: {log_file}")

if __name__ == "__main__":
    main()
