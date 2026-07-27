# MediaForge System Flowcharts

This document houses the Mermaid flowcharts detailing the functional pathways of **MediaForge**.

---

## 📂 1. Folder Watching & Ingestion Queue

```mermaid
flowchart TD
    A[File Copied to Incoming/] --> B{watchdog Event}
    B --> C[Check if file extension is valid video]
    C -- No --> D[Ignore File]
    C -- Yes --> E[Wait for file copy size to stabilize]
    E --> F[Add Job to SQLite 'jobs' Table status='queued']
    F --> G[Publish JOB_ADDED Event]
```

---

## ⚙️ 2. Transcode Pipeline Execution

```mermaid
flowchart TD
    A[Queue Scheduler Worker Thread] --> B[Poll DB for oldest 'queued' job]
    B --> C{Job Found?}
    C -- No --> D[Sleep 1.0s / Wait]
    C -- Yes --> E[Set Job status='analyzing']
    E --> F[Compute SHA256 Hash]
    F --> G{SHA256 in Completed History?}
    G -- Yes --> H[Bypass Transcoding / Move Original to Originals/ / Set status='duplicate']
    G -- No --> I[Query file properties via FFprobe]
    I --> J{Check GPU Acceleration Support}
    J -- CUDA --> K[Compile command with -hwaccel cuda]
    J -- CPU --> L[Compile command standard CPU]
    K --> M[Execute FFmpeg pipe progress telemetry]
    L --> M
    M --> N{Conversion Success?}
    N -- Yes --> O[Preserve Timestamp / Move original to Originals/ / Move output to clips/]
    N -- No --> P[Graceful Fallback to CPU/Retry / If failed twice set status='failed']
    O --> Q[Write Entry to History / Set status='completed']
```

---

## 💬 3. Inter-Process Communication (IPC) Socket Flow

```mermaid
flowchart LR
    A[GUI Dashboard / CLI Client] --> B[Connect to Unix Domain Socket]
    B --> C[Send JSON Request command: status]
    C --> D[IPC Server Daemon Thread]
    D --> E[Query SQLite DB for Jobs & Telemetry]
    E --> F[Form JSON Response payload]
    F --> G[Transmit back to Client over UDS]
```
