import argparse
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any

# Add parent directory to sys.path to enable 'src.' imports
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from src.config import ConfigManager
from src.db import DatabaseManager
from src.events import Events, get_event_bus
from src.executor import PipelineExecutor
from src.integrations.resolve import is_resolve_installed
from src.ipc import IpcClient, IpcServer
from src.logger import setup_logger
from src.metadata import get_video_metadata
from src.notifier import setup_notifier
from src.processors.converter import ConversionJob, detect_gpu_support, run_conversion
from src.scheduler import QueueScheduler
from src.utils import get_runtime_db_path, get_runtime_socket_path, wait_for_file_copy
from src.watcher import FileWatcher


def run_daemon(project_root: Path) -> None:
    """
    Core watcher daemon startup routine. Initializes all threads and blocks until stopped.
    """
    # 1. Config Manager
    config_mgr = ConfigManager(project_root)

    # 2. Logger Setup
    log_dir = project_root / "logs"
    logger = setup_logger(log_dir, config_mgr.config.logging_level if config_mgr.config else "INFO")
    logger.info("Initializing MediaForge Ingestion Daemon...")

    # 3. Database Setup
    db_path = get_runtime_db_path()
    db = DatabaseManager(db_path)

    # 4. Notifier Setup
    setup_notifier(config_mgr.config)

    # 5. Pipeline & Threads setup
    executor = PipelineExecutor(db, config_mgr)
    scheduler = QueueScheduler(db, executor)
    watcher = FileWatcher(db, config_mgr)

    socket_path = get_runtime_socket_path()
    ipc_server = IpcServer(socket_path, db, scheduler, executor, config_mgr)

    # Teardown event loop coordination
    stop_event = threading.Event()

    def handle_stop_event(data: Any = None) -> None:
        logger.info("Termination signal received. Gracefully stopping daemon components...")
        watcher.stop()
        scheduler.stop()
        ipc_server.stop()
        stop_event.set()

    # Wire to Event Bus stop signals
    get_event_bus().subscribe(Events.DAEMON_STOPPED, handle_stop_event)

    # Register OS signals
    def handle_os_signal(signum, frame):
        logger.info(f"OS Signal {signum} intercepted.")
        get_event_bus().publish(Events.DAEMON_STOPPED)

    signal.signal(signal.SIGINT, handle_os_signal)
    signal.signal(signal.SIGTERM, handle_os_signal)

    # Start threads
    scheduler.start()
    watcher.start()
    ipc_server.start()

    logger.info("MediaForge Ingestion Daemon is fully ACTIVE.")

    # Block main thread until stop_event is set
    while not stop_event.is_set():
        time.sleep(1.0)

    logger.info("MediaForge Ingestion Daemon has shut down successfully.")


def run_local_conversion(project_root: Path, file_path_str: str, profile_override: str | None = None) -> None:
    """
    CLI convert helper to execute synchronous conversion on a single file.
    """
    config_mgr = ConfigManager(project_root)
    logger = setup_logger(project_root / "logs", "INFO")

    file_path = Path(file_path_str).resolve()
    if not file_path.exists():
        logger.error(f"Target file not found: {file_path}")
        sys.exit(1)

    profile_name = profile_override or config_mgr.config.active_profile if config_mgr.config else "youtube"
    profile = config_mgr.profiles.get(profile_name)
    if not profile:
        logger.error(f"Encoding profile '{profile_name}' is not configured.")
        sys.exit(1)

    logger.info(f"Running single file conversion for {file_path.name} using profile '{profile_name}'...")

    # Verify copy
    wait_for_file_copy(file_path)

    # Read meta
    meta = get_video_metadata(file_path)
    logger.info(
        f"Metadata read - Codec: {meta['codec']} | Resolution: {meta['width']}x{meta['height']} | Duration: {meta['duration']}s"
    )

    dest_dir = config_mgr.get_resolved_path("resolve_clips_folder")
    dest_path = dest_dir / f"{file_path.stem}.{profile.ext}"

    # Resolve collision
    if dest_path.exists() and not (config_mgr.config.overwrite_existing if config_mgr.config else False):
        counter = 1
        while True:
            new_path = dest_dir / f"{file_path.stem}_{counter}.{profile.ext}"
            if not new_path.exists():
                dest_path = new_path
                break
            counter += 1

    gpu = detect_gpu_support()
    job = ConversionJob(
        input_path=file_path,
        output_path=dest_path,
        video_codec=profile.video_codec,
        profile=profile.profile,
        audio_codec=profile.audio_codec,
        duration=meta["duration"],
        hwaccel=gpu,
    )

    cancel_event = threading.Event()

    def on_progress(p, e, s):
        print(f"\rConversion Progress: {p:.1f}% | Speed: {s:.2f}x | ETA: {int(e)}s", end="", flush=True)

    try:
        run_conversion(job, on_progress, cancel_event)
        print("\nReady for Editor!")
        logger.info(f"Successfully converted file to: {dest_path}")
    except Exception as e:
        print(f"\nConversion failed: {e}")
        sys.exit(1)


