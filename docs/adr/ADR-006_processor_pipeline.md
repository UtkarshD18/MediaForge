# ADR-006: Processor Pipeline

## Context and Problem Statement
When video ingestion happens, the target file undergoes multiple progressive states: file monitoring (transfer stabilization), hash calculation (duplicate verification), metadata parsing (ffprobe characteristics extraction), core conversion (ffmpeg transcoding), filesystem relocation, and post-processing (thumbnail generation, notifications). 

## Decision
We chose to organize this sequence as a **unified pipeline executor** executing inside a single blocking flow under the queue thread scheduler.

## Status
Approved

## Consequences
* **Pros**:
  * Simple Error Tracking: If any stage of the pipeline fails (e.g. invalid file format or full disk space), the execution raises an error, unrolls partial files, and flags the database row status to `failed` with clear debug details.
  * Atomic Transitions: Intermediate file moves and name changes occur inside a final stage, ensuring that files do not appear partially rendered inside target editing directories.
* **Cons**:
  * Blocks Queue Thread: The pipeline execution blocks the scheduling thread. However, since the GUI runs UDS requests in auxiliary threads, the interface remains active and responsive.
