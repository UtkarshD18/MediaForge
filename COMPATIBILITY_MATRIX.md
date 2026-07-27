# NLE Compatibility Matrix - MediaForge

This document captures the verified compatibility of MediaForge's transcode outputs across major Linux Non-Linear Editors (NLEs) and players.

---

## 🎞️ Compatibility Grid

| Editor | Profile | Target Codec | Import Status | Playback | Audio Sync | Frame Accuracy | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **DaVinci Resolve (Linux)** | `youtube` | ProRes 422 HQ (`mov`) | 🟢 Success | Smooth | 🟢 Sync | 🟢 Accurate | Standard editing codec; flawless scrubbing |
| **DaVinci Resolve (Linux)** | `proxy` | ProRes Proxy (`mov`) | 🟢 Success | Smooth | 🟢 Sync | 🟢 Accurate | Ultra-low bandwidth; fast timeline response |
| **DaVinci Resolve (Linux)** | `social` | H.264 (`mp4`) | 🟢 Success | Smooth | 🟢 Sync | 🟢 Accurate | Good for final web preview clips |
| **Kdenlive** | `youtube` | ProRes 422 HQ (`mov`) | 🟢 Success | Smooth | 🟢 Sync | 🟢 Accurate | Native ffmpeg backend playback is flawless |
| **Kdenlive** | `social` | H.264 (`mp4`) | 🟢 Success | Smooth | 🟢 Sync | 🟢 Accurate | High compatibility standard |
| **Shotcut** | `youtube` | ProRes 422 HQ (`mov`) | 🟢 Success | Smooth | 🟢 Sync | 🟢 Accurate | Excellent performance |
| **VLC Media Player** | *All* | *All* | 🟢 Success | Smooth | 🟢 Sync | 🟢 Accurate | Telemetry diagnostics and sync OK |

---

## 🛠️ Verification Criteria

1. **Import successfully**: Asset registers correctly in the project bin without codec mismatch prompts.
2. **Timeline Playback**: Seamless scrubbing and rendering at native timeline frame rates without dropping frames.
3. **Audio Sync**: Perfect synchronization between the audio track (PCM/AAC) and the matching video frame stream over the entire footage length.
4. **Frame Accuracy**: The transcoded file length match matches the original to the exact frame boundaries.
5. **No Color Shift**: BT.709 color ranges are preserved without washing out gamma profiles or introducing tint shifts.
