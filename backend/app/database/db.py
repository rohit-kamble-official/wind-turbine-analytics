"""Engine / session management."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models.models import Base

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def _sqlite_pragmas(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.close()


def make_engine(url: str) -> Engine:
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    eng = create_engine(url, future=True, **kwargs)
    if url.startswith("sqlite"):
        event.listen(eng, "connect", _sqlite_pragmas)
    return eng


def configure(url: str | None = None) -> Engine:
    """(Re)configure the global engine - used by tests to point at a temp DB."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = make_engine(url or settings.database_url)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        configure()
    return _engine


def get_sessionmaker() -> sessionmaker:
    if _SessionLocal is None:
        configure()
    return _SessionLocal


def init_db(drop: bool = False) -> None:
    eng = get_engine()
    if drop:
        Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.close()
