CREATE TABLE IF NOT EXISTS metadata (
    sha256 TEXT PRIMARY KEY,
    filepath TEXT NOT NULL,
    codec TEXT NOT NULL,
    width INTEGER,
    height INTEGER,
    fps REAL,
    duration REAL,
    rotation INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filepath TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    profile_name TEXT NOT NULL,
    status TEXT CHECK(status IN ('queued', 'analyzing', 'converting', 'post_processing', 'moving', 'completed', 'failed')) DEFAULT 'queued',
    progress REAL DEFAULT 0.0,
    eta_seconds REAL DEFAULT 0.0,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS history (
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
    status TEXT CHECK(status IN ('completed', 'failed')) NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
