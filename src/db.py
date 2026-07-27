import sqlite3
import threading
from pathlib import Path
from typing import Any


class DatabaseManager:
    """
    Manages connections and schema migration for SQLite.
    Employs thread locks to ensure safe writes from watcher, executor, and UI threads.
    """
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.initialize_schema()

    def get_connection(self) -> sqlite3.Connection:
        """
        Creates a connection with row factory enabled for dict-like query outputs.
        """
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Log for concurrent readers/writers
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def initialize_schema(self) -> None:
        """
        Scan src/migrations/*.sql and execute migrations sequentially.
        """
        with self._lock:
            with self.get_connection() as conn:
                # Create migrations table if not exists
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version INTEGER PRIMARY KEY,
                        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()

            # Find and sort migration files
            migrations_dir = Path(__file__).parent / "migrations"
            if not migrations_dir.exists():
                # Fallback to direct path resolution in tests or manual execution
                migrations_dir = Path("/home/shadow/.gemini/antigravity-ide/scratch/mediaforge/src/migrations")
                
            if not migrations_dir.exists():
                raise FileNotFoundError(f"Migrations folder missing: {migrations_dir}")

            migration_files = sorted(migrations_dir.glob("*.sql"))
            
            for m_file in migration_files:
                # Extract version prefix (e.g. 001_initial.sql -> 1)
                try:
                    version = int(m_file.stem.split("_")[0])
                except (ValueError, IndexError):
                    continue
                
                with self.get_connection() as conn:
                    row = conn.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (version,)).fetchone()
                    if row:
                        continue # Already applied
                    
                    # Apply migration
                    print(f"Applying SQLite migration {m_file.name} (version {version})...")
                    with open(m_file, "r", encoding="utf-8") as f:
                        sql_script = f.read()
                    
                    try:
                        conn.executescript(sql_script)
                        conn.execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))
                        conn.commit()
                        print(f"Successfully applied migration {m_file.name}")
                    except Exception as e:
                        conn.rollback()
                        raise RuntimeError(f"Database migration {m_file.name} failed: {e}") from e

    def execute_write(self, query: str, params: tuple[Any, ...] = ()) -> int:
        """
        Executes a write query and returns the lastrowid.
        """
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return cursor.lastrowid or 0

    def execute_read(self, query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        """
        Executes a read query and returns rows.
        """
        with self._lock, self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()

    # --- Job Helper Methods ---
    
    def add_job(self, filepath: str, sha256: str, profile_name: str) -> int:
        """
        Appends a new job to the jobs table.
        """
        return self.execute_write(
            "INSERT INTO jobs (filepath, sha256, profile_name, status) VALUES (?, ?, ?, 'queued')",
            (filepath, sha256, profile_name)
        )

    def update_job_status(self, job_id: int, status: str, error_message: str | None = None, reason: str | None = None) -> None:
        """
        Update the status of a job. If status is 'converting', sets started_at.
        If status is in ('completed', 'failed', 'duplicate', 'cancelled'), sets completed_at and progress to 100.0.
        """
        if status == "converting":
            self.execute_write(
                "UPDATE jobs SET status = ?, started_at = datetime('now') WHERE id = ?",
                (status, job_id)
            )
        elif status in ("completed", "failed", "duplicate", "cancelled"):
            self.execute_write(
                "UPDATE jobs SET status = ?, error_message = ?, reason = ?, completed_at = datetime('now'), progress = 100.0 WHERE id = ?",
                (status, error_message, reason, job_id)
            )
        else:
            self.execute_write(
                "UPDATE jobs SET status = ? WHERE id = ?",
                (status, job_id)
            )

    def update_job_progress(self, job_id: int, progress: float, eta_seconds: float) -> None:
        """
        Updates active job conversion progress and ETA values.
        """
        self.execute_write(
            "UPDATE jobs SET progress = ?, eta_seconds = ? WHERE id = ?",
            (progress, eta_seconds, job_id)
        )

    def get_next_queued_job(self) -> sqlite3.Row | None:
        """
        Retrieves the oldest queued job in FIFO order.
        """
        rows = self.execute_read(
            "SELECT * FROM jobs WHERE status = 'queued' ORDER BY id ASC LIMIT 1"
        )
        return rows[0] if rows else None

    def get_active_job(self) -> sqlite3.Row | None:
        """
        Retrieves the job that is currently executing (non-queued, non-completed, non-failed).
        """
        rows = self.execute_read(
            "SELECT * FROM jobs WHERE status IN ('analyzing', 'converting', 'post_processing', 'moving') LIMIT 1"
        )
        return rows[0] if rows else None

    def list_jobs(self) -> list[sqlite3.Row]:
        """
        Returns all jobs ordered by creation.
        """
        return self.execute_read("SELECT * FROM jobs ORDER BY id DESC")

    def reset_stuck_jobs(self) -> None:
        """
        Finds any jobs that are in an active state and resets them back to queued.
        Called on startup to clean up after crashes or abrupt shutdowns.
        """
        self.execute_write(
            "UPDATE jobs SET status = 'queued', progress = 0.0, eta_seconds = 0.0 WHERE status NOT IN ('completed', 'failed', 'duplicate', 'cancelled')"
        )

    # --- Metadata Helper Methods ---

    def cache_metadata(self, sha256: str, filepath: str, codec: str, width: int | None, height: int | None, fps: float | None, duration: float | None, rotation: int = 0) -> None:
        """
        Write analysis metadata to cache.
        """
        self.execute_write(
            "INSERT OR REPLACE INTO metadata (sha256, filepath, codec, width, height, fps, duration, rotation) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (sha256, filepath, codec, width, height, fps, duration, rotation)
        )

    def get_metadata(self, sha256: str) -> sqlite3.Row | None:
        """
        Fetch cached metadata by sha256 hash.
        """
        rows = self.execute_read("SELECT * FROM metadata WHERE sha256 = ?", (sha256,))
        return rows[0] if rows else None

    # --- History Helper Methods ---

    def add_history_record(self, job_id: int, original_name: str, original_path: str, converted_path: str, sha256: str, original_size: int, converted_size: int, duration: float, conversion_time: float, avg_speed: float, status: str, reason: str | None = None) -> None:
        """
        Appends a processed run record to history.
        """
        self.execute_write(
            """INSERT INTO history (job_id, original_name, original_path, converted_path, sha256, original_size, converted_size, duration, conversion_time_seconds, avg_speed, status, reason) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (job_id, original_name, original_path, converted_path, sha256, original_size, converted_size, duration, conversion_time, avg_speed, status, reason)
        )

    def get_history(self, limit: int = 50) -> list[sqlite3.Row]:
        """
        Gets recently processed entries.
        """
        return self.execute_read("SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,))

    def get_analytics(self) -> dict[str, Any]:
        """
        Calculates key analytics: file counts, sizes, speed averages, and computed editing time saved.
        """
        rows = self.execute_read("""
            SELECT 
                COUNT(*) as total_count,
                SUM(original_size) as total_size,
                AVG(avg_speed) as avg_speed,
                SUM(duration) as total_duration
            FROM history 
            WHERE status = 'completed'
        """)
        
        row = rows[0] if rows and rows[0]["total_count"] > 0 else None
        if not row or row["total_count"] is None:
            return {
                "total_count": 0,
                "total_size_bytes": 0,
                "avg_speed": 1.0,
                "total_duration_seconds": 0.0,
                "time_saved_seconds": 0.0
            }
        
        # Estimate "Time Saved":
        # Assume converting highly compressed video to editing codecs saves the editor
        # 2 minutes of editing/lag time per minute of footage, plus a flat 5 seconds setup.
        duration = row["total_duration"] or 0.0
        time_saved = (duration * 2.0) + (row["total_count"] * 5.0)

        return {
            "total_count": row["total_count"],
            "total_size_bytes": row["total_size"] or 0,
            "avg_speed": round(row["avg_speed"] or 1.0, 2),
            "total_duration_seconds": round(duration, 2),
            "time_saved_seconds": round(time_saved, 2)
        }

    # --- Settings Helper Methods ---
    
    def set_setting(self, key: str, value: str) -> None:
        self.execute_write("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        rows = self.execute_read("SELECT value FROM settings WHERE key = ?", (key,))
        return rows[0]["value"] if rows else default
