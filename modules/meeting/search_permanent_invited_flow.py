"""
Диалог поиска постоянных приглашённых по ФИО или email.
"""
import logging
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class SearchPermanentInvitedFlow:
    """
    Состояние ожидания строки поиска для фильтрации постоянных приглашённых.
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

    def start(self, event: Any) -> str:
        """Запускает диалог поиска."""
        k = self._key(event)
        self._state[k] = {}
        return (
            "🔍 **Поиск постоянных участников**\n\n"
            "Введите **ФИО** или **email** для поиска:\n\n"
            "/отмена — отменить"
        )

    def cancel(self, event: Any) -> str:
        k = self._key(event)
        self._state.pop(k, None)
        return "❌ Поиск отменён."

    def process(
        self,
        event: Any,
        text: str,
        search_fn: Callable[[str], list],
    ) -> Tuple[str, bool]:
        """
        Обрабатывает ввод строки поиска.
        Returns: (reply_message, is_finished)
        """
        
        k = self._key(event)
        if k not in self._state:
            return "Нет активного диалога.", True

        text = text.strip()
        if not text:
            return "❌ Введите ФИО или email для поиска.\n\n/отмена — отменить", False

        search_query = text.strip()
        
        try:
            results = search_fn(search_query)
        except Exception as e:
            logger.exception("Ошибка поиска постоянных участников: %s", e)
            self._state.pop(k, None)
            return "❌ Ошибка при поиске.", True

        self._state.pop(k, None)
        if not results:
            return f"❌ По запросу «{search_query}» ничего не найдено.", True
        
        # Формируем список найденных
        lines = [f"🔍 **Результаты поиска** (найдено: {len(results)}):\n"]
        for i, inv in enumerate(results, 1):
            fio = (inv.get("full_name") or "").strip() or "—"
            contact = inv.get("email") or inv.get("phone") or ""
            part = f"{i}. {fio}"
            if contact:
                part += f" — {contact}"
            lines.append(part)
        
        return "\n".join(lines), True