def run_doctor(project_root: Path) -> None:
    """
    MediaForge doctor subcommand system check verification.
    """
    import shutil
    import subprocess

    print("\nMediaForge Doctor")
    print("----------------------------------------")

    healthy = True
    errors = []

    # 1. Python version
    py_ver = f"{sys.version.split()[0]}"
    print(f"✓ Python {py_ver}")

    # 2. FFmpeg found
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        print("✓ FFmpeg found")
    else:
        print("✗ FFmpeg missing")
        healthy = False
        errors.append("FFmpeg executable not found in system PATH.")

    # 3. FFprobe found
    ffprobe_path = shutil.which("ffprobe")
    if ffprobe_path:
        print("✓ FFprobe found")
    else:
        print("✗ FFprobe missing")
        healthy = False
        errors.append("FFprobe executable not found in system PATH.")

    # 4. SQLite OK
    try:
        db_path = get_runtime_db_path()
        db = DatabaseManager(db_path)
        # Test basic connection and write query
        db.execute_read("PRAGMA schema_version")
        print("✓ SQLite OK")
    except Exception as e:
        print("✗ SQLite error")
        healthy = False
        errors.append(f"SQLite database checks failed: {e}")

    # 5. Watchdog OK
    try:
        import watchdog  # noqa: F401

        print("✓ Watchdog OK")
    except ImportError:
        print("✗ Watchdog package missing")
        healthy = False
        errors.append("Python watchdog library is not installed in the current environment.")

    # 6. Config OK
    try:
        config_mgr = ConfigManager(project_root)
        print("✓ Config OK")
    except Exception as e:
        print("✗ Config error")
        healthy = False
        errors.append(f"Failed to load application settings YAML: {e}")
        return  # Stop doctor here since paths depend on config

    # 7. Incoming folder exists
    inc_path = config_mgr.get_resolved_path("incoming_folder")
    if inc_path.exists() and inc_path.is_dir():
        print("✓ Incoming folder exists")
    else:
        print("✗ Incoming folder missing")
        healthy = False
        errors.append(f"Incoming watch directory does not exist: {inc_path}")

    # 8. Output folder exists
    clips_path = config_mgr.get_resolved_path("resolve_clips_folder")
    if clips_path.exists() and clips_path.is_dir():
        print("✓ Output folder exists")
    else:
        print("✗ Output folder missing")
        healthy = False
        errors.append(f"Resolve clips target directory does not exist: {clips_path}")

    # 9. DaVinci Resolve detected
    if is_resolve_installed():
        print("✓ DaVinci Resolve detected")
    else:
        print("✗ DaVinci Resolve not found")
        # Do not mark as unhealthy; it is a soft warning since engine can run editor-agnostic
        errors.append("Soft Warning: DaVinci Resolve directory (/opt/resolve) was not detected.")

    # 10. NVIDIA GPU detected
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        print("✓ NVIDIA GPU detected")
    else:
        print("✗ NVIDIA GPU not found")
        # Soft warning

    # 11. CUDA decoding available
    gpu_accel = detect_gpu_support()
    if gpu_accel == "cuda":
        print("✓ CUDA decoding available")
    elif gpu_accel:
        print(f"✓ GPU decoding available ({gpu_accel.upper()})")
    else:
        print("✗ GPU hardware decoding unavailable (using CPU fallback)")

    # 12. Write permissions OK
    permissions_ok = True
    for p_name, path in [
        ("Incoming", inc_path),
        ("Clips", clips_path),
        ("Originals", config_mgr.get_resolved_path("originals_folder")),
    ]:
        if path.exists():
            test_file = path / ".mf_permission_test"
            try:
                test_file.write_text("test")
                test_file.unlink()
            except Exception:
                print(f"✗ Write permissions error in {p_name} folder")
                permissions_ok = False
                healthy = False
                errors.append(f"Write permission denied in folder: {path}")
    if permissions_ok:
        print("✓ Write permissions OK")

    # 13. Systemd service enabled
    try:
        out = subprocess.run(
            ["systemctl", "--user", "is-enabled", "mediaforge.service"], capture_output=True, text=True
        )
        if out.stdout.strip() == "enabled":
            print("✓ Systemd service enabled")
        else:
            print("✗ Systemd service disabled")
            healthy = False
            errors.append("Systemd service is registered but not enabled.")
    except Exception as e:
        print("✗ Systemd query error")
        healthy = False
        errors.append(f"Unable to query systemctl user service: {e}")

    print("----------------------------------------")
    if healthy:
        print("Overall: Healthy")
    else:
        print("Overall: Unhealthy (errors detected)")
        print("\nDiagnostics issues:")
        for idx, err in enumerate(errors, 1):
            print(f"  {idx}. {err}")
    print()


