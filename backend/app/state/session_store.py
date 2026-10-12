"""Conversation state: where sessions live between messages and across restarts.

`SessionStore` is the interface the pipeline uses. Two implementations:
- InMemorySessionStore: a dict; used by tests, lost on restart.
- SqliteSessionStore: a local SQLite file; survives restarts. Swapping in Postgres means writing a
  third class, without touching the pipeline.

A session's history holds the patient's own words, which is health data: sessions untouched for
`session_retention_days` are deleted.
"""
import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Protocol, Tuple

QuestionId = Tuple[str, int]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Session:
    session_id: str
    language: str = "fr"
    urgency_level: int = 1
    symptoms: List[str] = field(default_factory=list)
    history: List[Dict[str, str]] = field(default_factory=list)
    asked_questions: List[QuestionId] = field(default_factory=list)
    started_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


class SessionStore(Protocol):
    def create(self, language: str) -> Session: ...

    def get(self, session_id: str) -> Optional[Session]: ...

    def save(self, session: Session) -> None: ...

    def delete_expired(self) -> int:
        """Delete sessions past the retention period; returns how many were deleted."""
        ...


class InMemorySessionStore:
    def __init__(self, retention_days: Optional[float] = None, clock: Callable[[], datetime] = utc_now):
        self._sessions: Dict[str, Session] = {}
        self._lock = threading.Lock()
        self.retention = timedelta(days=retention_days) if retention_days else None
        self.clock = clock

    def create(self, language: str) -> Session:
        now = self.clock()
        session = Session(str(uuid.uuid4()), language=language, started_at=now, updated_at=now)
        self.save(session)
        return session

    def get(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    def save(self, session: Session) -> None:
        session.updated_at = self.clock()
        with self._lock:
            self._sessions[session.session_id] = session

    def delete_expired(self) -> int:
        if not self.retention:
            return 0
        cutoff = self.clock() - self.retention
        with self._lock:
            expired = [sid for sid, s in self._sessions.items() if s.updated_at < cutoff]
            for sid in expired:
                del self._sessions[sid]
        return len(expired)


# Each entry upgrades the database by one version. Never edit a released entry: append a new one.
MIGRATIONS = [
    """
    CREATE TABLE sessions (
        session_id      TEXT PRIMARY KEY,
        language        TEXT NOT NULL,
        urgency_level   INTEGER NOT NULL,
        symptoms        TEXT NOT NULL,   -- JSON list
        history         TEXT NOT NULL,   -- JSON list of {role, content}: contains patient text
        asked_questions TEXT NOT NULL,   -- JSON list of [category, index]
        started_at      TEXT NOT NULL,   -- ISO 8601, UTC
        updated_at      TEXT NOT NULL
    );
    CREATE INDEX sessions_updated_at ON sessions (updated_at);
    """,
]


class SqliteSessionStore:
    """Sessions in a SQLite file. One connection shared under a lock: SQLite serialises writes anyway,
    and this backend runs as a single process. A multi-process deployment would use Postgres."""

    def __init__(self, path: Path, retention_days: float, purge_every_seconds: float = 3600,
                 clock: Callable[[], datetime] = utc_now):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.retention = timedelta(days=retention_days)
        self.purge_every = purge_every_seconds
        self.clock = clock
        self._last_purge = 0.0
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode = WAL")  # readers don't block the writer
        self._migrate()

    def _migrate(self) -> None:
        version = self._db.execute("PRAGMA user_version").fetchone()[0]
        for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
            with self._db:  # one transaction per migration
                self._db.executescript(script)
                self._db.execute(f"PRAGMA user_version = {number}")

    @property
    def schema_version(self) -> int:
        return self._db.execute("PRAGMA user_version").fetchone()[0]

    def create(self, language: str) -> Session:
        now = self.clock()
        session = Session(str(uuid.uuid4()), language=language, started_at=now, updated_at=now)
        self.save(session)
        return session

    def get(self, session_id: str) -> Optional[Session]:
        with self._lock:
            row = self._db.execute(
                "SELECT session_id, language, urgency_level, symptoms, history, asked_questions, started_at,"
                " updated_at FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        if row is None:
            return None
        sid, language, urgency, symptoms, history, asked, started, updated = row
        return Session(sid, language, urgency, json.loads(symptoms), json.loads(history),
                       [tuple(q) for q in json.loads(asked)],
                       datetime.fromisoformat(started), datetime.fromisoformat(updated))

    def save(self, session: Session) -> None:
        session.updated_at = self.clock()
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(session_id) DO UPDATE SET"
                " language = excluded.language, urgency_level = excluded.urgency_level,"
                " symptoms = excluded.symptoms, history = excluded.history,"
                " asked_questions = excluded.asked_questions, updated_at = excluded.updated_at",
                (session.session_id, session.language, session.urgency_level, json.dumps(session.symptoms),
                 json.dumps(session.history, ensure_ascii=False), json.dumps(session.asked_questions),
                 session.started_at.isoformat(), session.updated_at.isoformat()))
        if time.monotonic() - self._last_purge > self.purge_every:
            self.delete_expired()

    def delete_expired(self) -> int:
        self._last_purge = time.monotonic()
        cutoff = (self.clock() - self.retention).isoformat()
        with self._lock, self._db:
            return self._db.execute("DELETE FROM sessions WHERE updated_at < ?", (cutoff,)).rowcount

    def close(self) -> None:
        self._db.close()
