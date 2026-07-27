# Changelog - MediaForge

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.0-rc1] - 2026-07-27

### Added
- **Core Ingestion Engine**: Folder watcher (using `watchdog`), worker scheduler, and SQLite queue persistence.
- **Transcoding Pipeline**: FFmpeg-based conversions supporting ProRes HQ/Proxy, DNxHR, and direct stream copying.
- **Hardware Acceleration**: Automatic NVDEC CUDA detection with a graceful CPU fallback strategy.
- **Duplicate Bypass**: SHA256 file hashing database lookup to bypass already ingested duplicates.
- **IPC Interface**: Unix Domain Socket daemon client-server querying.
- **UI Tray Dashboard**: System monitor displaying stats, queue loads, and toggle events.
- **Diagnostic Tool**: `mediaforge doctor` suite checking paths, GPU, and binary assets.
- **Robustness Features**: Auto-recreation of output clips/originals folders if unlinked mid-conversion, and dynamic seekers for short video thumbnails.
- **CI Workflows**: GitHub Actions validating Ruff, typing (Mypy), and Bandit scans on multiple Python runtimes.

### Changed
- Refactored duplicate record status codes to write `status="duplicate"` and `reason="sha256_match"` with zeroed timers.
- GUI telemetry monitors slowed to 5.0 seconds and connected window visibility event hooks to pause active GUI polling.

### Fixed
- Fixed critical missing module `import time` error inside the UDS daemon connection loops.
- Fixed thumbnail generator bounds crashes by dynamically seeking based on footage duration for short clips.
