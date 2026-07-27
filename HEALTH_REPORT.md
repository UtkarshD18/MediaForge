# System Health Report - MediaForge

This document establishes the verified system health matrix and telemetry integration check results for **MediaForge** on the Fedora workstation environment.

---

## 🚦 Integration Health Grid

| Component | Status | Verification Protocol | Notes |
| :--- | :--- | :--- | :--- |
| **packaging** | 🟢 PASS | `uv sync` / `pip install -e .` | Successfully maps `src` package imports cleanly under virtual environments. |
| **CLI** | 🟢 PASS | `mediaforge doctor` & `status` | Arguments parse correctly, commands route, and doctor outputs report healthy. |
| **watcher** | 🟢 PASS | watchdog folder monitoring | Instantly tracks file creation in `~/Videos/Incoming` and polls transfer locks. |
| **queue** | 🟢 PASS | FIFO SQLite scheduling | Jobs list sequentially and execute without overlapping resources. |
| **SQLite** | 🟢 PASS | migration application & history logs | Connects to `~/.local/share/mediaforge/mediaforge.db`, auto-migrates schemas. |
| **IPC** | 🟢 PASS | UDS socket transactions | IPC client and server communicate commands over `/run/user/1000/mediaforge.sock`. |
| **Event Bus** | 🟢 PASS | pub/sub thread notifications | Dispatchers wire system state signals across daemon threads. |
| **thumbnails** | 🟢 PASS | FFmpeg extraction | Auto-seeks and generates poster frames in `DaVinci/cache/`. |
| **GPU** | 🟢 PASS | CUDA acceleration | Doctor detects hardware acceleration, executing `-hwaccel cuda` transcodes. |
| **duplicate detection** | 🟢 PASS | SHA256 matches | Compares hashes against SQLite cache, bypassing duplicate files. |
| **FFmpeg** | 🟢 PASS | ProRes HQ mov exports | Generates standard editing profiles smoothly with native speed. |
| **Resolve compatibility** | 🟢 PASS | Manual timeline playback | Apple ProRes 422 HQ is natively recognized by DaVinci Resolve. |

---

## 📂 Runtime Path Mapping

To keep the repository root clean and avoid committing local states, all runtime assets are managed under XDG-compliant system user directories:

1. **SQLite Database**: `~/.local/share/mediaforge/mediaforge.db`
2. **UNIX Domain Socket (IPC)**: `/run/user/1000/mediaforge.sock` (Resolves dynamically via `$XDG_RUNTIME_DIR`)
3. **Application Logs**: `~/projects/MediaForge/logs/` (Separated by date)
