"""
Разрешение текстовой команды пользователя в идентификатор команды.
Обновляет контекст пользователя и атрибуты события для пагинации.
"""
import re
from typing import Any, Optional

from .user_context import UserContextStore


# Базовые команды бота (текст -> идентификатор)
COMMANDS: dict[str, str] = {
    "/start": "start",
    "/информация": "meeting",
    "/meeting": "meeting",
    "/приглашенные": "invited",
    "/участники": "participants",
    "/собрание": "meeting_menu",
    "собрание": "meeting_menu",
    "собрание создать": "create_meeting",
    "/создать_собрание": "create_meeting",
    "/create_meeting": "create_meeting",
    "/отмена": "cancel",
    "/cancel": "cancel",
    "/пропустить": "skip",
    "/skip": "skip",
    "/помощь": "help",
    "/help": "help",
    "/отправить": "send",
    "/неголосовали": "invited_not_voted",
    "/голосовали": "invited_voted",
}


class CommandResolver:
    """
    Определяет идентификатор команды по тексту сообщения.
    Учитывает контекст участников/приглашённых для /все и пагинации (/2, /3).
    """

    def __init__(self, user_context: UserContextStore) -> None:
        self._ctx = user_context

    def resolve(self, text_lower: str, event: Any) -> Optional[str]:
        """
        Возвращает идентификатор команды или None.
        Устанавливает на event атрибуты _page_number, _filter_type, _participants_page
        при необходимости.
        """
        command = COMMANDS.get(text_lower)

        if not command and text_lower.startswith("/приглашенные"):
            self._ctx.switch_to_invited(getattr(event, "sender_id", None))
            return "invited"

        if not command:
            participants_match = re.match(r"^/участники(\d+)$", text_lower)
            if participants_match:
                setattr(event, "_page_number", int(participants_match.group(1)))
                setattr(event, "_participants_page", True)
                self._ctx.switch_to_participants(getattr(event, "sender_id", None))
                return "participants_page"

        if not command and text_lower == "/участники":
            self._ctx.switch_to_participants(getattr(event, "sender_id", None))
            return "participants"

        if not command and text_lower == "/неголосовали":
            self._ctx.switch_to_invited_with_filter(
                getattr(event, "sender_id", None), "not_voted"
            )
            return "invited_not_voted"

        if not command and text_lower == "/голосовали":
            self._ctx.switch_to_invited_with_filter(
                getattr(event, "sender_id", None), "voted"
            )
            return "invited_voted"

        if not command and text_lower.startswith("/все"):
            sender_id = getattr(event, "sender_id", None)
            if self._ctx.get_participants_context(sender_id):
                return "participants_all"
            self._ctx.switch_to_invited_all(sender_id)
            return "invited_all"

        if not command and re.match(r"^/\d+$", text_lower):
            setattr(event, "_page_number", int(text_lower[1:]))
            sender_id = getattr(event, "sender_id", None)
            if self._ctx.get_participants_context(sender_id):
                return "participants_page"
            setattr(
                event,
                "_filter_type",
                self._ctx.get_filter_context(sender_id),
            )
            return "invited_page"

        return command
