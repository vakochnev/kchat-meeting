"""
Диспетчер команд: таблица «command → обработчик».

Заменяет длинную цепочку if/elif в _handle_command.
Новая команда = новая запись в register().
"""
import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class CommandDispatcher:
    """Маршрутизация идентификатора команды к обработчику."""

    def __init__(self) -> None:
        self._handlers: Dict[str, Callable] = {}

    def register(self, command: str, handler: Callable) -> None:
        """Регистрирует обработчик для команды."""
        self._handlers[command] = handler

    def dispatch(self, event: Any, command: str) -> bool:
        """
        Вызывает обработчик команды.

        Returns:
            True если обработчик найден и вызван, False если команда неизвестна.
        """
        handler = self._handlers.get(command)
        if handler is None:
            logger.warning("Неизвестная команда для диспетчера: %s", command)
            return False
        handler(event)
        return True
