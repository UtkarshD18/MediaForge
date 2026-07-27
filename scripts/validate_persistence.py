import sys
import threading
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import ConfigManager
from src.db import DatabaseManager
from src.executor import PipelineExecutor


def main():
    print("Queue Persistence Validation starting...")
    evidence_dir = PROJECT_ROOT / "evidence" / "stress-tests"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    log_file = evidence_dir / "queue_persistence_test.log"

    # Step 1: Wipe DB clean for strict validation
    db_path = PROJECT_ROOT / "mediaforge.db"
    for suffix in ["", "-wal", "-shm"]:
        p = db_path.parent / (db_path.name + suffix)
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass

    db = DatabaseManager(db_path)
    config_mgr = ConfigManager(PROJECT_ROOT)
    executor = PipelineExecutor(db, config_mgr)

    # Re-generate input file in incoming folder just in case it got moved
    incoming_dir = config_mgr.get_resolved_path("incoming_folder")
    input_file = incoming_dir / "persistence_test_src.mp4"

    # Generate 5-second test video in watched incoming folder
    import subprocess

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=5:size=640x360:rate=30",
            "-c:v",
            "libx264",
            "-t",
            "5",
            str(input_file),
        ],
        capture_output=True,
        check=True,
    )

    # Step 2: Add job and start pipeline in background thread
    job_id = db.add_job(str(input_file), "", "youtube")
    print(f"Added job {job_id} to queue.")

    pipeline_thread = threading.Thread(target=executor.run_pipeline, args=(job_id,), daemon=True)
    pipeline_thread.start()

    # Wait for the job to start converting
    time.sleep(1.5)

    # Check status in db
    jobs = db.execute_read("SELECT * FROM jobs WHERE id = ?", (job_id,))
    initial_status = jobs[0]["status"]
    print(f"Mid-transcode job status: {initial_status}")

    # Step 3: Simulate Abrupt Daemon Crash / Kill
    print("Simulating abrupt daemon crash by writing 'converting' to DB and stopping the thread...")
    # Force cancel to stop the active thread
    executor.cancel_active_job()
    pipeline_thread.join()

    # Manually overwrite status to 'converting' in SQLite to simulate crash state
    db.execute_write("UPDATE jobs SET status = 'converting', progress = 45.0 WHERE id = ?", (job_id,))
    jobs_crash = db.execute_read("SELECT * FROM jobs WHERE id = ?", (job_id,))
    print(f"Post-crash database state: status={jobs_crash[0]['status']} | progress={jobs_crash[0]['progress']}%")

    # Step 4: Run Startup recovery
    print("Running startup recovery 'reset_stuck_jobs'...")
    db.reset_stuck_jobs()

    # Verify queue survives restart
    recovered_jobs = db.execute_read("SELECT * FROM jobs WHERE id = ?", (job_id,))
    recovered_status = recovered_jobs[0]["status"]
    recovered_progress = recovered_jobs[0]["progress"]
    print(f"Recovered job status: {recovered_status} | Progress: {recovered_progress}%")

    # Step 5: Resume conversion (should succeed now)
    print("Resuming/re-executing recovered job...")
    success = executor.run_pipeline(job_id)
    print(f"Re-execution outcome: {success}")

    # Verify output exists
    clips_dir = config_mgr.get_resolved_path("resolve_clips_folder")
    output_mov = clips_dir / "persistence_test_src.mov"
    output_exists = output_mov.exists()
    print(f"Output clips file exists: {output_exists}")

    # Clean up output and moved original
    if output_mov.exists():
        output_mov.unlink()

    orig_dir = config_mgr.get_resolved_path("originals_folder")
    orig_file = orig_dir / "persistence_test_src.mp4"
    if orig_file.exists():
        orig_file.unlink()

    # Write evidence log
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("=== Queue Persistence Validation Log ===\n")
        f.write(f"Mid-transcode status: {initial_status}\n")
        f.write("Simulated crash state: status=converting, progress=45.0%\n")
        f.write(f"After crash and recovery status: {recovered_status}\n")
        f.write(f"After crash and recovery progress: {recovered_progress}%\n")
        f.write(f"Re-execution outcome: {success}\n")
        f.write(f"Final output file verified: {output_exists}\n")

    print(f"Evidence log written to: {log_file}")


if __name__ == "__main__":
    main()
