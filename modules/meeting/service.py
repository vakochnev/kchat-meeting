"""
Сервис для работы с совещаниями.
"""
import logging
import re
from datetime import datetime
from typing import Optional, Dict, Any

from messenger_bot_api import MessageBotEvent, InlineMessageButton, MessageRequest

from config import config as app_config
from .storage import MeetingStorage
from .api_client import BackendAPIClient
from .config_manager import MeetingConfigManager
from db.models import MeetingUser

logger = logging.getLogger(__name__)


def _normalize_job_title(value: Any) -> Optional[str]:
    """
    Возвращает строку должности или None.
    Числовые значения (ID должности, напр. 113) не считаются названием — отбрасываются.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.isdigit():
        return None
    return s


def _merge_user_data(
    payload_data: Optional[Dict[str, Any]],
    api_data: Optional[Dict[str, Any]],
) -> Dict[str, Optional[str]]:
    """Объединяет данные из payload и API: приоритет у непустых значений payload."""
    result = {}
    for key in ("last_name", "first_name", "middle_name", "email", "phone",
                "username", "job_title"):
        p = (payload_data or {}).get(key) if payload_data else None
        a = (api_data or {}).get(key) if api_data else None
        if p is not None and str(p).strip():
            result[key] = str(p).strip()
        elif a is not None and str(a).strip():
            result[key] = str(a).strip()
        else:
            result[key] = p if p is not None else a
    result["job_title"] = _normalize_job_title(result.get("job_title"))
    return result


class MeetingService:
    """Сервис для обработки логики совещаний."""
    
    def __init__(self, config_manager: Optional[MeetingConfigManager] = None):
        """
        Инициализирует сервис совещаний.
        
        Args:
            config_manager: Менеджер конфигурации. Если не указан, создаётся новый.
        """
        self.storage = MeetingStorage()
        self.api_client = BackendAPIClient()
        self.config = config_manager or MeetingConfigManager()
    
    def sync_user_from_event(self, event: MessageBotEvent) -> Optional[MeetingUser]:
        """
        Проверка приглашённости: получаем ФИО и email из SSE (payload события),
        при отсутствии — из API. Сравниваем с invited.json: совпадение ФИО,
        при наличии email в записи json — ещё и совпадение email.
        При совпадении выставляем meeting_datetime в БД.

        Вызывать при любой команде/обращении пользователя.

        Args:
            event: Событие сообщения (SSE payload с данными отправителя).

        Returns:
            MeetingUser после сохранения или None.
        """
        sender_id = event.sender_id
        group_id = getattr(event, "group_id", None)
        workspace_id = getattr(event, "workspace_id", None)
        if not sender_id or not group_id or not workspace_id:
            return None

        # ФИО и email: приоритет у данных из SSE (payload), иначе — из API
        payload_data = self._user_data_from_message_payload(event)
        api_data = None
        try:
            from api.users import get_user_info, user_info_to_user_data
            user_info = get_user_info(sender_id)
            if user_info:
                api_data = user_info_to_user_data(user_info)
        except Exception as e:
            logger.debug("Не удалось получить пользователя из API: %s", e)

        user_data = _merge_user_data(payload_data, api_data)
        if not user_data or not any(
            user_data.get(k) for k in ("email", "last_name", "first_name")
        ):
            return self.storage.get_user(sender_id)

        meeting_datetime = self._meeting_datetime_if_invited(user_data)
        self.storage.save_user(
            sender_id=sender_id,
            group_id=group_id,
            workspace_id=workspace_id,
            email=user_data.get("email"),
            phone=user_data.get("phone"),
            last_name=user_data.get("last_name"),
            first_name=user_data.get("first_name"),
            middle_name=user_data.get("middle_name"),
            username=user_data.get("username"),
            job_title=user_data.get("job_title"),
            meeting_datetime=meeting_datetime,
        )
        if meeting_datetime is not None:
            logger.info(
                "Пользователь в списке приглашённых: sender_id=%s",
                sender_id
            )

        return self.storage.get_user(sender_id)

    def _meeting_datetime_if_invited(
        self,
        user_data: Dict[str, Optional[str]],
    ) -> Optional[datetime]:
        """
        Сравнение с invited.json: ФИО должно совпадать; если у записи в json
        указан email — дополнительно должно совпадать поле email пользователя.
        Возвращает meeting_datetime при совпадении, иначе None.
        """
        invited_list = self.config.get_invited_list()
        meeting_info = self.config.get_meeting_info()
        if not invited_list or not meeting_info:
            logger.debug(
                "allowed_check: нет данных для проверки — invited_list=%s, meeting_info=%s",
                "пусто" if not invited_list else len(invited_list),
                "пусто" if not meeting_info else "есть",
            )
            return None

        meeting_dt = self._parse_meeting_datetime_from_info(meeting_info)
        if meeting_dt is None:
            logger.debug(
                "allowed_check: не удалось получить дату совещания (ключи meeting: %s)",
                list(meeting_info.keys()),
            )
            return None

        # Совещание в прошлом — участников нет, всем отказ
        now = datetime.utcnow() if meeting_dt.tzinfo is None else datetime.now(meeting_dt.tzinfo)
        if meeting_dt < now:
            logger.debug(
                "allowed_check: совещание в прошлом (%s), доступ запрещён",
                meeting_dt,
            )
            return None

        def get_str(d: dict, *keys: str) -> Optional[str]:
            for k in keys:
                v = d.get(k)
                if v is not None and str(v).strip():
                    return str(v).strip()
            return None

        user_email = self._normalize_email(get_str(user_data, "email"))
        user_phone = self._normalize_phone(get_str(user_data, "phone"))
        user_ln = get_str(user_data, "last_name")
        user_fn = get_str(user_data, "first_name")
        user_mn = get_str(user_data, "middle_name")
        logger.debug(
            "allowed_check: проверка ФИО — пользователь [%s %s %s] email=%s",
            user_ln or "",
            user_fn or "",
            user_mn or "",
            user_email or "нет",
        )

        def fio_eq(a: Optional[str], b: Optional[str]) -> bool:
            return (a or "").strip().lower() == (b or "").strip().lower()

        def inv_fio(inv: dict) -> tuple:
            """ФИО из записи invited: last_name, first_name, middle_name."""
            ln = get_str(inv, "last_name", "lastName")
            fn = get_str(inv, "first_name", "firstName")
            mn = get_str(inv, "middle_name", "middleName")
            if not ln and not fn and not mn:
                name = get_str(inv, "name")
                if name:
                    parts = name.split(maxsplit=2)
                    if len(parts) >= 3:
                        return parts[0], parts[1], parts[2]
                    if len(parts) == 2:
                        return parts[0], parts[1], None
                    if len(parts) == 1:
                        return parts[0], None, None
            return ln, fn, mn

        for inv in invited_list:
            if not isinstance(inv, dict):
                continue
            inv_ln, inv_fn, inv_mn = inv_fio(inv)
            fio_match = (
                fio_eq(user_ln, inv_ln)
                and fio_eq(user_fn, inv_fn)
                and fio_eq(user_mn or "", inv_mn or "")
            )
            if not fio_match:
                logger.debug(
                    "allowed_check: не совпало ФИО — пользователь [%s %s %s] vs invited [%s %s %s]",
                    user_ln or "", user_fn or "", user_mn or "",
                    inv_ln or "", inv_fn or "", inv_mn or "",
                )
                continue
            inv_email = self._normalize_email(get_str(inv, "email"))
            if inv_email:
                if user_email and user_email == inv_email:
                    logger.debug(
                        "allowed_check: совпадение по ФИО и email с записью [%s %s]",
                        inv_ln or "", inv_fn or "",
                    )
                    return meeting_dt
                else:
                    logger.debug(
                        "allowed_check: ФИО совпало, но email не совпал — пользователь email=%s vs invited email=%s",
                        user_email or "нет", inv_email,
                    )
            else:
                logger.debug(
                    "allowed_check: совпадение по ФИО с записью [%s %s] (email в json не задан)",
                    inv_ln or "", inv_fn or "",
                )
                return meeting_dt

        logger.debug(
            "allowed_check: нет совпадения в списке приглашённых (%s записей); "
            "проверены ФИО и при наличии — email. Пользователь: ФИО=[%s %s %s] email=%s",
            len(invited_list),
            user_ln or "", user_fn or "", user_mn or "",
            user_email or "нет",
        )
        return None

    @staticmethod
    def _normalize_email(s: Optional[str]) -> Optional[str]:
        if not s or not s.strip():
            return None
        return s.strip().lower()

    @staticmethod
    def _normalize_phone(s: Optional[str]) -> Optional[str]:
        if not s or not s.strip():
            return None
        digits = re.sub(r"\D", "", s)
        return digits if digits else None

    def _user_data_from_message_payload(
        self,
        event: MessageBotEvent,
    ) -> Optional[Dict[str, Optional[str]]]:
        """
        Извлекает данные пользователя из payload: messages[0].sender или
        payload.user / payload.sender (для callback и иных форматов SSE).
        """
        def get_str(d: Dict[str, Any], *keys: str) -> Optional[str]:
            if not d or not isinstance(d, dict):
                return None
            for k in keys:
                v = d.get(k)
                if v is not None and str(v).strip():
                    return str(v).strip()
            return None

        def sender_to_user_data(sender: Dict[str, Any]) -> Dict[str, Optional[str]]:
            return {
                "last_name": get_str(sender, "last_name", "lastName", "surname"),
                "first_name": get_str(sender, "first_name", "firstName", "name"),
                "middle_name": get_str(sender, "middle_name", "middleName"),
                "email": get_str(sender, "email"),
                "phone": get_str(sender, "phone"),
                "username": get_str(sender, "username", "login"),
                "job_title": _normalize_job_title(
                    get_str(sender, "job_title", "position", "jobTitle")
                ),
            }

        try:
            payload = event.get_payload_data()
            logger.info(
                "payload_check: sender_id=%s payload_type=%s payload_keys=%s",
                event.sender_id,
                type(payload).__name__,
                list(payload.keys()) if isinstance(payload, dict) else "не dict",
            )
            if not isinstance(payload, dict):
                logger.info("payload_check: payload не является словарём")
                return None
            # 1) Классический формат: payload.messages[0].sender / .user
            messages = payload.get("messages")
            if messages and isinstance(messages, list) and len(messages) > 0:
                msg = messages[0]
                if isinstance(msg, dict):
                    sender = msg.get("sender") or msg.get("user") or msg
                    if sender and isinstance(sender, dict):
                        logger.info(
                            "payload_check: найдены данные в messages[0], sender_keys=%s",
                            list(sender.keys()),
                        )
                        return sender_to_user_data(sender)
            # 2) Fallback: пользователь в корне payload (часть SSE)
            sender = payload.get("user") or payload.get("sender")
            if sender and isinstance(sender, dict):
                logger.info(
                    "payload_check: найдены данные в payload.user/sender, keys=%s",
                    list(sender.keys()),
                )
                return sender_to_user_data(sender)
            logger.info("payload_check: данные пользователя не найдены в payload")
            return None
        except Exception as e:
            logger.info("payload_check: ошибка извлечения данных из payload: %s", e, exc_info=True)
            return None

    def _get_user_data_from_event(
        self, event: MessageBotEvent
    ) -> Optional[Dict[str, Optional[str]]]:
        """
        Получает ФИО и email пользователя из SSE (payload) и API.
        Таблица не используется. Нужно для проверки допуска по json.
        """
        payload_data = self._user_data_from_message_payload(event)
        api_data = None
        if event.sender_id is not None:
            try:
                from api.users import get_user_info, user_info_to_user_data
                logger.info("api_check: запрос к API для sender_id=%s", event.sender_id)
                user_info = get_user_info(event.sender_id)
                if user_info:
                    logger.info("api_check: получены данные из API, keys=%s", list(user_info.keys()))
                    api_data = user_info_to_user_data(user_info)
                    logger.info(
                        "api_check: преобразовано в user_data — ФИО=[%s %s %s] email=%s",
                        api_data.get("last_name") or "",
                        api_data.get("first_name") or "",
                        api_data.get("middle_name") or "",
                        api_data.get("email") or "нет",
                    )
                else:
                    logger.info("api_check: API вернул пустой результат")
            except Exception as e:
                logger.info("api_check: ошибка получения пользователя из API: %s", e, exc_info=True)
        user_data = _merge_user_data(payload_data, api_data)
        has_ident = bool(
            user_data
            and any(
                user_data.get(k) for k in ("email", "last_name", "first_name")
            )
        )
        logger.debug(
            "allowed_check: sender_id=%s payload=%s api=%s merged_has_fio_or_email=%s",
            event.sender_id,
            "есть" if payload_data else "нет",
            "есть" if api_data else "нет",
            has_ident,
        )
        if user_data:
            logger.debug(
                "allowed_check: данные пользователя из SSE/API — ФИО=[%s %s %s] email=%s phone=%s",
                user_data.get("last_name") or "",
                user_data.get("first_name") or "",
                user_data.get("middle_name") or "",
                user_data.get("email") or "нет",
                user_data.get("phone") or "нет",
            )
        if not has_ident:
            return None
        return user_data

    def check_user_allowed(self, event: MessageBotEvent) -> bool:
        """
        Проверяет, допущен ли пользователь: только сравнение данных из SSE
        (кто зашёл) со списком приглашённых из json. Таблица не участвует.
        """
        user_data = self._get_user_data_from_event(event)
        if user_data is None:
            logger.debug(
                "allowed_check: sender_id=%s — нет ФИО/email из SSE и API, доступ запрещён",
                event.sender_id,
            )
            return False
        
        logger.debug(
            "allowed_check: sender_id=%s данные из SSE/API — ФИО=[%s %s %s] email=%s",
            event.sender_id,
            user_data.get("last_name") or "",
            user_data.get("first_name") or "",
            user_data.get("middle_name") or "",
            user_data.get("email") or "нет",
        )
        
        in_invited = self._meeting_datetime_if_invited(user_data) is not None
        allowed = in_invited
        
        if allowed:
            logger.info(
                "Пользователь допущен к совещанию: sender_id=%s",
                event.sender_id
            )
        else:
            logger.info(
                "Пользователь НЕ допущен к совещанию: sender_id=%s (не найден в invited.json или совещание в прошлом)",
                event.sender_id
            )
        return allowed
    
    def get_user_fio(
        self,
        sender_id: int,
        event: Optional[MessageBotEvent] = None,
    ) -> Optional[str]:
        """
        Возвращает ФИО пользователя по sender_id для приветствия.
        Только чтение: из БД или из события (payload/API). В БД не сохраняет —
        сохранение выполняется при голосовании (sync_user_from_event).
        """
        fio = self.storage.get_user_fio(sender_id)
        if fio:
            return fio

        if event is not None:
            payload_fio, payload_data = self._fio_from_message_payload(event)
            if payload_fio:
                return payload_fio

            try:
                from api.users import get_user_info, user_info_to_user_data
                user_info = get_user_info(sender_id)
                if user_info:
                    api_data = user_info_to_user_data(user_info)
                    merged = _merge_user_data(payload_data, api_data)
                    parts = [
                        merged.get("last_name"),
                        merged.get("first_name"),
                        merged.get("middle_name"),
                    ]
                    parts = [p.strip() for p in parts if p and str(p).strip()]
                    if parts:
                        return " ".join(parts)
            except Exception as e:
                logger.debug("Не удалось получить ФИО из API: %s", e)

        return None

    def _fio_from_message_payload(
        self,
        event: MessageBotEvent,
    ) -> tuple[Optional[str], Optional[Dict[str, Optional[str]]]]:
        """
        Извлекает ФИО из payload события (messages[0].sender или messages[0]).
        Поддерживает camelCase и snake_case.

        Returns:
            (fio_string, dict с last_name, first_name, middle_name для сохранения в БД).
        """
        try:
            payload = event.get_payload_data()
            if not isinstance(payload, dict):
                return None, None
            messages = payload.get("messages")
            if not messages or not isinstance(messages, list) or len(messages) == 0:
                return None, None
            msg = messages[0]
            if not isinstance(msg, dict):
                return None, None
            sender = msg.get("sender") or msg.get("user") or msg

            def get_str(d: Dict[str, Any], *keys: str) -> Optional[str]:
                for k in keys:
                    v = d.get(k)
                    if v is not None and str(v).strip():
                        return str(v).strip()
                return None

            last_name = get_str(sender, "last_name", "lastName", "surname")
            middle_name = get_str(sender, "middle_name", "middleName")
            first_name = get_str(sender, "first_name", "firstName", "name")

            parts = [p for p in (last_name, first_name, middle_name) if p]
            if not parts:
                return None, None

            fio = " ".join(parts)
            data = {
                "last_name": last_name,
                "first_name": first_name,
                "middle_name": middle_name,
            }
            return fio, data
        except Exception as e:
            logger.debug("Не удалось извлечь ФИО из payload: %s", e)
            return None, None
    
    def ask_attendance(
        self,
        event: MessageBotEvent,
        message: Optional[str] = None,
    ) -> None:
        """
        Спрашивает пользователя о планируемом присутствии на совещании.
        Если message передан — отправляет его с кнопками; иначе собирает welcome с ФИО.
        """
        if message is None:
            fio = self.get_user_fio(event.sender_id, event) or "—"
            tpl = self.config.get_message("welcome")
            message = tpl.format(fio=fio) if "{fio}" in (tpl or "") else (tpl or "")
        
        # Создаём кнопки из конфигурации
        buttons = []
        all_buttons = self.config.get_all_buttons()
        
        for key in ["yes", "no"]:
            button_config = all_buttons.get(key)
            if button_config:
                label = button_config.get("label") or ""
                callback_message = button_config.get("callback_message") or label
                callback_data = button_config.get("callback_data") or ""
                buttons.append(
                    InlineMessageButton(
                        id=button_config.get("id"),
                        label=label,
                        callback_message=callback_message,
                        callback_data=callback_data,
                    )
                )
        
        try:
            event.reply_text_message(
                MessageRequest(text=message, buttons=buttons)
            )
        except Exception as e:
            logger.error("Ошибка отправки сообщения: %s", e)
            event.reply_text(message)
    
    def _parse_meeting_datetime_from_info(
        self, meeting_info: Dict[str, Any]
    ) -> Optional[datetime]:
        """
        Парсит дату/время совещания из meeting (invited.json).
        Поддерживает: поле "datetime" (ISO) или пару "date" + "time"
        (date: DD.MM.YYYY или YYYY-MM-DD, time: HH:MM или HH:MM:SS).
        """
        dt_str = meeting_info.get("datetime")
        if dt_str:
            try:
                return datetime.fromisoformat(
                    str(dt_str).replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass
        date_str = meeting_info.get("date")
        time_str = meeting_info.get("time")
        if not date_str or not time_str:
            return None
        date_str = str(date_str).strip()
        time_str = str(time_str).strip()
        try:
            # DD.MM.YYYY
            if "." in date_str and len(date_str) >= 8:
                parts = date_str.split(".")
                if len(parts) == 3:
                    day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                    if len(parts[2]) == 2:
                        year += 2000 if year < 50 else 1900
                else:
                    return None
            else:
                # YYYY-MM-DD
                dt_date = datetime.strptime(date_str[:10], "%Y-%m-%d")
                day, month, year = dt_date.day, dt_date.month, dt_date.year
            # time HH:MM or HH:MM:SS
            if time_str.count(":") >= 2:
                t = datetime.strptime(time_str, "%H:%M:%S")
            else:
                t = datetime.strptime(time_str, "%H:%M")
            return datetime(year, month, day, t.hour, t.minute, t.second)
        except (ValueError, TypeError):
            return None

    def _get_meeting_datetime(self) -> Optional[datetime]:
        """Возвращает дату/время совещания из invited.json или None."""
        meeting_info = self.config.get_meeting_info()
        return self._parse_meeting_datetime_from_info(meeting_info)

    def get_meeting_datetime_display(self) -> str:
        """
        Возвращает строку даты и времени совещания для отображения (из invited.json).
        Например: "15.02.2026, 10:00".
        """
        meeting_info = self.config.get_meeting_info()
        date_str = (meeting_info.get("date") or "").strip()
        time_str = (meeting_info.get("time") or "").strip()
        if date_str and time_str:
            return f"{date_str}, {time_str}"
        if date_str:
            return date_str
        meeting_dt = self._get_meeting_datetime()
        if meeting_dt:
            return meeting_dt.strftime("%d.%m.%Y, %H:%M")
        return ""

    def get_voted_users(self) -> list:
        """
        Возвращает список проголосовавших по текущему совещанию (дата из invited.json).
        Отметки ✅/❌ показываются только за это совещание.
        """
        meeting_dt = self._get_meeting_datetime()
        return self.storage.get_users_with_answers(meeting_datetime=meeting_dt)

    def save_answer(
        self,
        sender_id: int,
        answer: str,
        group_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> bool:
        """
        Сохраняет ответ пользователя в таблицу (по пользователю и дате совещания)
        и при включённой настройке отправляет на бэкенд.

        Args:
            sender_id: ID отправителя.
            answer: Текст ответа для сохранения (из answer_text в config).
            group_id: ID группы (из события).
            workspace_id: ID рабочего пространства (из события).

        Returns:
            True если ответ сохранён в таблицу.
        """
        meeting_dt = self._get_meeting_datetime()
        user_data = self.storage.update_user_answer(
            sender_id=sender_id,
            answer=answer,
            status="pending",
            group_id=group_id,
            workspace_id=workspace_id,
            meeting_datetime=meeting_dt,
        )

        if not user_data:
            logger.error(
                "Не удалось сохранить ответ: sender_id=%s, group_id=%s, workspace_id=%s, meeting_datetime=%s",
                sender_id, group_id, workspace_id, meeting_dt,
            )
            return False

        if app_config.send_to_backend:
            if self.api_client.send_meeting_response(user_data):
                self.storage.update_user_answer(
                    sender_id=sender_id,
                    answer=answer,
                    status="sent",
                    group_id=group_id,
                    workspace_id=workspace_id,
                    meeting_datetime=meeting_dt,
                )
            else:
                logger.warning(
                    "Не удалось отправить данные на бэкенд: sender_id=%s",
                    sender_id,
                )
        else:
            logger.debug(
                "Отправка на бэкенд отключена (SEND_TO_BACKEND), данные только в таблице"
            )

        return True
    
    def process_sse_event(self, event_data: Dict[str, Any]) -> None:
        """
        Обрабатывает событие из SSE и сохраняет данные пользователя.
        
        Args:
            event_data: Данные события из SSE.
        """
        try:
            event_type = event_data.get("type")
            
            # Обрабатываем только события MESSAGE
            if event_type != "MESSAGE":
                return
            
            # Извлекаем данные из события
            # Структура может быть разной, проверяем несколько вариантов
            sender_id = (
                event_data.get("sender_id") or
                event_data.get("sender", {}).get("id") or
                event_data.get("user", {}).get("id")
            )
            
            group_id = (
                event_data.get("group_id") or
                event_data.get("group", {}).get("id")
            )
            
            workspace_id = (
                event_data.get("workspace_id") or
                event_data.get("workspace", {}).get("id")
            )
            
            if not sender_id or not group_id or not workspace_id:
                logger.debug(
                    "Неполные данные события (пропуск): %s",
                    event_data.get("type")
                )
                return
            
            # Извлекаем данные пользователя
            sender_data = event_data.get("sender", {}) or event_data.get("user", {})
            
            username = (
                sender_data.get("username") or
                event_data.get("username")
            )
            
            email = (
                sender_data.get("email") or
                event_data.get("email")
            )
            
            phone = (
                sender_data.get("phone") or
                event_data.get("phone")
            )
            
            job_title = (#_normalize_job_title(
                sender_data.get("job_title") or
                # sender_data.get("position") or
                event_data.get("job_title")
            )
            
            last_name = (
                sender_data.get("last_name") or
                sender_data.get("surname") or
                event_data.get("last_name")
            )
            
            middle_name = (
                sender_data.get("middle_name") or
                event_data.get("middle_name")
            )
            
            first_name = (
                sender_data.get("first_name") or
                sender_data.get("name") or
                event_data.get("first_name")
            )
            
            # Данные пользователя в БД не сохраняем при входе в чат (SSE).
            # Сохранение выполняется только при голосовании (sync_user_from_event в handler).
            logger.info(
                "SSE MESSAGE: sender_id=%s ФИО=[%s %s %s] email=%s (данные в БД сохраняются при голосовании)",
                sender_id,
                last_name or "",
                first_name or "",
                middle_name or "",
                email or "нет",
            )
            logger.info(
                "SSE MESSAGE: структура события — type=%s keys=%s",
                event_type,
                list(event_data.keys()),
            )
        
        except Exception as e:
            logger.error("Ошибка обработки SSE события: %s", e, exc_info=True)
