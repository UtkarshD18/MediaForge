# Future Roadmap - MediaForge (V1.1 to V3.0)

This document establishes the feature staging timeline and version development gates for **MediaForge**.

---

## 🗺️ Version Milestones

### 🚀 MediaForge V1.1 - Network Storage & Metadata Enhancements (Q3 2026)
* **Goal**: Optimize for multi-user NAS/SAN environments and enrich clip metadata parsing.
* **Key Features**:
  * **Directory Poll Sync**: Auxiliary cron-like file-system scanner to catch watchdog missed events on slow network drives.
  * **EXIF and Color Primaries Extraction**: Capture BT.2020 color spaces and camera model tags during FFprobe checks, warning users of potential color space differences.
  * **JSON Metadata Exports**: Write companion `.json` sidecar files in the clips directory to allow third-party asset managers to read ingestion tags.

### 🌐 MediaForge V2.0 - Client-Server Distributed Transcoding (Q1 2027)
* **Goal**: Offload heavy transcoding workloads from local editor workstations to dedicated home/studio server nodes.
* **Key Features**:
  * **TCP RPC Socket Layer**: Expand the IPC Unix Domain Sockets interface to support network TCP socket bindings.
  * **Distributed Worker Protocol**: Allow server nodes to check out queued transcode jobs, run high-speed GPU renders, and write files back to shared storage targets.
  * **REST API Gateway**: Expose web hooks for job status updates and browser dashboard remote controls.

### 🧠 MediaForge V3.0 - AI Smart Tagging & Proxy Sync (Q4 2027)
* **Goal**: Incorporate localized AI automation pipelines directly into the ingestion stages.
* **Key Features**:
  * **Local AI Transcription (Whisper)**: Auto-generate subtitle tracks (`.srt`) and transcript metadata on ingestion completion.
  * **Smart Visual Tagging**: Run lightweight, local MobileNet/YOLO objects and face models to append tag lists inside SQLite history logs.
  * **Automatic Proxy-Original Sync Hook**: Native helper scripts tracking when original files are offlined, automating DaVinci Resolve proxy mapping.
