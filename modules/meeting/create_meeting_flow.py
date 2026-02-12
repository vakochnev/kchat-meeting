"""
Диалог создания нового собрания (только для админов).
Пошаговый ввод с валидацией: topic, date, time, place, link.
"""
import logging
from typing import Any, Callable, Dict, Optional, Tuple

from .validators import validate_meeting_date, validate_meeting_time

logger = logging.getLogger(__name__)

MAX_TOPIC_LEN = 500
MAX_PLACE_LEN = 255
MAX_LINK_LEN = 500
CANCEL_HINT = "\n\n/отмена — отменить создание"
SKIP_HINT = "\n/пропустить — к следующему полю"


# Описание шагов диалога: label — текст запроса, hint — подсказка (выводится после label)
CREATE_MEETING_STEPS = {
    "topic": {
        "label": "✏️ Введите **тему** собрания:",
        "hint": "Например: «Планирование квартала»",
    },
    "date": {
        "label": "📅 Введите **дату**:",
        "hint": "Формат дд.мм.гггг",
    },
    "time": {
        "label": "🕐 Введите **время**:",
        "hint": "Формат чч:мм",
    },
    "place": {
        "label": "📍 Введите **место** проведения:",
        "hint": "Например: Зал конференций или пропустите",
    },
    "link": {
        "label": "🔗 Введите **ссылку** на подключение:",
        "hint": "Например: https://meet.example.com или пропустите",
    },
}


def _build_success_message(
    data: Dict[str, Any],
    is_move: bool = False,
    copied_count: int = 0,
) -> str:
    """Формирует итоговое сообщение о созданном собрании (без пустых место/ссылка)."""
    lines = [
        "✅ **Собрание успешно создано!**",
        "",
        "**Данные собрания:**",
        f"📅 Тема: {data.get('topic', '')}",
        f"🕐 Дата: {data.get('date', '')} время: {data.get('time', '')}",
    ]
    if data.get("place"):
        lines.append(f"📍 Место проведения: {data['place']}")
    if data.get("link"):
        lines.append(f"🔗 Ссылка: {data['link']}")
    if is_move and copied_count > 0:
        lines.extend([
            "",
            "👥 Приглашённые перенесены на новое собрание (статус сброшен).",
        ])
    lines.extend([
        "",
        "👥 /приглашенные — просмотр и редактирование списка приглашённых.",
    ])
    return "\n".join(lines)


def _build_header(data: Dict[str, Any], is_move: bool = False) -> str:
    """Формирует заголовок с собранными данными о собрании."""
    title = "📅 **Перенос собрания**" if is_move else "📋 **Создание нового собрания**"
    lines = [title]
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


