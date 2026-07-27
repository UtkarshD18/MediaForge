import json
import socket
import time
import threading
import traceback
from pathlib import Path
from typing import Any

from src.db import DatabaseManager
from src.events import Events, get_event_bus
from src.logger import get_logger


class IpcServer(threading.Thread):
    """
    Local UNIX Domain Socket server running in the daemon.
    Receives JSON instructions and responds with state telemetry.
    """
    def __init__(
        self,
        socket_path: Path,
        db: DatabaseManager,
        scheduler: Any,
        executor: Any,
        config_mgr: Any
    ) -> None:
        super().__init__()
        self.socket_path = Path(socket_path).resolve()
        self.db = db
        self.scheduler = scheduler
        self.executor = executor
        self.config_mgr = config_mgr
        self.logger = get_logger()
        self.daemon = True
        self._stop_event = threading.Event()
        self.server_socket: socket.socket | None = None

    def stop(self) -> None:
        """
        Shuts down the server and cleans up the UDS file.
        """
        self._stop_event.set()
        if self.server_socket:
            try:
                # Trigger a dummy connection to break the accept() block
                self.server_socket.close()
            except Exception:
                pass
        if self.socket_path.exists():
            try:
                self.socket_path.unlink()
            except Exception:
                pass

    def run(self) -> None:
        self.logger.info(f"Starting IPC UDS server at {self.socket_path}")
        
        # Clean up stale socket files
        if self.socket_path.exists():
            try:
                self.socket_path.unlink()
            except Exception as e:
                self.logger.error(f"Failed to clear stale UDS socket file: {e}")
                return

        try:
            self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.server_socket.bind(str(self.socket_path))
            self.server_socket.listen(5)
            self.server_socket.settimeout(1.0)
        except Exception as e:
            self.logger.error(f"UDS bind failed at {self.socket_path}: {e}")
            return

        while not self._stop_event.is_set():
            try:
                conn, _ = self.server_socket.accept()
            except TimeoutError:
                continue
            except Exception:
                if self._stop_event.is_set():
                    break
                continue

            # Process client request in a helper thread or inline
            threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()

        # Final cleanup
        self.stop()
        self.logger.info("IPC UDS server thread terminated.")

    def _handle_client(self, conn: socket.socket) -> None:
        try:
            conn.settimeout(5.0)
            data = conn.recv(4096)
            if not data:
                return

            req = json.loads(data.decode("utf-8"))
            cmd = req.get("command")
            
            response = self._process_command(cmd, req)
            conn.sendall(json.dumps(response).encode("utf-8"))
        except Exception as e:
            self.logger.error(f"Error handling IPC connection: {e}\n{traceback.format_exc()}")
            try:
                err_resp = {"success": False, "error": str(e)}
                conn.sendall(json.dumps(err_resp).encode("utf-8"))
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _process_command(self, cmd: str, req: dict[str, Any]) -> dict[str, Any]:
        """
        Executes instructions and returns serialized telemetry/states.
        """
        if cmd == "status":
            active_job_row = self.db.get_active_job()
            active_job = dict(active_job_row) if active_job_row else None
            
            # Fetch jobs list
            jobs_rows = self.db.list_jobs()
            jobs_list = [dict(r) for r in jobs_rows[:15]]  # limit to top 15 for payload size
            
            # Fetch stats
            analytics = self.db.get_analytics()
            
            # Watch status
            status_str = "paused" if self.scheduler.is_paused() else "watching"
            
            return {
                "success": True,
                "status": status_str,
                "active_job": active_job,
                "jobs_list": jobs_list,
                "analytics": analytics,
                "config": {
                    "incoming_folder": self.config_mgr.config.incoming_folder if self.config_mgr.config else "",
                    "resolve_clips_folder": self.config_mgr.config.resolve_clips_folder if self.config_mgr.config else "",
                    "active_profile": self.config_mgr.config.active_profile if self.config_mgr.config else "youtube"
                }
            }

        elif cmd == "pause":
            self.scheduler.pause_queue()
            return {"success": True, "message": "Scheduler paused."}

        elif cmd == "resume":
            self.scheduler.resume_queue()
            return {"success": True, "message": "Scheduler resumed."}

        elif cmd == "cancel":
            self.executor.cancel_active_job()
            return {"success": True, "message": "Active job cancellation signal dispatched."}

        elif cmd == "reload_config":
            try:
                self.config_mgr.load()
                return {"success": True, "message": "Configuration reloaded successfully."}
            except Exception as e:
                return {"success": False, "error": f"Reload failed: {e}"}

        elif cmd == "history":
            history_rows = self.db.get_history(limit=req.get("limit", 50))
            history_list = [dict(r) for r in history_rows]
            return {"success": True, "history": history_list}

        elif cmd == "stop":
            self.logger.info("Daemon termination requested over IPC.")
            # Trigger a stop in a short delay so the socket response delivers first
            def shutdown():
                time.sleep(0.5)
                get_event_bus().publish(Events.DAEMON_STOPPED)

            threading.Thread(target=shutdown, daemon=True).start()
            return {"success": True, "message": "Daemon shutting down."}

        else:
            return {"success": False, "error": f"Unknown command: {cmd}"}

class IpcClient:
    """
    Local UNIX Domain Socket client used by the GUI dashboard and CLI commands.
    """
    def __init__(self, socket_path: Path) -> None:
        self.socket_path = Path(socket_path).resolve()

    def is_daemon_running(self) -> bool:
        """
        Quick check to verify UDS socket availability.
        """
        if not self.socket_path.exists():
            return False
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect(str(self.socket_path))
            s.close()
            return True
        except Exception:
            return False

    def send_command(self, cmd_dict: dict[str, Any], timeout: float = 3.0) -> dict[str, Any]:
        """
        Establishes connection, pushes instruction, reads response.
        """
        if not self.socket_path.exists():
            return {"success": False, "error": f"UDS socket not found at {self.socket_path}. Daemon probably offline."}
            
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect(str(self.socket_path))
            
            s.sendall(json.dumps(cmd_dict).encode("utf-8"))
            data = s.recv(65536)  # Large buffer size for stats/jobs payloads
            s.close()
            
            if not data:
                return {"success": False, "error": "No response payload received."}
                
            return json.loads(data.decode("utf-8"))
        except Exception as e:
            return {"success": False, "error": str(e)}
