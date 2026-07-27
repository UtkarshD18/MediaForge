# ADR-001: SQLite over PostgreSQL or Raw JSON

## Context and Problem Statement
MediaForge requires a persistent data store to keep ingestion queue states, transcode run history logs, metadata caches, and UI configurations. We need a system that ensures ACID guarantees, handles concurrent read operations from the UI while writing from background workers, and has zero external server installation requirements for desktop usability.

## Decision
We chose **SQLite** as our local relational database storage engine.

## Status
Approved

## Consequences
* **Pros**:
  * Zero-configuration installation: SQLite reads and writes to a single local file (`mediaforge.db`), requiring no local port bindings or systemd database service administration.
  * Thread Safety: Safe concurrent reading is unlocked by using Write-Ahead Logging (`PRAGMA journal_mode=WAL`), allowing the GUI to query statistics without blocking active background transcode writes.
  * Transactional Rigidity: Complete ACID transactions guarantee that database corruption does not occur during system power loss or daemon termination mid-conversion.
* **Cons**:
  * Relational constraints: Altering table structures or checking constraints requires SQL schema copy-recreation patterns (which we manage using a migrations scanner in `db.py`).