def get_gpu_info() -> tuple[str, bool, bool]:
    """
    Detects GPU model name, CUDA, and NVDEC support.
    """
    import shutil
    import subprocess

    gpu_model = "None / CPU Only"
    cuda_ok = False
    nvdec_ok = False

    # Check nvidia-smi
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        try:
            res = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=3.0,
            )
            if res.returncode == 0 and res.stdout.strip():
                gpu_model = res.stdout.strip()
        except Exception:
            pass

    # Check CUDA support via ffmpeg decoders
    try:
        res = subprocess.run(["ffmpeg", "-decoders"], capture_output=True, text=True, timeout=3.0)
        if res.returncode == 0:
            decoders = res.stdout.lower()
            if "h264_cuvid" in decoders or "hevc_cuvid" in decoders:
                nvdec_ok = True
                cuda_ok = True
    except Exception:
        pass

    # If cuda support is available but nvidia-smi didn't return a name, check lspci
    if gpu_model == "None / CPU Only" and cuda_ok:
        gpu_model = "NVIDIA GPU"

    return gpu_model, cuda_ok, nvdec_ok


def print_status(project_root: Path) -> None:
    """
    Queries running daemon state and prints the MediaForge console dashboard.
    """
    import os
    from pathlib import Path

    socket_path = get_runtime_socket_path()
    client = IpcClient(socket_path)

    # 1. Gather GPU metrics
    gpu_model, cuda_ok, nvdec_ok = get_gpu_info()

    # 2. Handle daemon offline scenario
    if not client.is_daemon_running():
        print("══════════════════════════════════════")
        print("MediaForge")
        print("══════════════════════════════════════")
        print("Daemon        ✗ Stopped")
        print("Watcher       ✗ Stopped")
        print("Queue         --")
        print(f"GPU           {gpu_model}")
        print(f"              CUDA {'✓' if cuda_ok else '✗'}")
        print(f"              NVDEC {'✓' if nvdec_ok else '✗'}")
        print("SQLite        Disconnected")
        print("IPC           ✗ Disconnected")
        print("Incoming      --")
        print("Processed     --")
        print("Duplicates    --")
        print("\nLast Job      --")
        print("══════════════════════════════════════")
        return

    # 3. Handle daemon online scenario
    resp = client.send_command({"command": "status"})
    if not resp.get("success"):
        print(f"Error querying daemon: {resp.get('error')}")
        return

    status_str = resp.get("status", "unknown")
    watcher_state = "✓ Watching" if status_str == "watching" else "✗ Paused"
    daemon_state = "✓ Running"

    queue_size = resp.get("queue_size", 0)
    processed_size = resp.get("processed_size", 0)
    duplicate_size = resp.get("duplicate_size", 0)

    # Ingestion folders
    incoming_raw = resp.get("config", {}).get("incoming_folder", "~/Videos/Incoming")
    incoming_dir = Path(os.path.expanduser(incoming_raw)).resolve()
    incoming_count = 0
    if incoming_dir.exists() and incoming_dir.is_dir():
        incoming_count = len([f for f in incoming_dir.glob("*") if f.is_file()])

    print("══════════════════════════════════════")
    print("MediaForge")
    print("══════════════════════════════════════")
    print(f"Daemon        {daemon_state}")
    print(f"Watcher       {watcher_state}")
    print(f"Queue         {queue_size} jobs")
    print(f"GPU           {gpu_model}")
    print(f"              CUDA {'✓' if cuda_ok else '✗'}")
    print(f"              NVDEC {'✓' if nvdec_ok else '✗'}")
    print("SQLite        Connected")
    print("IPC           Connected")
    print(f"Incoming      {incoming_count}")
    print(f"Processed     {processed_size}")
    print(f"Duplicates    {duplicate_size}")

    # Active or Last Job rendering
    active = resp.get("active_job")
    last_job = resp.get("last_job")

    if active:
        name = Path(active["filepath"]).name
        progress = active.get("progress", 0.0)
        eta = active.get("eta_seconds", 0.0)
        status_label = active.get("status", "processing").capitalize()
        print(f"\nActive Job    {name}")
        print(f"              Status: {status_label}")
        print(f"              Progress: {progress:.1f}%")
        print(f"              ETA: {int(eta // 60):02d}:{int(eta % 60):02d}")
    elif last_job:
        name = last_job.get("original_name", "unknown")
        status_label = last_job.get("status", "completed").capitalize()
        conv_time = last_job.get("conversion_time_seconds", 0.0)
        out_path = last_job.get("converted_path", "")

        # Format output path using tilde if under home
        home_str = str(Path.home())
        if out_path.startswith(home_str):
            out_path = out_path.replace(home_str, "~", 1)

        print(f"\nLast Job      {name}")
        print(f"              {status_label}")
        print(f"              {int(conv_time)} seconds")
        print(f"              Output: {out_path}")
    else:
        print("\nLast Job      --")

    print("══════════════════════════════════════")


