import sys
import time
from pathlib import Path
import shutil
import threading
import subprocess

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.db import DatabaseManager
from src.executor import PipelineExecutor
from src.scheduler import QueueScheduler
from src.watcher import FileWatcher
from src.config import ConfigManager

def get_rss_memory_mb() -> float:
    try:
        with open("/proc/self/status", "r") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return float(line.split()[1]) / 1024.0
    except Exception:
        pass
    return 0.0

def main():
    print("Stress Testing Ingestion Engine (100 Simultaneous Videos)...")
    evidence_dir = PROJECT_ROOT / "evidence" / "stress-tests"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    log_file = evidence_dir / "stress_test.log"
    csv_file = evidence_dir / "stress_test_throughput.csv"

    # Reset DB
    db_path = PROJECT_ROOT / "mediaforge.db"
    for suffix in ["", "-wal", "-shm"]:
        p = db_path.parent / (db_path.name + suffix)
        if p.exists():
            try: p.unlink()
            except Exception: pass

    db = DatabaseManager(db_path)
    config_mgr = ConfigManager(PROJECT_ROOT)
    
    # Configure low latency and overwrite existing to speed up stress test
    config_mgr.config.overwrite_existing = True
    config_mgr.config.stability_duration = 0.1
    
    executor = PipelineExecutor(db, config_mgr)
    scheduler = QueueScheduler(db, executor)
    watcher = FileWatcher(db, config_mgr)

    # 1. Generate 1-second base clip
    temp_src_dir = PROJECT_ROOT / "temp_stress_src"
    temp_src_dir.mkdir(parents=True, exist_ok=True)
    base_clip = temp_src_dir / "base.mp4"
    
    print("Generating base 1-second clip using ffmpeg...")
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=320x180:rate=30",
        "-c:v", "libx264", "-t", "1", str(base_clip)
    ], capture_output=True, check=True)

    # 2. Copy base clip 100 times to simulate batch drop
    print("Preparing 100 duplicate files...")
    incoming_dir = config_mgr.get_resolved_path("incoming_folder")
    
    # Ensure clean incoming directory
    for f in incoming_dir.glob("*"):
        if f.is_file():
            f.unlink()

    batch_dir = PROJECT_ROOT / "temp_stress_batch"
    batch_dir.mkdir(parents=True, exist_ok=True)
    
    for i in range(1, 101):
        target = batch_dir / f"stress_test_{i:03d}.mp4"
        shutil.copy2(base_clip, target)

    # Start watcher and scheduler
    scheduler.start()
    watcher.start()

    # Wait for watcher to initialize
    time.sleep(1.0)

    # 3. Drop all 100 files simultaneously (move from batch_dir to incoming_dir)
    print("Dropping 100 files simultaneously into watched folder...")
    start_time = time.time()
    
    # Move files
    for i in range(1, 101):
        shutil.move(batch_dir / f"stress_test_{i:03d}.mp4", incoming_dir / f"stress_test_{i:03d}.mp4")

    # Monitor loop
    time_series = []
    
    print("Monitoring queue processing progress...")
    while True:
        # Check active & queued count
        queued = db.execute_read("SELECT COUNT(*) as count FROM jobs WHERE status = 'queued'")
        active = db.execute_read("SELECT COUNT(*) as count FROM jobs WHERE status IN ('analyzing', 'converting', 'post_processing', 'moving')")
        completed = db.execute_read("SELECT COUNT(*) as count FROM jobs WHERE status = 'completed'")
        duplicates = db.execute_read("SELECT COUNT(*) as count FROM jobs WHERE status = 'duplicate'")
        failed = db.execute_read("SELECT COUNT(*) as count FROM jobs WHERE status = 'failed'")
        
        q_count = queued[0]["count"]
        a_count = active[0]["count"]
        c_count = completed[0]["count"]
        d_count = duplicates[0]["count"]
        f_count = failed[0]["count"]
        
        elapsed = time.time() - start_time
        ram = get_rss_memory_mb()
        
        metrics = {
            "elapsed": round(elapsed, 2),
            "queued": q_count,
            "active": a_count,
            "completed": c_count,
            "duplicates": d_count,
            "failed": f_count,
            "ram_mb": round(ram, 2)
        }
        time_series.append(metrics)
        
        print(f"Elapsed: {elapsed:.1f}s | Queued: {q_count} | Active: {a_count} | Completed: {c_count} | Duplicates: {d_count} | Failed: {f_count} | RAM: {ram:.1f}MB")
        
        # Check if all 100 are processed (since they are duplicates, job 1 should be completed, jobs 2-100 should be duplicates!)
        if c_count + d_count + f_count >= 100:
            break
            
        time.sleep(1.0)

    total_time = time.time() - start_time
    print(f"Stress test complete in {total_time:.2f} seconds!")

    # Stop watcher and scheduler
    watcher.stop()
    scheduler.stop()

    # Clean up temp folders
    shutil.rmtree(temp_src_dir, ignore_errors=True)
    shutil.rmtree(batch_dir, ignore_errors=True)
    
    # Clear clips and originals generated during test
    clips_dir = config_mgr.get_resolved_path("resolve_clips_folder")
    for f in clips_dir.glob("stress_test_*"):
        f.unlink()
        
    orig_dir = config_mgr.get_resolved_path("originals_folder")
    for f in orig_dir.glob("stress_test_*"):
        f.unlink()

    # Save CSV metrics
    with open(csv_file, "w", encoding="utf-8") as f:
        f.write("elapsed_seconds,queued,active,completed,duplicates,failed,ram_mb\n")
        for ts in time_series:
            f.write(f"{ts['elapsed']},{ts['queued']},{ts['active']},{ts['completed']},{ts['duplicates']},{ts['failed']},{ts['ram_mb']}\n")

    # Save log evidence
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("=== Ingestion Stress Test Report ===\n")
        f.write(f"Total files dropped: 100\n")
        f.write(f"Total time elapsed: {total_time:.2f} seconds\n")
        f.write(f"Average throughput: {100 / total_time:.2f} files/second\n")
        f.write(f"Final Completed count: {c_count}\n")
        f.write(f"Final Duplicates count: {d_count}\n")
        f.write(f"Final Failed count: {f_count}\n")
        f.write(f"Peak RAM usage: {max(ts['ram_mb'] for ts in time_series):.2f} MB\n")

    print(f"Evidence files written to {log_file} and {csv_file}")

if __name__ == "__main__":
    main()
