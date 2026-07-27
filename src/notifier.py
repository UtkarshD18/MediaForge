import subprocess
from pathlib import Path
from typing import Any

from src.events import Events, get_event_bus
from src.logger import get_logger


class Notifier:
    """
    Subscribes to EventBus notifications and issues KDE desktop alerts via notify-send.
    """
    def __init__(self, notification_toggle: bool = True) -> None:
        self.enabled = notification_toggle
        self.logger = get_logger()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled

    def notify(self, title: str, message: str, urgency: str = "normal") -> None:
        """
        Executes notify-send command to display a desktop bubble.
        """
        if not self.enabled:
            return
            
        cmd = [
            "notify-send",
            "-t", "5000",
            "-u", urgency,
            title,
            message
        ]
        try:
            subprocess.run(cmd, capture_output=True, check=True)
        except Exception as e:
            self.logger.warning(f"Failed to issue desktop notification: {e}")

    def on_job_started(self, data: dict[str, Any]) -> None:
        """
        Triggered when conversion begins.
        """
        filepath = Path(data.get("filepath", "Unknown"))
        profile = data.get("profile_name", "Unknown").upper()
        self.notify(
            "🎬 Conversion Started",
            f"{filepath.name}\n↓\n{profile}"
        )

    def on_job_finished(self, data: dict[str, Any]) -> None:
        """
        Triggered when conversion finishes.
        """
        filename = data.get("original_name", "file")
        self.notify(
            "✅ Ready for Editor",
            f"{filename} ingestion completed."
        )

    def on_job_failed(self, data: dict[str, Any]) -> None:
        """
        Triggered when conversion encounters an error.
        """
        filename = data.get("original_name", "file")
        error_msg = data.get("error", "Unknown error")
        self.notify(
            "❌ Conversion Failed",
            f"Failed on {filename}:\n{error_msg}",
            urgency="critical"
        )

def setup_notifier(config: Any) -> Notifier:
    """
    Constructs the Notifier and wires its event listeners to the global event bus.
    """
    if hasattr(config, "notification_toggle"):
        feat_enabled = config.features.get("notifications", True) if hasattr(config, "features") else True
        enabled = config.notification_toggle and feat_enabled
    else:
        enabled = bool(config)

    notifier = Notifier(enabled)
    bus = get_event_bus()

    # Wire event receivers
    bus.subscribe(Events.JOB_STARTED, notifier.on_job_started)
    bus.subscribe(Events.JOB_FINISHED, notifier.on_job_finished)
    bus.subscribe(Events.JOB_FAILED, notifier.on_job_failed)
    
    # Also react to settings changing at runtime
    def on_settings_changed(config_obj: Any) -> None:
        feat_enabled = config_obj.features.get("notifications", True) if hasattr(config_obj, "features") else True
        notifier.set_enabled(config_obj.notification_toggle and feat_enabled)

    bus.subscribe(Events.SETTINGS_CHANGED, on_settings_changed)

    return notifier
