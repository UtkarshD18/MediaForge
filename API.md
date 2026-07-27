# Inter-Process Communication (IPC) Protocol - MediaForge

This document specifies the inter-process communication JSON schemas and routing commands available over the Unix Domain Socket (`mediaforge.sock`).

---

## 💬 Communication Channel

* **Socket Location**: `/home/shadow/.gemini/antigravity-ide/scratch/mediaforge/mediaforge.sock`
* **Transport**: Local Unix Domain Socket (UDS)
* **Payload Encoding**: UTF-8 encoded JSON strings terminated by a newline (`\n`).

---

## 📋 Client Command Routes

### 1. `status`
Requests active transcoding statuses and queue metrics from the running daemon.

#### Request Schema
```json
{
  "command": "status"
}
```

#### Response Schema
```json
{
  "status": "ok",
  "active_job": {
    "job_id": 12,
    "filename": "test_clip.mp4",
    "progress": 45.5,
    "eta_seconds": 12.4
  },
  "queue_size": 2,
  "scheduler_paused": false
}
```

### 2. `pause` / `resume`
Toggles active scheduler queue worker loop checks.

#### Request Schema
```json
{
  "command": "pause"
}
```

#### Response Schema
```json
{
  "status": "ok",
  "message": "Scheduler execution paused successfully."
}
```

### 3. `cancel`
Interrupts and stops the current transcoding process execution, restoring intermediate file structures.

#### Request Schema
```json
{
  "command": "cancel"
}
```

#### Response Schema
```json
{
  "status": "ok",
  "message": "Active job cancelled successfully."
}
```
If no job is running, returns a status indicator with message `No active transcoding job found to cancel`.
