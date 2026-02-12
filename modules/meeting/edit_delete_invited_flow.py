"""
Диалог удаления приглашённого по email.
"""
import logging
import re
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"[^@]+@[^@]+\.[^@]+", re.IGNORECASE)


class EditDeleteInvitedFlow:
    """
    Состояние ожидания email для удаления приглашённого.
    Ключ: (sender_id, group_id, workspace_id).
    """

    def __init__(self) -> None:
        self._state: Dict[Tuple[int, int, int], Dict[str, Any]] = {}

    def _key(self, event: Any) -> Tuple[int, int, int]:
        sid = getattr(event, "sender_id", None) or getattr(event, "senderId", None) or 0
        gid = getattr(event, "group_id", None) or getattr(event, "groupId", None) or 0
        wid = getattr(event, "workspace_id", None) or getattr(event, "workspaceId", None) or 0
        try:
            sid = int(sid) if sid else 0
            gid = int(gid) if gid else 0
            wid = int(wid) if wid else 0
        except (TypeError, ValueError):
            pass
        return (sid, gid, wid)

    def is_active(self, event: Any) -> bool:
        return self._key(event) in self._state

    def start(self, event: Any, meeting_id: int) -> str:
        """Запускает диалог удаления."""
        k = self._key(event)
        self._state[k] = {
            "meeting_id": meeting_id,
        }
        return (
            "🗑 **Удаление приглашённого**\n\n"
            "Введите **email** приглашённого для удаления:\n\n"
            "/отмена — отменить"
        )

    def cancel(self, event: Any) -> str:
        k = self._key(event)
        self._state.pop(k, None)
        return "❌ Удаление отменено."

    def process(
        self,
        event: Any,
        text: str,
        delete_fn: Callable[[int, str], bool],
    ) -> Tuple[str, bool]:
        """
        Обрабатывает ввод email для удаления.
        Returns: (reply_message, is_finished)
        """
        k = self._key(event)
        if k not in self._state:
            return "Нет активного диалога.", True

        state = self._state[k]
        meeting_id = state.get("meeting_id")

        if not meeting_id:
            self._state.pop(k, None)
            return "❌ Ошибка: meeting_id не найден.", True

        text = text.strip()
        if not text:
            return "❌ Введите email.\n\n/отмена — отменить", False

        email = text.strip().lower()
        if not EMAIL_RE.match(email):
            return (
                "❌ Некорректный формат email. Введите email, например:\n"
                "user@example.com\n\n"
                "/отмена — отменить",
                False,
            )

        try:
            deleted = delete_fn(meeting_id, email)
        except Exception as e:
            logger.exception("Ошибка удаления приглашённого: %s", e)
            self._state.pop(k, None)
            return "❌ Ошибка при удалении.", True

        self._state.pop(k, None)
        if deleted:
            return "✅ Приглашённый удалён.", True
        return "❌ Приглашённый с таким email не найден.", True
