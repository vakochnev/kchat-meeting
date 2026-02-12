"""
Диалог редактирования активного собрания (только для админов).
Пошаговый ввод с валидацией: topic, date, time, place, link.
"""
import logging
from typing import Any, Callable, Dict, Optional, Tuple

from .create_meeting_flow import (
    CREATE_MEETING_STEPS,
    SKIP_HINT,
    MAX_TOPIC_LEN,
    MAX_PLACE_LEN,
    MAX_LINK_LEN,
)

EDIT_EDIT_CANCEL_HINT = "\n\n/отмена — отменить редактирование"
from .validators import validate_meeting_date, validate_meeting_time

logger = logging.getLogger(__name__)


def _build_meeting_display(data: Dict[str, Any]) -> str:
    """Формирует блок «Данные собрания» (как итоговое окно при создании)."""
    lines = [
        "**Данные собрания:**",
        f"📅 Тема: {data.get('topic', '')}",
        f"🕐 Дата: {data.get('date', '')} время: {data.get('time', '')}",
    ]
    if data.get("place"):
        lines.append(f"📍 Место проведения: {data['place']}")
    if data.get("link"):
        lines.append(f"🔗 Ссылка: {data['link']}")
    return "\n".join(lines)


def _build_edit_header(data: Dict[str, Any]) -> str:
    """Заголовок с собранными данными при редактировании."""
    lines = ["✏️ **Редактирование собрания**"]
    if data.get("topic"):
        lines.append(f"✏️ Тема: {data['topic']}")
    if data.get("date"):
        lines.append(f"📅 Дата: {data['date']}")
    if data.get("time"):
        lines.append(f"🕐 Время: {data['time']}")
    if "place" in data and data.get("place"):
        lines.append(f"📍 Место: {data['place']}")
    if "link" in data and data.get("link"):
        lines.append(f"🔗 Ссылка: {data['link']}")
    return "\n".join(lines)


def _build_edit_success_message(data: Dict[str, Any]) -> str:
    """Сообщение об успешном изменении собрания."""
    lines = [
        "✅ **Собрание успешно изменено!**",
        "",
        _build_meeting_display(data),
        "",
        "👥 /приглашенные — просмотр списка приглашённых и их ответов.",
    ]
    return "\n".join(lines)


