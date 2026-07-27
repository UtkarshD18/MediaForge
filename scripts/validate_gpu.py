import sys
from pathlib import Path
import threading

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.processors.converter import ConversionJob, FFmpegBuilder, run_conversion, detect_gpu_support

def main():
    print("GPU Validation Test starting...")
    evidence_dir = PROJECT_ROOT / "evidence" / "doctor"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    log_file = evidence_dir / "gpu_validation.log"

    # Step 1: Detect hardware acceleration
    hwaccel = detect_gpu_support()
    print(f"Detected hardware accelerator: {hwaccel}")

    # Step 2: Create a conversion job
    input_path = PROJECT_ROOT / "test_input.mp4"
    output_path = PROJECT_ROOT / "test_output.mov"

    job = ConversionJob(
        input_path=input_path,
        output_path=output_path,
        video_codec="prores",
        profile="3", # ProRes HQ
        audio_codec="pcm_s16le",
        duration=5.0,
        hwaccel=hwaccel
    )

    # Compile the command
    cmd = FFmpegBuilder.build(job)
    cmd_str = " ".join(cmd)
    print(f"Generated FFmpeg Command:\n{cmd_str}")

    # Step 3: Run the conversion
    cancel_event = threading.Event()
    
    def on_progress(percent, eta, speed):
        print(f"Progress: {percent:.1f}% | ETA: {eta:.1f}s | Speed: {speed:.1f}x")

    try:
        run_conversion(job, on_progress, cancel_event)
        print("Conversion succeeded!")
        success = True
    except Exception as e:
        print(f"Conversion failed: {e}")
        success = False

    # Save to evidence
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("=== FFmpeg Hardware Acceleration Test ===\n")
        f.write(f"Detected hwaccel method: {hwaccel}\n")
        f.write(f"Executed FFmpeg command:\n{cmd_str}\n\n")
        f.write(f"Success: {success}\n")
        if not success:
            f.write("Triggering fallback validation...\n")
            # Force CPU conversion
            job.hwaccel = None
            cpu_cmd = FFmpegBuilder.build(job)
            f.write(f"CPU Fallback command:\n{' '.join(cpu_cmd)}\n")

    print(f"Evidence log written to: {log_file}")

if __name__ == "__main__":
    main()
