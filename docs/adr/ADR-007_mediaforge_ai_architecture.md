# ADR-007: MediaForge AI Architecture

* **Status**: Proposed
* **Date**: 2026-07-27
* **Author**: MediaForge AI Contributors

---

## Context

We are extending **MediaForge** with **MediaForge AI**, a local AI-assisted video editing framework. This document defines the core architecture decisions required to build a scalable, modular, local-first system under strict local resource constraints (e.g., 8 GB GPU VRAM).

---

## Decisions

### 1. Timeline AST (Abstract Syntax Tree)
* **Choice**: Introduce a declarative intermediate representation (JSON schema) named **Timeline AST**.
* **Rationale**: Decouples planner logic from specific Non-Linear Editor (NLE) target formats. An intermediate AST allows simple translation to any editor schema, makes timeline diffing and suggestions patching straightforward, and provides clean serializable unit testing points.

### 2. OTIO as an Exporter Target
* **Choice**: Exporters (like `OTIOExporter`) consume the Timeline AST rather than having the LLM Planner output OTIO directly.
* **Rationale**: OpenTimelineIO (OTIO) is a rich and verbose target structure. Forcing local LLMs to generate valid OTIO models directly raises token costs, increases parsing failures, and increases syntax error rates. The LLM only needs to produce a simplified Timeline AST JSON, which is then compiled into OTIO programmatically.

### 3. Local Model Preference
* **Choice**: Zero cloud-dependencies. All models (transcription, frame analysis, planning) run locally.
* **Rationale**: Editing high-bandwidth local video files over the cloud is bottlenecked by network upload bandwidth. Running local models ensures absolute privacy of private footage, zero API paywall billing, and reliable offline operation.

### 4. Provider Plugin Architecture
* **Choice**: Abstract base provider classes (`BaseVisionModel`, `BaseSpeechModel`, `BasePlanner`) loaded dynamically via a registry system.
* **Rationale**: Avoids hardcoding specific models (e.g., Moondream, Whisper) directly in the engine. Users can configure and swap backend engines (Hugging Face `transformers` libraries, Ollama REST API endpoints, llama.cpp bindings) via `config/config.yaml`.

### 5. Memory Management Strategy (8 GB VRAM Constraint)
* **Choice**: 
  1. **Sequential Execution**: Frame extraction, VLM analysis, Whisper transcription, and LLM planning run in strict sequential pipelines, never simultaneously, to prevent VRAM allocation conflicts.
  2. **Model Offloading**: Models are loaded on-demand and fully garbage collected/purged from memory upon completion of their specific stage.
  3. **Quantizations**: Default to `float16` or `int8` model quantization profiles for VLM and Whisper (e.g., `faster-whisper`'s `int8` execution) to keep VRAM footprint under 3.5 GB.

### 6. Future Exporter Compatibility
* **Choice**: Design the `ASTExporter` interface with modular subclass mappings (e.g., `ResolveXMLExporter`, `EDLExporter`).
* **Rationale**: Decoupling the output compiler allows other formats (Final Cut Pro XML, Premiere XML, Edit Decision Lists) to be added without changing the planner or core database schemas.

### 7. Failure Recovery Strategy
* **Choice**: Job-level pipeline transaction boundaries.
* **Rationale**: If a stage fails (e.g., out-of-memory or corrupt frame file), the database logs the step status as `failed` with diagnostic logs. The pipeline recovers by clearing locks, purging allocated VRAM, and skipping the job, keeping the main daemon active.

### 8. Incremental Analysis Strategy
* **Choice**: Hash-indexed analysis caching.
* **Rationale**: Before running heavy VLM or audio models, check the `ai_clip_analysis` table for matches on the file's SHA256 hash. If found, ingestion updates are instant, saving massive processing workloads.

### 9. Caching Strategy
* **Choice**: Cache transcription segments and frame summaries directly in the SQLite schemas (`ai_transcripts`, `ai_clip_analysis`).
* **Rationale**: Centralizing cache data inside SQLite ensures ACID transactions, fast relational queries, and simplifies data deletion/pruning when a user removes a project.

### 10. Model Selection Strategy
* **Choice**: Default recommendations optimized for RTX 4060:
  * **VLM**: Moondream2 (~1.6B parameters) or LLaVA-v1.5-7b-q4.
  * **ASR**: Whisper-Base (or Whisper-Small) via `faster-whisper` library.
  * **Planner**: local Qwen2.5-Coder-7B-Instruct-Q4.

---

## Consequences

* **Benefits**: Swappable local models, resilient memory footprints (low chance of CUDA Out-Of-Memory crashes), easy support for other NLE output targets, and high-performance duplicate/cache check passes.
* **Trade-offs**: Processing speed is limited by local GPU power. Model swaps require loading time latencies.
