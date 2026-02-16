#!/usr/bin/env python3
"""
Скрипт заполнения таблицы meeting_admins при инициализации БД.

Источники (по приоритету):
1. MEETING_ADMINS_FILE — путь к файлу. Формат строки: "ФИО | email | phone"
2. MEETING_ADMINS — env. Формат: "email" или "full_name|email", разделитель ; или \n

Примеры:
  MEETING_ADMINS="a@x.ru;b@y.ru"
  MEETING_ADMINS="Иванов И.И.|a@x.ru;Петров П.П.|b@y.ru"
"""
import logging
import os
import sys
from pathlib import Path

# Добавляем корень проекта в path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from config import config
from db.models import MeetingAdmin
from db.session import get_session_context

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def _parse_env_entry(entry: str) -> tuple[str, str] | None:
    """
    Парсит запись: "email" или "full_name|email".
    Возвращает (email, full_name) или None если email пустой.
    """
    entry = entry.strip()
    if not entry:
        return None
    parts = [p.strip() for p in entry.split("|", 1)]
    if len(parts) == 1:
        email = parts[0]
        full_name = None
    else:
        full_name = parts[0] if parts[0] else None
        email = parts[1]
    email = email.lower().strip()
    if not email or "@" not in email:
        return None
    return (email, full_name or "")


def _parse_file_line(line: str) -> tuple[str, str] | None:
    """
    Парсит строку файла: "ФИО | email | phone".
    Возвращает (email, full_name) или None.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    parts = [p.strip() for p in line.split("|")]
    if len(parts) < 2:
        return None
    full_name = parts[0] if parts[0] else ""
    email = parts[1].lower().strip()
    if not email or "@" not in email:
        return None
    return (email, full_name)


def _load_admins_from_file(path: str) -> list[tuple[str, str]]:
    """Загружает список админов из файла."""
    result: list[tuple[str, str]] = []
    p = Path(path)
    if not p.exists():
        logger.warning("Файл %s не найден, пропуск", path)
        return result
    with open(p, encoding="utf-8") as f:
        for line in f:
            parsed = _parse_file_line(line)
            if parsed:
                result.append(parsed)
    return result


def _load_admins_from_env() -> list[tuple[str, str]]:
    """Загружает список админов из MEETING_ADMINS."""
    raw = os.getenv("MEETING_ADMINS", "").strip()
    if not raw:
        return []
    result: list[tuple[str, str]] = []
    for entry in raw.replace("\n", ";").split(";"):
        parsed = _parse_env_entry(entry)
        if parsed:
            result.append(parsed)
    return result


def seed_meeting_admins() -> int:
    """
    Добавляет админов в meeting_admins. Существующие по email пропускаются.
    Возвращает количество добавленных записей.
    """
    admins: list[tuple[str, str]] = []

    file_path = os.getenv("MEETING_ADMINS_FILE", "").strip()
    if file_path:
        admins = _load_admins_from_file(file_path)
        logger.info("Загружено %d админов из %s", len(admins), file_path)
    else:
        admins = _load_admins_from_env()
        if admins:
            logger.info("Загружено %d админов из MEETING_ADMINS", len(admins))

    if not admins:
        logger.info("Список meeting_admins пуст, пропуск")
        return 0

    added = 0
    with get_session_context() as session:
        for email, full_name in admins:
            existing = session.scalar(
                select(MeetingAdmin).where(MeetingAdmin.email == email)
            )
            if existing:
                if full_name and (
                    not existing.full_name or existing.full_name != full_name
                ):
                    existing.full_name = full_name
                    logger.info("Обновлён full_name: %s", email)
                continue
            try:
                with session.begin_nested():
                    admin = MeetingAdmin(email=email, full_name=full_name or None)
                    session.add(admin)
                added += 1
                logger.info("Добавлен админ: %s (%s)", email, full_name or "-")
            except IntegrityError:
                logger.warning("Дубликат email (пропуск): %s", email)

    return added


def main() -> int:
    """Точка входа."""
    try:
        # Инициализируем engine для config.database_url
        from db.session import get_engine
        get_engine()
    except Exception as e:
        logger.error("Ошибка подключения к БД: %s", e)
        return 1

    try:
        added = seed_meeting_admins()
        logger.info("Инициализация meeting_admins: добавлено %d", added)
        return 0
    except Exception as e:
        logger.error("Ошибка: %s", e, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
