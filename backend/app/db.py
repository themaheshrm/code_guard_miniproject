from __future__ import annotations

import datetime as dt
import logging
import uuid
from pathlib import Path
from typing import Iterator

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import get_settings

logger = logging.getLogger("codeguard.db")


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _uid() -> str:
    return uuid.uuid4().hex


def as_utc(d: dt.datetime | None) -> dt.datetime | None:
    """SQLite drops tzinfo; values are always written in UTC, so re-attach it before serialising."""
    if d is None:
        return None
    return d.replace(tzinfo=dt.timezone.utc) if d.tzinfo is None else d


class Base(DeclarativeBase):
    pass


class Analysis(Base):
    __tablename__ = "analyses"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    mode: Mapped[str] = mapped_column(String(16))          # single | batch
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued | running | done | failed
    n_files: Mapped[int] = mapped_column(default=0)
    persist: Mapped[bool] = mapped_column(Boolean, default=False)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # compact stats for lists/dashboard
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Submission(Base):
    """Stored ONLY when the user opts in (persist=true). Used as the reference corpus for later comparisons."""
    __tablename__ = "submissions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    name: Mapped[str] = mapped_column(String(255))
    language: Mapped[str] = mapped_column(String(16))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    code: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[dict] = mapped_column(JSON)


# Columns added after the first release. create_all() never alters existing tables, so add them in place.
_ADDED_COLUMNS = {"analyses": {"title": "VARCHAR(200)", "summary": "JSON", "finished_at": "DATETIME"}}

_engine = None
_Session: sessionmaker | None = None


def _migrate(engine) -> None:
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, cols in _ADDED_COLUMNS.items():
            if not insp.has_table(table):
                continue
            have = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in cols.items():
                if name not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                    logger.info("DB migration: added %s.%s", table, name)


def init_db(url: str | None = None) -> None:
    global _engine, _Session
    url = url or get_settings().database_url
    kwargs: dict = {}
    is_sqlite = url.startswith("sqlite")
    memory = ":memory:" in url
    if is_sqlite:
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    if url.startswith("sqlite:///") and not memory:
        Path(url.replace("sqlite:///", "", 1)).parent.mkdir(parents=True, exist_ok=True)
    if memory:
        kwargs["poolclass"] = StaticPool
    if _engine is not None:
        _engine.dispose()
    _engine = create_engine(url, **kwargs)
    if is_sqlite:
        @event.listens_for(_engine, "connect")
        def _on_sqlite_connect(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
            dbapi_conn.execute("PRAGMA busy_timeout=30000")
            if not memory:
                dbapi_conn.execute("PRAGMA journal_mode=WAL")
    Base.metadata.create_all(_engine)
    _migrate(_engine)
    _Session = sessionmaker(_engine, expire_on_commit=False)


def session() -> Session:
    if _Session is None:
        init_db()
    return _Session()  # type: ignore[misc]


def get_session() -> Iterator[Session]:
    s = session()
    try:
        yield s
    finally:
        s.close()
