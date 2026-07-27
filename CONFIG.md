# Configuration Manual - MediaForge

This document describes the settings properties, feature flags, and profiles layout configured in `config/config.yaml`.

---

## ⚙️ Core Configuration Variables

```yaml
version: 1
incoming_folder: "~/Videos/Incoming"
originals_folder: "~/Videos/Originals"
resolve_clips_folder: "~/Videos/DaVinci/clips"
active_profile: "youtube"
overwrite_existing: false
notification_toggle: true
logging_level: "INFO"
stability_duration: 2.0
```

* **`version`** (`int`): Configuration version marker.
* **`incoming_folder`** (`str`): Absolute or home-relative path watched by watchdog. New files here are automatically queued.
* **`originals_folder`** (`str`): Target destination for archiving original files after conversion.
* **`resolve_clips_folder`** (`str`): Target destination clips folder for intermediate editing formats.
* **`active_profile`** (`str`): The name of the profile active for transcode mapping.
* **`overwrite_existing`** (`bool`): If true, skips filename collision index increments (`_001`, `_002`) and overwrites existing destination targets.
* **`notification_toggle`** (`bool`): Toggles notify-send desktop notifications.
* **`logging_level`** (`str`): Minimum logger level output (`DEBUG`, `INFO`, `WARNING`, `ERROR`).
* **`stability_duration`** (`float`): Second count checked by the file-copy observer to wait before executing transcodes.

---

## 🎨 Feature Flag Controls

```yaml
features:
  thumbnails: true
  notifications: true
  gpu_monitor: true
  resolve_integration: true
```

* **`thumbnails`** (`bool`): Enables extraction of thumbnail poster images (`.jpg`) inside `/home/shadow/Videos/DaVinci/cache/`.
* **`notifications`** (`bool`): Wires notify-send triggers.
* **`gpu_monitor`** (`bool`): Turns on NVIDIA CUDA memory and load checking using `nvidia-smi`.
* **`resolve_integration`** (`bool`): Wires DaVinci diagnostic database queries.

---

## 📋 Profile Mappings

Profile definition YAML files reside in `config/profiles/` (e.g. `youtube.yaml`, `proxy.yaml`):

```yaml
video_codec: "prores"
profile: "3"        # ProRes HQ
audio_codec: "pcm_s16le"
ext: "mov"
```

* **`video_codec`** (`str`): Video encoder passed to FFmpeg (`prores_ks`, `dnxhd`, `copy`).
* **`profile`** (`str`): Encoder profile scale (e.g. `3` for ProRes HQ, `1` for ProRes Proxy, `dnxhr_lb` for DNxHR).
* **`audio_codec`** (`str`): Audio encoder wrapper (`pcm_s16le`, `aac`, `copy`).
* **`ext`** (`str`): Target output file container extension (`mov`, `mp4`, `mkv`).
