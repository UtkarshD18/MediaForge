import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


class JsonFormatter(logging.Formatter):
    """
    Format log entries as JSON structures for simple analytic ingestion.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "module": record.module,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Include extra payload if present
        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):  # type: ignore
            log_data.update(record.extra_data)  # type: ignore

        return json.dumps(log_data)


class DailyFileHandler(logging.Handler):
    """
    Custom logging handler that dynamically creates/shifts file descriptors
    to log into logs/YYYY-MM-DD.log. Extremely robust against sleep/resume cycles.
    """

    def __init__(self, log_dir: Path):
        super().__init__()
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.current_date = ""
        self._file_handler: logging.FileHandler | None = None

    def _get_handler(self) -> logging.FileHandler:
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self.current_date:
            if self._file_handler:
                self._file_handler.close()
            self.current_date = today
            log_file = self.log_dir / f"{today}.log"
            self._file_handler = logging.FileHandler(log_file, encoding="utf-8")
            self._file_handler.setFormatter(self.formatter)
        assert self._file_handler is not None
        return self._file_handler

    def emit(self, record: logging.LogRecord) -> None:
        try:
            handler = self._get_handler()
            handler.emit(record)
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        if self._file_handler:
            self._file_handler.close()
        super().close()


def setup_logger(log_dir: Path, level_str: str = "INFO") -> logging.Logger:
    """
    Initialize system logger writing JSON to daily logs, and color-coded plaintext to stdout.
    """
    logger = logging.getLogger("mediaforge")
    logger.handlers.clear()

    level = getattr(logging, level_str.upper(), logging.INFO)
    logger.setLevel(level)

    # 1. Daily File Handler (JSON)
    file_handler = DailyFileHandler(log_dir)
    file_handler.setFormatter(JsonFormatter())
    file_handler.setLevel(level)
    logger.addHandler(file_handler)

    # 2. Console Handler (Plain Text Reader-friendly)
    console_handler = logging.StreamHandler(sys.stdout)

    class ConsoleFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            time_str = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
            return f"[{time_str}] {record.levelname:<7} {record.module}:{record.lineno} - {record.getMessage()}"

    console_handler.setFormatter(ConsoleFormatter())
    console_handler.setLevel(level)
    logger.addHandler(console_handler)

    return logger


def get_logger() -> logging.Logger:
    """
    Retrieve the configured logger.
    """
    return logging.getLogger("mediaforge")
