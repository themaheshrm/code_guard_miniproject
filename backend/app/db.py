from __future__ import annotations

import datetime as dt
import uuid
from typing import Iterator

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import get_settings


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _uid() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class Analysis(Base):
    __tablename__ = "analyses"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    mode: Mapped[str] = mapped_column(String(16))          # single | batch
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued | running | done | failed
    n_files: Mapped[int] = mapped_column(default=0)
    persist: Mapped[bool] = mapped_column(Boolean, default=False)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
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


_engine = None
_Session: sessionmaker | None = None


def init_db(url: str | None = None) -> None:
    global _engine, _Session
    url = url or get_settings().database_url
    kwargs = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    if url.startswith("sqlite:///") and ":memory:" not in url:
        from pathlib import Path
        Path(url.replace("sqlite:///", "", 1)).parent.mkdir(parents=True, exist_ok=True)
    if url.endswith(":memory:"):
        from sqlalchemy.pool import StaticPool
        kwargs["poolclass"] = StaticPool
    _engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        from sqlalchemy import event

        @event.listens_for(_engine, "connect")
        def _on_sqlite_connect(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
            dbapi_conn.execute("PRAGMA busy_timeout=30000")
            if not url.endswith(":memory:"):
                dbapi_conn.execute("PRAGMA journal_mode=WAL")
    Base.metadata.create_all(_engine)
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
