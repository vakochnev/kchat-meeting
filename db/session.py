"""
Сессия и подключение к базе данных.
"""
import logging
from contextlib import contextmanager
from typing import Generator, Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from config import config
from .models import Base

logger = logging.getLogger(__name__)

_engine = None
_SessionLocal = None


def get_engine():
    """Возвращает engine базы данных (singleton)."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            config.database_url,
            echo=False,
            pool_pre_ping=True,
        )
        logger.info("Подключение к БД: %s", config.database_url)
    return _engine


def get_session_factory():
    """Возвращает фабрику сессий."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
        )
    return _SessionLocal


def get_session() -> Generator[Session, None, None]:
    """Генератор сессий для dependency injection."""
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def get_session_context() -> Iterator[Session]:
    """Контекстный менеджер для работы с сессией БД."""
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Инициализирует базу данных (создаёт таблицы)."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    logger.info("База данных инициализирована")