def main() -> None:
    # Resolve project root automatically based on python script layout location
    project_root = Path(__file__).parent.parent.resolve()

    parser = argparse.ArgumentParser(description="MediaForge Ingestion Engine Utility")
    subparsers = parser.add_subparsers(dest="command", required=False)

    # 1. Watch Subcommand
    subparsers.add_parser("watch", help="Start background file ingestion daemon.")

    # 2. Convert Subcommand
    conv_parser = subparsers.add_parser("convert", help="Convert a file synchronously using default profile.")
    conv_parser.add_argument("input_file", type=str, help="Absolute path to target video file.")

    # 3. Profile Subcommand
    prof_parser = subparsers.add_parser("profile", help="Convert a file synchronously using a specific profile.")
    prof_parser.add_argument("profile_name", type=str, help="Encoding profile name (e.g. proxy, social).")
    prof_parser.add_argument("input_file", type=str, help="Absolute path to target video file.")

    # 4. Doctor Subcommand
    subparsers.add_parser("doctor", help="Verify dependencies, file paths, and drivers.")

    # 5. Status Subcommand
    subparsers.add_parser("status", help="Get status of running watcher daemon.")
    subparsers.add_parser("dashboard", help="Display the console status dashboard.")

    # 6. Stop Subcommand
    subparsers.add_parser("stop", help="Shutdown the running daemon.")

    # 7. GUI Subcommand
    subparsers.add_parser("gui", help="Open the MediaForge GUI Dashboard dashboard.")

    args = parser.parse_args()

    # Default to GUI if no arguments are provided
    if not args.command:
        # Launch PySide6 GUI
        from src.gui import start_gui

        socket_path = get_runtime_socket_path()
        start_gui(socket_path, project_root)
        return

    if args.command == "watch":
        run_daemon(project_root)
    elif args.command == "convert":
        run_local_conversion(project_root, args.input_file)
    elif args.command == "profile":
        run_local_conversion(project_root, args.input_file, args.profile_name)
    elif args.command == "doctor":
        run_doctor(project_root)
    elif args.command in ("status", "dashboard"):
        print_status(project_root)
    elif args.command == "stop":
        socket_path = get_runtime_socket_path()
        client = IpcClient(socket_path)
        resp = client.send_command({"command": "stop"})
        print(resp.get("message", "Stop command sent."))
    elif args.command == "gui":
        from src.gui import start_gui

        socket_path = get_runtime_socket_path()
        start_gui(socket_path, project_root)


if __name__ == "__main__":
    main()
