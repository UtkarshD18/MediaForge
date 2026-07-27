# Logging Specification - MediaForge

This document outlines the structured logging framework, log rotation policy, and JSON parsing layouts implemented in **MediaForge**.

---

## 🗂️ Log Directory Structure

All engine operations write to rolling files located inside:

```text
mediaforge/logs/
├── 2026-07-26.log
├── 2026-07-27.log
└── ...
```

Logs are divided into daily files formatted as `YYYY-MM-DD.log`. Rotation runs automatically: when the calendar day changes, the logger writes to a new log descriptor.

---

## 📝 Structured JSON Schema

Every log entry is written as a single line of structured JSON (except console logs which are formatted for readability), making it easy to parse via aggregators (like ELK, Loki, or jq).

### JSON Log Keys

```json
{
  "time": "2026-07-27T09:29:58.123456Z",
  "level": "INFO",
  "module": "executor",
  "message": "Starting pipeline for job 1: test_input.mp4"
}
```

* **`time`**: ISO-8601 UTC timestamp.
* **`level`**: Logging severity (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`).
* **`module`**: The module origin (e.g. `watcher`, `scheduler`, `executor`, `ipc`).
* **`message`**: Readable execution descriptions.

---

## 🔍 Parsing Log Files via CLI

### Read today's logs using `jq`
To filter and render today's logs in colorized human-readable formats:

```bash
cat logs/$(date +%Y-%m-%d).log | jq -r '"[\(.time[11:19])] \(.level) [\(.module)] - \(.message)"'
```

### Find Errors only
To fetch warning or error logs:

```bash
grep -E '"level":"(WARNING|ERROR|CRITICAL)"' logs/*.log
```

---

## 🖥️ Console Output Formatting

When running the daemon interactively (e.g., `mediaforge watch` directly in terminal), standard output (stdout) is formatted for desktop users:

```text
[09:29:58] INFO    executor - Starting pipeline for job 1: test_input.mp4
[09:30:02] INFO    executor - Ingest completed for job 1 in 4.54s
```
This is achieved by `ConsoleFormatter` matching system console parameters.
