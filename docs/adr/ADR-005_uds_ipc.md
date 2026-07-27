# ADR-005: Unix Domain Socket IPC

## Context and Problem Statement
MediaForge splits user interaction from background processing by running a systemd daemon and a desktop tray GUI client. The GUI dashboard and CLI router need a fast, low-overhead inter-process communication (IPC) channel to query active queues, list stats, and toggle daemon state triggers.

## Decision
We chose **UNIX Domain Sockets (UDS)** as our primary IPC protocol.

## Status
Approved

## Consequences
* **Pros**:
  * High Performance: UDS communicates entirely inside system kernel space, bypassing network stack overhead (such as TCP handshakes, routing loops, and loopback socket translation), yielding sub-millisecond latencies.
  * Local Security: Access is restricted naturally using filesystem permissions on the socket file (`mediaforge.sock`), blocking unauthorized network users or external network nodes from querying states.
  * Portability: Simple JSON payload encoding over standard socket connections requires no complex RPC compilation tools (e.g. Protocol Buffers / gRPC).
* **Cons**:
  * Not Networkable: UDS is restricted to communications on the local host machine. Remote worker capabilities ( NAS ingestion / distributed encoding) require migration to TCP interfaces (planned for V2.0).
