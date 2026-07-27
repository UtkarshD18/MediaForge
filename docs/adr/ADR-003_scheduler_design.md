# ADR-003: Scheduler Design

## Context and Problem Statement
Transcoding video files (especially ProRes HQ compression via FFmpeg NVDEC/NVENC) is a high-utilization task that consumes massive CPU/GPU resources and disk write bandwidth. Concurrent transcoding of multiple files causes extreme desktop lag, UI frame drops in NLEs, and thermal throttling.

## Decision
We chose a **sequential FIFO Queue Scheduler** running in a single worker thread.

## Status
Approved

## Consequences
* **Pros**:
  * Predictable Resource Load: Exactly one transcoding pipeline execution runs at any given time, preserving system resources for the active editing workspace.
  * FIFO Ordering: Submissions are resolved strictly in order of creation (database ID increment), avoiding random task prioritization.
  * Pause/Resume Capability: The scheduler can pause queue polling safely without interrupting the active transcoding thread.
* **Cons**:
  * No Parallel Processing: Multi-file batches do not transcode simultaneously. This is an intentional design trade-off to prioritize workstation editing responsiveness.