class CreateMeetingFlow:
    """
    Управление состоянием диалога создания собрания.
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
        self,
        event: Any,
        move_from_meeting_id: Optional[int] = None,
        move_from_meeting_info: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Начинает диалог, возвращает первый запрос.
        move_from_meeting_id: при переносе — ID собрания, откуда копировать.
        move_from_meeting_info: topic, place, link из источника (при переносе).
        """
        k = self._key(event)
        is_move = move_from_meeting_id is not None and move_from_meeting_info
        if is_move:
            data = {
                "topic": move_from_meeting_info.get("topic") or "",
                "place": move_from_meeting_info.get("place"),
                "link": move_from_meeting_info.get("link"),
            }
            self._state[k] = {
                "step": "date",
                "data": data,
                "move_from_meeting_id": move_from_meeting_id,
            }
            return self._get_step_prompt("date", data, is_move=True)
        self._state[k] = {
            "step": "topic",
            "data": {},
            "move_from_meeting_id": None,
        }
        return self._get_step_prompt("topic", {}, is_move=False)

    def get_move_from_meeting_id(self, event: Any) -> Optional[int]:
        """Возвращает ID собрания для переноса приглашённых или None."""
        k = self._key(event)
        state = self._state.get(k)
        if not state:
            return None
        return state.get("move_from_meeting_id")

    def _get_step_prompt(
        self,
        step: str,
        data: Dict[str, Any],
        is_move: bool = False,
    ) -> str:
        """Формирует запрос для шага: header, label, hint, /отмена."""
        header = _build_header(data, is_move=is_move)
        step_cfg = CREATE_MEETING_STEPS.get(step, {})
        label = step_cfg.get("label", "")
        hint = step_cfg.get("hint", "")
        base = CANCEL_HINT
        suffix = f"{base}{SKIP_HINT}" if step in ("place", "link") else base
        if not label:
            return header
        parts = [f"{header}\n\n{label}"]
        if hint:
            parts.append(f"\n{hint}")
        parts.append(suffix)
        return "".join(parts)

    def try_skip(
        self, event: Any, create_fn: Callable[..., int]
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
            return (self._get_step_prompt("link", data, is_move=bool(state.get("move_from_meeting_id"))), False)
        if step == "link":
            data["link"] = None
            try:
                result = create_fn(
                    topic=data["topic"],
                    date=data["date"],
                    time=data["time"],
                    place=data.get("place"),
                    link=data.get("link"),
                )
                copied_count = result[1] if isinstance(result, tuple) else 0
                is_move = bool(state.get("move_from_meeting_id"))
                self._state.pop(k, None)
                return (
                    _build_success_message(data, is_move=is_move, copied_count=copied_count),
                    True,
                )
            except Exception as e:
                logger.exception("Ошибка создания собрания: %s", e)
                return f"❌ Ошибка при создании собрания: {e}", True

        return "Поле обязательно. Введите значение или используйте /отмена.", False

    def cancel(self, event: Any) -> str:
        """Отменяет диалог."""
        k = self._key(event)
        state = self._state.pop(k, None)
        if state and state.get("move_from_meeting_id"):
            return "❌ Перенос собрания отменён."
        return "❌ Создание собрания отменено."

    def process(
        self,
        event: Any,
        text: str,
        create_fn: Callable[..., int],
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
                header = _build_header({}, is_move=bool(state.get("move_from_meeting_id")))
                return f"{header}{CANCEL_HINT}\n\n❌ Тема не может быть пустой. Введите тему собрания:", False
            if len(val) > MAX_TOPIC_LEN:
                header = _build_header({}, is_move=bool(state.get("move_from_meeting_id")))
                return f"{header}{CANCEL_HINT}\n\n❌ Тема слишком длинная (макс. {MAX_TOPIC_LEN} символов). Сократите:", False
            data["topic"] = val
            state["step"] = "date"
            return (self._get_step_prompt("date", data, is_move=bool(state.get("move_from_meeting_id"))), False)

        if step == "date":
            is_valid, normalized, error_msg = validate_meeting_date(text)
            if not is_valid:
                header = _build_header(data, is_move=bool(state.get("move_from_meeting_id")))
                err = f"{header}{CANCEL_HINT}\n\n{error_msg or '❌ Неверный формат даты.'}"
                return (err, False)
            data["date"] = normalized
            state["step"] = "time"
            return (self._get_step_prompt("time", data, is_move=bool(state.get("move_from_meeting_id"))), False)

        if step == "time":
            is_valid, normalized, error_msg = validate_meeting_time(text)
            if not is_valid:
                header = _build_header(data, is_move=bool(state.get("move_from_meeting_id")))
                err = f"{header}{CANCEL_HINT}\n\n{error_msg or '❌ Неверный формат времени.'}"
                return (err, False)
            data["time"] = normalized
            # При переносе — только дата и время, сразу создаём
            if state.get("move_from_meeting_id"):
                try:
                    result = create_fn(
                        topic=data["topic"],
                        date=data["date"],
                        time=data["time"],
                        place=data.get("place"),
                        link=data.get("link"),
                    )
                    copied_count = result[1] if isinstance(result, tuple) else 0
                    self._state.pop(k, None)
                    return (
                        _build_success_message(
                            data, is_move=True, copied_count=copied_count
                        ),
                        True,
                    )
                except Exception as e:
                    logger.exception("Ошибка переноса собрания: %s", e)
                    return f"❌ Ошибка при переносе собрания: {e}", True
            state["step"] = "place"
            return (self._get_step_prompt("place", data, is_move=False), False)

        if step == "place":
            val = text.strip()
            if val in ("—", "-"):
                data["place"] = None
            else:
                if len(val) > MAX_PLACE_LEN:
                    header = _build_header(data, is_move=bool(state.get("move_from_meeting_id")))
                    return (
                        f"{header}\n\n"
                        f"❌ Место слишком длинное (макс. {MAX_PLACE_LEN} символов):"
                        f"{SKIP_HINT}{CANCEL_HINT}",
                        False,
                    )
                data["place"] = val or None
            state["step"] = "link"
            return (self._get_step_prompt("link", data, is_move=bool(state.get("move_from_meeting_id"))), False)

        if step == "link":
            val = text.strip()
            if val in ("—", "-"):
                data["link"] = None
            else:
                if len(val) > MAX_LINK_LEN:
                    header = _build_header(data, is_move=bool(state.get("move_from_meeting_id")))
                    return (
                        f"{header}{SKIP_HINT}{CANCEL_HINT}\n\n"
                        f"❌ Ссылка слишком длинная (макс. {MAX_LINK_LEN} символов):",
                        False,
                    )
                data["link"] = val or None

            # Все поля собраны — создаём
            try:
                result = create_fn(
                    topic=data["topic"],
                    date=data["date"],
                    time=data["time"],
                    place=data.get("place"),
                    link=data.get("link"),
                )
                copied_count = result[1] if isinstance(result, tuple) else 0
                is_move = bool(state.get("move_from_meeting_id"))
                self._state.pop(k, None)
                return (
                    _build_success_message(data, is_move=is_move, copied_count=copied_count),
                    True,
                )
            except Exception as e:
                logger.exception("Ошибка создания собрания: %s", e)
                return f"❌ Ошибка при создании собрания: {e}", True

        return "Неизвестный шаг.", True
