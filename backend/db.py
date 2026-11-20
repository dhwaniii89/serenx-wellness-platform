"""SQLite helpers. A new connection per call keeps things thread-safe."""
import os
import sqlite3
from datetime import datetime


_RESOLVED: str | None = None


def _writable(path: str) -> bool:
    try:
        c = sqlite3.connect(path, timeout=5)
        c.execute("CREATE TABLE IF NOT EXISTS _probe (x INTEGER)")
        c.execute("INSERT INTO _probe VALUES (1)")
        c.execute("DELETE FROM _probe")
        c.commit()
        c.close()
        return True
    except sqlite3.Error:
        return False


def db_path() -> str:
    """DB_PATH if set. Otherwise wellness.db in the project folder, unless that place is not writable
    or is synced by OneDrive (which can lock SQLite files); then a local app folder is used instead."""
    global _RESOLVED
    env = os.getenv("DB_PATH")
    if env:
        return env
    if _RESOLVED:
        return _RESOLVED
    here = os.path.abspath("wellness.db")
    if "onedrive" not in here.lower() and _writable(here):
        _RESOLVED = here
    else:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        folder = os.path.join(base, "SERENX")
        os.makedirs(folder, exist_ok=True)
        _RESOLVED = os.path.join(folder, "wellness.db")
    return _RESOLVED


def conn() -> sqlite3.Connection:
    c = sqlite3.connect(db_path(), timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


def q(sql: str, args: tuple = ()) -> list[dict]:
    c = conn()
    try:
        return [dict(r) for r in c.execute(sql, args).fetchall()]
    finally:
        c.close()


def ex(sql: str, args: tuple = ()) -> int:
    c = conn()
    try:
        cur = c.execute(sql, args)
        c.commit()
        return cur.lastrowid
    finally:
        c.close()


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL CHECK (role IN ('doctor','patient')),
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    pw_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    specialization TEXT DEFAULT '',
    bio TEXT DEFAULT '',
    age INTEGER,
    doctor_id INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id INTEGER NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    text TEXT NOT NULL,
    qtype TEXT NOT NULL CHECK (qtype IN ('multiple_choice','rating','text')),
    options TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS a_assign (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id INTEGER NOT NULL REFERENCES assessments(id),
    patient_id INTEGER NOT NULL REFERENCES users(id),
    frequency TEXT NOT NULL CHECK (frequency IN ('once','daily','weekly','monthly')),
    start_date TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS a_sub (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assign_id INTEGER NOT NULL REFERENCES a_assign(id),
    due_date TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    answers TEXT NOT NULL,
    summary TEXT DEFAULT '',
    flagged INTEGER DEFAULT 0,
    reviewed INTEGER DEFAULT 0,
    UNIQUE (assign_id, due_date)
);

CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS g_assign (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id INTEGER NOT NULL REFERENCES goals(id),
    patient_id INTEGER NOT NULL REFERENCES users(id),
    frequency TEXT NOT NULL CHECK (frequency IN ('once','daily','weekly','monthly')),
    start_date TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS g_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assign_id INTEGER NOT NULL REFERENCES g_assign(id),
    due_date TEXT NOT NULL,
    progress INTEGER DEFAULT 0,
    completed INTEGER DEFAULT 0,
    notes TEXT DEFAULT '',
    updated_at TEXT NOT NULL,
    UNIQUE (assign_id, due_date)
);

CREATE TABLE IF NOT EXISTS mood_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    day TEXT NOT NULL,
    mood INTEGER NOT NULL CHECK (mood BETWEEN 1 AND 5),
    note TEXT DEFAULT '',
    updated_at TEXT NOT NULL,
    UNIQUE (user_id, day)
);

CREATE TABLE IF NOT EXISTS journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    text TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'typed',
    reflection TEXT DEFAULT '',
    flagged INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS chat_msgs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    role TEXT NOT NULL CHECK (role IN ('user','assistant')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def init_db() -> None:
    c = conn()
    try:
        c.executescript(SCHEMA)
        c.commit()
    finally:
        c.close()
