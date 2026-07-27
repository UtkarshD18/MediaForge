# Command Line Interface (CLI) Manual - MediaForge

This document describes the command-line commands, parameter interfaces, and response telemetry structures available in **MediaForge**.

---

## 🚀 Command Syntax

All CLI operations are launched using the primary wrapper:

```bash
mediaforge [command] [options]
```

---

## 📋 Commands Directory

### 1. `mediaforge doctor`
Runs health diagnostic scans on the local host environment.
* **Checks performed**:
  * Python runtime version validation (expects `3.11` to `3.13`).
  * FFmpeg and FFprobe binary execution paths.
  * GPU drivers and CUDA acceleration status.
  * Watched directory workspace existence.
  * Systemd service unit registration.
* **Syntax**:
  ```bash
  mediaforge doctor
  ```

### 2. `mediaforge watch`
Starts the background daemon engine interactively in the current terminal, initializing the SQLite migrations, watchdog observers, worker schedulers, and UDS IPC servers.
* **Syntax**:
  ```bash
  mediaforge watch
  ```

### 3. `mediaforge status`
Queries the local active daemon over the UDS and reports engine execution states.
* **Output fields**:
  * Daemon connection status.
  * Active processing job name, codec, and duration.
  * Progress percentage and dynamic ETA.
  * Queue load sizing.
* **Syntax**:
  ```bash
  mediaforge status
  ```

### 4. `mediaforge queue`
Prints a formatted text grid displaying all currently queued, active, or failed tasks inside the SQLite queue.
* **Syntax**:
  ```bash
  mediaforge queue
  ```

### 5. `mediaforge history`
Prints a historical log grid of completed ingest records.
* **Syntax**:
  ```bash
  mediaforge history [--limit N]
  ```

### 6. `mediaforge pause` / `mediaforge resume`
Suspends or resumes polling in the Queue Scheduler. Active conversions are allowed to complete.
* **Syntax**:
  ```bash
  mediaforge pause
  mediaforge resume
  ```

### 7. `mediaforge cancel`
Abruptly cancels the active transcoding job, unrolls temp files, and shifts status to `cancelled`.
* **Syntax**:
  ```bash
  mediaforge cancel
  ```