class EditMeetingFlow:
    """
    Управление состоянием диалога редактирования собрания.
    Ключ: (sender_id, group_id, workspace_id).
    """

    def __init__(self) -> None:
        self._state: Dict[Tuple[int, int, int], Dict[str, Any]] = {}

    def _key(self, event: Any) -> Tuple[int, int, int]:
        """Ключ сессии для группировки сообщений в чате."""
        sid = event.sender_id or 0
        gid = getattr(event, "group_id", None) or 0
        wid = getattr(event, "workspace_id", None) or 0
        return (sid, gid, wid)

    def is_active(self, event: Any) -> bool:
        """Есть ли активный диалог для этого пользователя."""
        return self._key(event) in self._state

    def start(
        self, event: Any, meeting_info: Dict[str, Any]
    ) -> str:
        """
        Начинает диалог с данными текущего собрания.
        Показывает блок «Данные собрания» и первый запрос (тема).
        """
        k = self._key(event)
        data = {
            "topic": meeting_info.get("topic") or "",
            "date": meeting_info.get("date") or "",
            "time": meeting_info.get("time") or "",
            "place": meeting_info.get("place"),
            "link": meeting_info.get("link"),
        }
        self._state[k] = {"step": "topic", "data": data}
        display = _build_meeting_display(data)
        header = f"✏️ **Редактирование собрания**\n\n{display}"
        step_cfg = CREATE_MEETING_STEPS.get("topic", {})
        label = step_cfg.get("label", "")
        hint = step_cfg.get("hint", "")
        suffix = EDIT_EDIT_CANCEL_HINT
        parts = [f"{header}\n\n{label}"]
        if hint:
            parts.append(f"\n{hint}")
        parts.append(suffix)
        return "".join(parts)

    def _get_step_prompt(self, step: str, data: Dict[str, Any]) -> str:
        """Формирует запрос для шага: header, label, hint, /отмена."""
        header = _build_edit_header(data)
        step_cfg = CREATE_MEETING_STEPS.get(step, {})
        label = step_cfg.get("label", "")
        hint = step_cfg.get("hint", "")
        base = EDIT_EDIT_CANCEL_HINT
        suffix = f"{base}{SKIP_HINT}" if step in ("place", "link") else base
        if not label:
            return header
        parts = [f"{header}\n\n{label}"]
        if hint:
            parts.append(f"\n{hint}")
        parts.append(suffix)
        return "".join(parts)

    def try_skip(
        self, event: Any, update_fn: Callable[..., int]
    ) -> Tuple[str, bool]:
        """
        Пропуск необязательного поля (место, ссылка).
        Returns:
            (message, is_finished)
        """
        k = self._key(event)
        if k not in self._state:
            return "Нет активного диалога.", True

        state = self._state[k]
        step = state["step"]
        data = state["data"]

        if step == "place":
            data["place"] = None
            state["step"] = "link"
            return (self._get_step_prompt("link", data), False)
        if step == "link":
            data["link"] = None
            try:
                update_fn(
                    topic=data["topic"],
                    date=data["date"],
                    time=data["time"],
                    place=data.get("place"),
                    link=data.get("link"),
                )
                self._state.pop(k, None)
                return (_build_edit_success_message(data), True)
            except Exception as e:
                logger.exception("Ошибка обновления собрания: %s", e)
                return f"❌ Ошибка при изменении собрания: {e}", True

        return "Поле обязательно. Введите значение или используйте /отмена.", False

    def cancel(self, event: Any) -> str:
        """Отменяет диалог."""
        k = self._key(event)
        self._state.pop(k, None)
        return "❌ Редактирование собрания отменено."

    def process(
        self,
        event: Any,
        text: str,
        update_fn: Callable[..., int],
    ) -> Tuple[str, bool]:
        """
        Обрабатывает ввод пользователя.
        Returns:
            (reply_message, is_finished)
        """
        k = self._key(event)
        if k not in self._state:
            return "Нет активного диалога.", True

        state = self._state[k]
        step = state["step"]
        data = state["data"]

        if step == "topic":
            val = text.strip()
            if not val:
                header = _build_edit_header(data)
                return (
                    f"{header}{EDIT_CANCEL_HINT}\n\n"
                    "❌ Тема не может быть пустой. Введите тему собрания:",
                    False,
                )
            if len(val) > MAX_TOPIC_LEN:
                header = _build_edit_header(data)
                return (
                    f"{header}{EDIT_CANCEL_HINT}\n\n"
                    f"❌ Тема слишком длинная (макс. {MAX_TOPIC_LEN} символов). "
                    "Сократите:",
                    False,
                )
            data["topic"] = val
            state["step"] = "date"
            return (self._get_step_prompt("date", data), False)

        if step == "date":
            is_valid, normalized, error_msg = validate_meeting_date(text)
            if not is_valid:
                header = _build_edit_header(data)
                err = (
                    f"{header}{EDIT_CANCEL_HINT}\n\n"
                    f"{error_msg or '❌ Неверный формат даты.'}"
                )
                return (err, False)
            data["date"] = normalized
            state["step"] = "time"
            return (self._get_step_prompt("time", data), False)

        if step == "time":
            is_valid, normalized, error_msg = validate_meeting_time(text)
            if not is_valid:
                header = _build_edit_header(data)
                err = (
                    f"{header}{EDIT_CANCEL_HINT}\n\n"
                    f"{error_msg or '❌ Неверный формат времени.'}"
                )
                return (err, False)
            data["time"] = normalized
            state["step"] = "place"
            return (self._get_step_prompt("place", data), False)

        if step == "place":
            val = text.strip()
            if val in ("—", "-"):
                data["place"] = None
            else:
                if len(val) > MAX_PLACE_LEN:
                    header = _build_edit_header(data)
                    return (
                        f"{header}\n\n"
                        f"❌ Место слишком длинное (макс. {MAX_PLACE_LEN} символов):"
                        f"{SKIP_HINT}{EDIT_CANCEL_HINT}",
                        False,
                    )
                data["place"] = val or None
            state["step"] = "link"
            return (self._get_step_prompt("link", data), False)

        if step == "link":
            val = text.strip()
            if val in ("—", "-"):
                data["link"] = None
            else:
                if len(val) > MAX_LINK_LEN:
                    header = _build_edit_header(data)
                    return (
                        f"{header}{SKIP_HINT}{EDIT_CANCEL_HINT}\n\n"
                        f"❌ Ссылка слишком длинная (макс. {MAX_LINK_LEN} символов):",
                        False,
                    )
                data["link"] = val or None

            try:
                update_fn(
                    topic=data["topic"],
                    date=data["date"],
                    time=data["time"],
                    place=data.get("place"),
                    link=data.get("link"),
                )
                self._state.pop(k, None)
                return (_build_edit_success_message(data), True)
            except Exception as e:
                logger.exception("Ошибка обновления собрания: %s", e)
                return f"❌ Ошибка при изменении собрания: {e}", True

        return "Неизвестный шаг.", True
