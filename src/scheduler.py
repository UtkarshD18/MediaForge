import threading
import time

from src.db import DatabaseManager
from src.events import Events, get_event_bus
from src.executor import PipelineExecutor
from src.logger import get_logger


class QueueScheduler(threading.Thread):
    """
    Background worker thread polling SQLite jobs and dispatching them sequentially
    to the PipelineExecutor. Supports pausing/resuming.
    """
    def __init__(self, db: DatabaseManager, executor: PipelineExecutor) -> None:
        super().__init__()
        self.db = db
        self.executor = executor
        self.logger = get_logger()
        self.bus = get_event_bus()
        self.daemon = True
        self._stop_event = threading.Event()

    def stop(self) -> None:
        """
        Signals the scheduler loop to shut down.
        """
        self._stop_event.set()

    def is_paused(self) -> bool:
        """
        Check if the queue execution is paused.
        """
        return self.db.get_setting("queue_paused", "false") == "true"

    def pause_queue(self) -> None:
        """
        Persists the paused state and publishes the update.
        """
        self.db.set_setting("queue_paused", "true")
        self.logger.info("Scheduler execution queue has been PAUSED.")
        self.bus.publish(Events.QUEUE_UPDATED)

    def resume_queue(self) -> None:
        """
        Resumes scheduler queue processing and publishes the update.
        """
        self.db.set_setting("queue_paused", "false")
        self.logger.info("Scheduler execution queue has been RESUMED.")
        self.bus.publish(Events.QUEUE_UPDATED)

    def run(self) -> None:
        """
        Main execution loop. Polling SQLite for next job.
        """
        self.logger.info("Queue Scheduler thread started.")
        
        # Reset stuck jobs on start (e.g. from crash or abrupt process kill)
        self.db.reset_stuck_jobs()
        self.bus.publish(Events.QUEUE_UPDATED)

        while not self._stop_event.is_set():
            try:
                # 1. If queue is paused, wait
                if self.is_paused():
                    time.sleep(1.0)
                    continue

                # 2. Check if a pipeline is already executing
                active = self.db.get_active_job()
                if active:
                    # Let it run; sleep and check later
                    time.sleep(0.5)
                    continue

                # 3. Pull next FIFO queued job
                next_job = self.db.get_next_queued_job()
                if next_job:
                    job_id = next_job["id"]
                    self.logger.info(f"Scheduler picked up job {job_id} from queue.")
                    self.bus.publish(Events.QUEUE_UPDATED)
                    
                    # Blocking call executing the pipeline stages
                    success = self.executor.run_pipeline(job_id)
                    
                    self.logger.info(f"Scheduler finished job {job_id}. Success={success}")
                    self.bus.publish(Events.QUEUE_UPDATED)
                else:
                    # Queue is empty, sleep briefly
                    time.sleep(0.5)

            except Exception as e:
                self.logger.error(f"Error in Scheduler loop: {e}")
                time.sleep(2.0)

        self.logger.info("Queue Scheduler thread terminated.")
