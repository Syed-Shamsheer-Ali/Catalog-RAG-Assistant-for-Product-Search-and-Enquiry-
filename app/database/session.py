from __future__ import annotations

from pathlib import Path
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import DATABASE_URL
from app.models.entities import Base


def make_engine(database_url: str = DATABASE_URL) -> Engine:
    if database_url.startswith("sqlite:"):
        raw_path = database_url.removeprefix("sqlite:///")
        if raw_path != ":memory:":
            path = Path(raw_path)
            if not path.is_absolute():
                path = Path.cwd() / path
            path.parent.mkdir(parents=True, exist_ok=True)
        return create_engine(database_url, connect_args={"check_same_thread": False})
    return create_engine(database_url)


def create_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=engine or make_engine(), expire_on_commit=False)


def initialize_database(engine: Engine | None = None) -> Engine:
    db_engine = engine or make_engine()
    Base.metadata.create_all(db_engine)
    return db_engine


@contextmanager
def session_scope(factory: sessionmaker[Session] | None = None) -> Iterator[Session]:
    session = (factory or create_session_factory())()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
