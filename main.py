#!/usr/bin/env python3
"""
Главный модуль бота совещаний KChat.

Запуск:
    uv run python main.py
"""
import logging
import sys

from config import config
from db import init_db
from modules.core import BotApp
from modules.meeting import MeetingHandler

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, config.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)

if config.log_file:
    file_handler = logging.FileHandler(config.log_file, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    ))
    logging.getLogger().addHandler(file_handler)

logger = logging.getLogger(__name__)


def main() -> int:
    """Точка входа приложения."""
    logger.info("=" * 50)
    logger.info("Запуск бота совещаний KChat")
    logger.info("=" * 50)
    
    # Проверяем конфигурацию
    try:
        config.validate()
    except ValueError as e:
        logger.error("Ошибка конфигурации: %s", e)
        return 1
    
    # Инициализируем БД
    try:
        init_db()
    except Exception as e:
        logger.error("Ошибка инициализации БД: %s", e)
        return 1

    # Импортируем invited.json в БД при первом запуске (если нет активного совещания)
    try:
        from modules.meeting.meeting_repository import MeetingRepository
        repo = MeetingRepository()
        if not repo.get_active_meeting():
            mid, count = repo.import_from_invited_json()
            if mid:
                logger.info("Импорт invited.json в БД: meeting_id=%s, invited=%s", mid, count)
    except Exception as e:
        logger.warning("Импорт invited.json не выполнен: %s", e)

    # Создаём обработчик совещаний
    meeting_handler = MeetingHandler()
    
    # Создаём и настраиваем приложение
    app = BotApp()
    app.setup(
        message_handler=meeting_handler.handle_message,
        callback_handler=meeting_handler.handle_callback,
        sse_handler=meeting_handler.handle_sse_event,
    )
    
    # Запускаем (метод run() блокирует выполнение до остановки)
    try:
        app.run()
    except Exception as e:
        logger.error("Критическая ошибка: %s", e, exc_info=True)
        return 1
    
    logger.info("Бот остановлен")
    return 0


if __name__ == "__main__":
    sys.exit(main())
