import sqlite3
from datetime import datetime, timezone

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS known_people (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    photo_path TEXT NOT NULL,
    added_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    status TEXT NOT NULL,
    person_name TEXT,
    image_path TEXT NOT NULL,
    emailed INTEGER NOT NULL DEFAULT 0
);
"""


def connect():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    # Multiple camera threads (monitor.py) can now log a detection at
    # nearly the same instant - without this, one of them hitting SQLite's
    # write lock would raise "database is locked" immediately instead of
    # briefly waiting its turn.
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db():
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
        _migrate(conn)
    finally:
        conn.close()


def _migrate(conn):
    """Adds columns to a pre-existing detections table from before
    multi-camera support - CREATE TABLE IF NOT EXISTS above doesn't touch
    a table that already exists."""
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(detections)")}
    if "camera" not in cols:
        conn.execute("ALTER TABLE detections ADD COLUMN camera TEXT")
        conn.commit()


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_setting(key, default=None):
    conn = connect()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def set_setting(key, value):
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


def list_known_people():
    conn = connect()
    try:
        return conn.execute("SELECT * FROM known_people ORDER BY name").fetchall()
    finally:
        conn.close()


def add_known_person(name, photo_path):
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO known_people (name, photo_path, added_at) VALUES (?, ?, ?)",
            (name, photo_path, now_iso()),
        )
        conn.commit()
    finally:
        conn.close()


def delete_known_person(person_id):
    conn = connect()
    try:
        conn.execute("DELETE FROM known_people WHERE id = ?", (person_id,))
        conn.commit()
    finally:
        conn.close()


def log_detection(status, person_name, image_path, emailed, camera=None):
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO detections (ts, status, person_name, image_path, emailed, camera) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (now_iso(), status, person_name, image_path, int(emailed), camera),
        )
        conn.commit()
    finally:
        conn.close()


def recent_detections(limit=100):
    conn = connect()
    try:
        return conn.execute(
            "SELECT * FROM detections ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        conn.close()


def clear_detections():
    """Deletes every detection row and returns their image_paths, so the
    caller can also remove the now-orphaned snapshot files."""
    conn = connect()
    try:
        paths = [row["image_path"] for row in conn.execute("SELECT image_path FROM detections")]
        conn.execute("DELETE FROM detections")
        conn.commit()
        return paths
    finally:
        conn.close()
