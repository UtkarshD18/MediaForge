import threading
from collections.abc import Callable
from typing import Any


class EventBus:
    """
    Thread-safe event dispatcher that decouples module-to-module communication.
    """

    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable[[Any], None]]] = {}
        self._lock = threading.Lock()

    def subscribe(self, event_type: str, callback: Callable[[Any], None]) -> None:
        """
        Register a callback for an event type.
        """
        with self._lock:
            if event_type not in self._listeners:
                self._listeners[event_type] = []
            self._listeners[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable[[Any], None]) -> None:
        """
        Unsubscribe a callback from an event type.
        """
        with self._lock:
            if event_type in self._listeners:
                try:
                    self._listeners[event_type].remove(callback)
                except ValueError:
                    pass

    def publish(self, event_type: str, data: Any = None) -> None:
        """
        Publish an event to all subscribers. Callbacks are executed in the publisher's thread.
        """
        callbacks = []
        with self._lock:
            if event_type in self._listeners:
                callbacks = list(self._listeners[event_type])

        for callback in callbacks:
            try:
                callback(data)
            except Exception as e:
                # Avoid circular logging imports in event publishing; prints to stderr
                import sys

                print(f"Error executing callback for event '{event_type}': {e}", file=sys.stderr)


# Global singleton
_bus = EventBus()


def get_event_bus() -> EventBus:
    """
    Access the application-wide global EventBus.
    """
    return _bus


# Event Types Constants
class Events:
    JOB_ADDED = "JOB_ADDED"
    JOB_STARTED = "JOB_STARTED"
    JOB_PROGRESS = "JOB_PROGRESS"
    JOB_FINISHED = "JOB_FINISHED"
    JOB_FAILED = "JOB_FAILED"
    QUEUE_UPDATED = "QUEUE_UPDATED"
    DAEMON_STOPPED = "DAEMON_STOPPED"
    SETTINGS_CHANGED = "SETTINGS_CHANGED"
