"""
Диалог добавления постоянных приглашённых списком (только для админов).
Ожидает следующее сообщение с форматом: ФИО | email | телефон.
"""
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class AddPermanentInvitedFlow:
    """
    Состояние ожидания списка постоянных приглашённых.
    Ключ: (sender_id, group_id, workspace_id).
    """

    def __init__(self) -> None:
        self._state: Dict[Tuple[int, int, int], Dict[str, Any]] = {}

    def _key(self, event: Any) -> Tuple[int, int, int]:
        """Ключ сессии: (sender_id, group_id, workspace_id)."""
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
        """Есть ли активное ожидание списка."""
        k = self._key(event)
        found = k in self._state
        logger.debug(
            "AddPermanentInvitedFlow.is_active: key=%s state_keys=%s found=%s",
            k,
            list(self._state.keys()),
            found,
        )
        return found

    def start(self, event: Any) -> str:
        """Запускает ожидание списка."""
        k = self._key(event)
        self._state[k] = {}
        logger.debug(
            "AddPermanentInvitedFlow.start: key=%s state_keys=%s",
            k, list(self._state.keys()),
        )
        return (
            "📋 Отправьте список постоянных участников:\n\n"
            "Формат: **ФИО** | **email** | **телефон**\n"
            "Пример: (каждая строка — один человек)\n"
            "✅ Иванов Иван Иванович | ivanov@mail.ru | +79991234567\n\n"
            "/отмена — отменить"
        )

    def cancel(self, event: Any) -> str:
        """Отменяет ожидание."""
        k = self._key(event)
        self._state.pop(k, None)
        return "❌ Добавление постоянных участников отменено."

    def process(
        self,
        event: Any,
        text: str,
        parse_fn: Callable[[str], List[Dict[str, str]]],
        save_fn: Callable[[str, str, Optional[str]], bool],
    ) -> Tuple[str, bool]:
        """
        Обрабатывает сообщение со списком.
        save_fn(full_name, email, phone) -> True если добавлен, False если обновлён.
        Returns:
            (reply_message, is_finished)
        """
        k = self._key(event)
        logger.debug(
            "AddPermanentInvitedFlow.process: key=%s in_state=%s text_len=%d text=%r",
            k, k in self._state, len(text), text[:200] if text else "",
        )
        if k not in self._state:
            return "Нет активного ожидания списка.", True

        parsed = parse_fn(text)
        logger.debug("AddPermanentInvitedFlow.process: parsed=%d записей %s", len(parsed), parsed)
        if not parsed:
            return (
                "❌ Не найдено ни одной записи в формате:\n"
                "ФИО | email | телефон\n\n"
                "Попробуйте снова или /отмена",
                False,
            )

        added_count = 0
        updated_count = 0
        try:
            for row in parsed:
                full_name = row.get("full_name") or ""
                email = row.get("email") or ""
                phone = row.get("phone")
                if not email:
                    continue
                is_new = save_fn(full_name, email, phone)
                if is_new:
                    added_count += 1
                else:
                    updated_count += 1
        except Exception as e:
            logger.exception("Ошибка сохранения постоянных участников: %s", e)
            return (
                "❌ Ошибка при сохранении в базу данных. "
                "Попробуйте ещё раз или /отмена.",
                False,
            )

        self._state.pop(k, None)
        parts = ["✅ **Данные сохранены.**"]
        if added_count > 0:
            parts.append(f"\nДобавлено: **{added_count}** чел.")
        if updated_count > 0:
            parts.append(f"Обновлено: **{updated_count}** чел.")
        return ("\n".join(parts), True)
