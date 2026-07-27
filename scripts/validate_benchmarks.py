import sys
import time
from pathlib import Path
import subprocess

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

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
    print("Performance Profiling starting...")
    evidence_dir = PROJECT_ROOT / "evidence" / "benchmarks"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    log_file = evidence_dir / "profiling_results.log"

    # 1. Startup Latency
    print("Measuring engine startup latency...")
    t0 = time.perf_counter()
    
    from src.db import DatabaseManager
    from src.config import ConfigManager
    from src.executor import PipelineExecutor
    
    config_mgr = ConfigManager(PROJECT_ROOT)
    db_path = PROJECT_ROOT / "mediaforge_benchmark.db"
    if db_path.exists():
        db_path.unlink()
        
    db = DatabaseManager(db_path)
    executor = PipelineExecutor(db, config_mgr)
    
    startup_time = time.perf_counter() - t0
    print(f"Startup latency: {startup_time * 1000:.2f} ms")

    # 2. Idle Memory Footprint
    idle_ram = get_rss_memory_mb()
    print(f"Idle RAM footprint: {idle_ram:.2f} MB")

    # 3. DB Latency (1000 reads and writes)
    print("Profiling database query latency...")
    # Write transactions
    t_w0 = time.perf_counter()
    for i in range(500):
        db.execute_write("INSERT INTO settings (key, value) VALUES (?, ?)", (f"test_key_{i}", f"test_val_{i}"))
    db_write_latency_ms = ((time.perf_counter() - t_w0) / 500) * 1000

    # Read transactions
    t_r0 = time.perf_counter()
    for i in range(500):
        db.execute_read("SELECT value FROM settings WHERE key = ?", (f"test_key_{i}",))
    db_read_latency_ms = ((time.perf_counter() - t_r0) / 500) * 1000
    
    print(f"DB Write latency: {db_write_latency_ms:.3f} ms/query")
    print(f"DB Read latency: {db_read_latency_ms:.3f} ms/query")

    # Clean up benchmark DB
    for suffix in ["", "-wal", "-shm"]:
        p = db_path.parent / (db_path.name + suffix)
        if p.exists():
            try: p.unlink()
            except Exception: pass

    # 4. Transcoding Peak Memory (using original test file)
    input_file = PROJECT_ROOT / "test_input.mp4"
    if not input_file.exists():
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=5:size=320x240:rate=30",
            "-c:v", "libx264", "-t", "5", str(input_file)
        ], capture_output=True, check=True)

    # Trigger transcode and monitor RAM in a separate thread
    import threading
    peak_ram = [idle_ram]
    monitor_active = True

    def monitor_ram():
        while monitor_active:
            peak_ram.append(get_rss_memory_mb())
            time.sleep(0.1)

    monitor_thread = threading.Thread(target=monitor_ram, daemon=True)
    monitor_thread.start()

    # Re-run clean DB for transcode job
    transcode_db_path = PROJECT_ROOT / "mediaforge_transcode_bench.db"
    for suffix in ["", "-wal", "-shm"]:
        p = transcode_db_path.parent / (transcode_db_path.name + suffix)
        if p.exists():
            try: p.unlink()
            except Exception: pass

    db_t = DatabaseManager(transcode_db_path)
    executor_t = PipelineExecutor(db_t, config_mgr)

    # Override config stability duration to bypass delay
    config_mgr.config.stability_duration = 0.1

    print("Running benchmark transcode...")
    temp_input = PROJECT_ROOT / "temp_bench.mp4"
    import shutil
    shutil.copy2(input_file, temp_input)
    
    job_id = db_t.add_job(str(temp_input), "", "youtube")
    
    t_trans0 = time.perf_counter()
    executor_t.run_pipeline(job_id)
    transcode_time = time.perf_counter() - t_trans0

    # Stop monitor
    monitor_active = False
    monitor_thread.join()

    peak_ram_val = max(peak_ram)
    print(f"Transcode duration: {transcode_time:.2f} s")
    print(f"Peak RAM during transcode: {peak_ram_val:.2f} MB")

    # Clean up transcode bench db and clips
    for suffix in ["", "-wal", "-shm"]:
        p = transcode_db_path.parent / (transcode_db_path.name + suffix)
        if p.exists():
            try: p.unlink()
            except Exception: pass
            
    # Remove temp files and output mov
    if temp_input.exists():
        temp_input.unlink()
        
    clips_dir = config_mgr.get_resolved_path("resolve_clips_folder")
    out_mov = clips_dir / "temp_bench.mov"
    if out_mov.exists():
        out_mov.unlink()
        
    orig_dir = config_mgr.get_resolved_path("originals_folder")
    orig_mp4 = orig_dir / "temp_bench.mp4"
    if orig_mp4.exists():
        orig_mp4.unlink()

    # Write report
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("=== MediaForge V1 Benchmark Profiling ===\n\n")
        f.write(f"Startup Initialization Latency: {startup_time * 1000:.2f} ms\n")
        f.write(f"Idle System RAM Footprint: {idle_ram:.2f} MB\n")
        f.write(f"Peak System RAM during Transcode: {peak_ram_val:.2f} MB\n")
        f.write(f"Memory Increment: {peak_ram_val - idle_ram:.2f} MB\n")
        f.write(f"SQLite DB Write Latency: {db_write_latency_ms:.4f} ms/query\n")
        f.write(f"SQLite DB Read Latency: {db_read_latency_ms:.4f} ms/query\n")
        f.write(f"Test Video Transcode Duration: {transcode_time:.2f} s\n")

    print(f"Evidence log written to: {log_file}")

if __name__ == "__main__":
    main()
