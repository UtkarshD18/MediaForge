# Risk Register - MediaForge V1

This document evaluates system integration risks, performance bottlenecks, and hardware dependency mitigations for **MediaForge**.

---

## ⚡ Risk Assessment Matrix

| Risk ID | Risk Description | Probability | Impact | Mitigation Plan |
| :--- | :--- | :--- | :--- | :--- |
| **RSK-001** | FFmpeg execution failures due to unsupported source video container streams. | Medium | Medium | Implement automatic ffmpeg error diagnostics parsing and log clear details in the history table. |
| **RSK-002** | CUDA driver or NVDEC decoder unavailability on target host. | Low | Low | Built-in fallback routines instantly catch execution errors and run CPU-based transcoding instead. |
| **RSK-003** | Disk space depletion during high-volume transcode runs. | Medium | High | Perform disk space check verification inside the pre-transcode pipeline checks. |
| **RSK-004** | SQLite queue database corruption due to hard system power cuts. | Low | High | Enable Write-Ahead Logging (`WAL`) and execute all status updates inside ACID transactional boundaries. |
| **RSK-005** | Watchdog missed file events on rapid network storage (NAS) connections. | Medium | Medium | Perform periodic directory scans on a cron-like ticker or CLI status triggers to re-index. |
