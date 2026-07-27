import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import ConfigManager
from src.db import DatabaseManager
from src.executor import PipelineExecutor


def main():
    print("Duplicate Detection Validation starting...")
    evidence_dir = PROJECT_ROOT / "evidence" / "sqlite"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    log_file = evidence_dir / "duplicate_test_history.log"

    # Step 1: Initialize components
    db_path = PROJECT_ROOT / "mediaforge.db"
    # Ensure starting clean
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

    # Step 2: Queue and process the original file
    input_master = PROJECT_ROOT / "test_input.mp4"
    temp_file1 = PROJECT_ROOT / "temp_input_1.mp4"
    temp_file2 = PROJECT_ROOT / "temp_input_2.mp4"

    # Copy master to temp_file1
    with open(input_master, "rb") as sf, open(temp_file1, "wb") as df:
        df.write(sf.read())

    # Simulate watcher queueing first job
    job_id_1 = db.add_job(str(temp_file1), "", "youtube")
    print(f"Queued initial job: ID={job_id_1}")
    success_1 = executor.run_pipeline(job_id_1)
    print(f"Executed initial job: Success={success_1}")

    # Copy master to temp_file2
    with open(input_master, "rb") as sf, open(temp_file2, "wb") as df:
        df.write(sf.read())

    job_id_2 = db.add_job(str(temp_file2), "", "youtube")
    print(f"Queued duplicate job: ID={job_id_2}")
    success_2 = executor.run_pipeline(job_id_2)
    print(f"Executed duplicate job: Success={success_2}")

    # Cleanup
    for p in [temp_file1, temp_file2]:
        if p.exists():
            p.unlink()

    # Step 3: Query history table and verify fields
    history_entries = db.get_history(limit=5)
    print(f"Total history entries retrieved: {len(history_entries)}")

    # Write output evidence
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("=== Duplicate Detection History DB Dump ===\n\n")
        for h in history_entries:
            row_dict = dict(h)
            line = (
                f"ID: {row_dict['id']} | "
                f"Job ID: {row_dict['job_id']} | "
                f"Original Name: {row_dict['original_name']} | "
                f"Status: {row_dict['status']} | "
                f"Reason: {row_dict['reason']} | "
                f"Duration: {row_dict['duration']}s | "
                f"Conv Time: {row_dict['conversion_time_seconds']}s | "
                f"Speed: {row_dict['avg_speed']}x\n"
            )
            print(line.strip())
            f.write(line)

    print(f"Evidence log written to: {log_file}")


if __name__ == "__main__":
    main()
