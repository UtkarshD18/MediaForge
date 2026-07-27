-- Alter jobs table constraints and add reason column
CREATE TABLE IF NOT EXISTS jobs_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filepath TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    profile_name TEXT NOT NULL,
    status TEXT CHECK(status IN ('queued', 'analyzing', 'converting', 'post_processing', 'moving', 'completed', 'failed', 'duplicate', 'cancelled')) DEFAULT 'queued',
    progress REAL DEFAULT 0.0,
    eta_seconds REAL DEFAULT 0.0,
    error_message TEXT,
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

INSERT INTO jobs_new (id, filepath, sha256, profile_name, status, progress, eta_seconds, error_message, created_at, started_at, completed_at)
SELECT id, filepath, sha256, profile_name, status, progress, eta_seconds, error_message, created_at, started_at, completed_at FROM jobs;

DROP TABLE jobs;
ALTER TABLE jobs_new RENAME TO jobs;

-- Alter history table constraints and add reason column
CREATE TABLE IF NOT EXISTS history_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER,
    original_name TEXT NOT NULL,
    original_path TEXT NOT NULL,
    converted_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    original_size INTEGER NOT NULL,
    converted_size INTEGER NOT NULL,
    duration REAL NOT NULL,
    conversion_time_seconds REAL NOT NULL,
    avg_speed REAL NOT NULL,
    status TEXT CHECK(status IN ('completed', 'failed', 'duplicate', 'cancelled')) NOT NULL,
    reason TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO history_new (id, job_id, original_name, original_path, converted_path, sha256, original_size, converted_size, duration, conversion_time_seconds, avg_speed, status, timestamp)
SELECT id, job_id, original_name, original_path, converted_path, sha256, original_size, converted_size, duration, conversion_time_seconds, avg_speed, status, timestamp FROM history;

DROP TABLE history;
ALTER TABLE history_new RENAME TO history;
