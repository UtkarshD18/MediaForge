from pathlib import Path
from typing import Any, Optional

from watchdog.events import PatternMatchingEventHandler
from watchdog.observers import Observer

from src.config import ConfigManager
from src.db import DatabaseManager
from src.events import Events, get_event_bus
from src.logger import get_logger


class IngestionHandler(PatternMatchingEventHandler):
    """
    Listens to watchdog creation and movement events, filters paths, 
    and appends jobs to the SQLite execution queue.
    """
    def __init__(self, db: DatabaseManager, config_mgr: ConfigManager) -> None:
        super().__init__(patterns=["*"], ignore_directories=True, case_sensitive=False)
        self.db = db
        self.config_mgr = config_mgr
        self.logger = get_logger()
        self.bus = get_event_bus()

    def process_file(self, filepath_str: str) -> None:
        path = Path(filepath_str).resolve()
        
        # Ignore temp files, hidden files, or files created by mediaforge processes
        if path.name.startswith(".") or "._tmp" in path.name or "_tmp" in path.name:
            return
            
        # Verify video file extensions to avoid queueing random text/system files
        # Edit-ready video extension check
        valid_extensions = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".flv", ".m4v", ".qt"}
        if path.suffix.lower() not in valid_extensions:
            self.logger.debug(f"Ignoring file {path.name} with non-video extension {path.suffix}")
            return

        try:
            # Query if file is already active in queue (queued, converting, etc.)
            active = self.db.execute_read(
                "SELECT id FROM jobs WHERE filepath = ? AND status NOT IN ('completed', 'failed')",
                (str(path),)
            )
            if active:
                self.logger.debug(f"File {path.name} is already active in queue (Job {active[0]['id']}). Skipping duplicate.")
                return
                
            # Queue the file
            profile = self.config_mgr.config.active_profile if self.config_mgr.config else "youtube"
            job_id = self.db.add_job(str(path), "", profile)
            self.logger.info(f"Automatically queued file {path.name} for ingestion (Job ID: {job_id})")
            
            # Emit events
            self.bus.publish(Events.JOB_ADDED, {"job_id": job_id, "filepath": str(path)})
            self.bus.publish(Events.QUEUE_UPDATED)
        except Exception as e:
            self.logger.error(f"Error queueing file {path.name}: {e}")

    def on_created(self, event) -> None:
        self.process_file(event.src_path)

    def on_moved(self, event) -> None:
        self.process_file(event.dest_path)

class FileWatcher:
    """
    Wraps the watchdog Observer service, facilitating starting/stopping.
    """
    def __init__(self, db: DatabaseManager, config_mgr: ConfigManager) -> None:
        self.db = db
        self.config_mgr = config_mgr
        self.logger = get_logger()
        self.observer: Any = None
        self.handler = IngestionHandler(db, config_mgr)
        
        # Listen for config/settings changes to dynamically adjust watch directories
        get_event_bus().subscribe(Events.SETTINGS_CHANGED, self.on_settings_changed)

    def start(self) -> None:
        """
        Starts watching the Incoming directory.
        """
        watch_dir = self.config_mgr.get_resolved_path("incoming_folder")
        self.logger.info(f"Starting file watcher on: {watch_dir}")
        
        self.observer = Observer()
        self.observer.schedule(self.handler, str(watch_dir), recursive=False)
        self.observer.start()

    def stop(self) -> None:
        """
        Stops the file watcher observer thread.
        """
        if self.observer:
            self.logger.info("Stopping file watcher observer...")
            self.observer.stop()
            self.observer.join()
            self.observer = None

    def on_settings_changed(self, new_config: Any) -> None:
        """
        Hot-reloads watcher directory targets when changed in the settings.
        """
        self.logger.info("Settings change detected. Restarting file watcher directory target...")
        self.stop()
        self.start()
