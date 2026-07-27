# ADR-002: Event Bus Architecture

## Context and Problem Statement
 Subsystems in MediaForge (such as Watcher folder listeners, Scheduler queue monitors, Pipeline Executors, and Notifier system tray alerts) must communicate state updates. Tight binding between these components (for example, direct function calls from watchdog threads to FFmpeg builders) leads to code tangles, testing complexity, and makes extending pipeline hooks difficult.

## Decision
We chose a **thread-safe Event Bus** (Observer pattern) as our central internal communication channel.

## Status
Approved

## Consequences
* **Pros**:
  * High Decoupling: Subsystems publish events (e.g. `Events.JOB_ADDED`, `Events.JOB_FINISHED`) to the global bus. Subscribers (like the system Tray Notifier or CLI outputs) process events asynchronously without the caller needing to know who handles them.
  * Thread Safety: Event registration and dispatch are protected by a `threading.RLock()` to prevent race conditions when Watchdog observer threads and main UI loops subscribe or publish concurrently.
* **Cons**:
  * Indirect Flow: It is harder to trace code flows statically since events jump between subscriber callbacks. We mitigate this by maintaining logging inside event dispatchers.
