"""
Сервис для работы с совещаниями.
"""
import logging
import re
from datetime import datetime
from typing import Optional, Dict, Any

from messenger_bot_api import MessageBotEvent, InlineMessageButton, MessageRequest

from .storage import MeetingStorage
from .config_manager import MeetingConfigManager
from .meeting_repository import MeetingRepository
from db.user_repository import UserRepository

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


def _build_full_name(data: Optional[Dict[str, Any]]) -> str:
    """Собирает full_name из last_name, first_name, middle_name (формат SSE/API)."""
    if not data:
        return "—"
    parts = [
        (data.get("last_name") or "").strip(),
        (data.get("first_name") or "").strip(),
        (data.get("middle_name") or "").strip(),
    ]
    return " ".join(p for p in parts if p) or "—"


def _merge_user_data(
    payload_data: Optional[Dict[str, Any]],
    api_data: Optional[Dict[str, Any]],
) -> Dict[str, Optional[str]]:
    """
    Объединяет данные из payload (SSE) и API. SSE/API присылают last_name, first_name,
    middle_name — при сохранении в БД использовать _build_full_name().
    """
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
        self.config = config_manager or MeetingConfigManager()
        self.meeting_repo = MeetingRepository()
        self.user_repo = UserRepository()
        self.storage = MeetingStorage(
            meeting_repo=self.meeting_repo,
            user_repo=self.user_repo,
        )
    
    def sync_user_from_event(self, event: MessageBotEvent) -> None:
        """
        Проверка приглашённости: получаем ФИО и email из SSE (payload события),
        при отсутствии — из API. Сравниваем с invited из БД по email.
        При совпадении связываем Invited с User (user_id).

        Вызывать при любой команде/обращении пользователя.
        """
        sender_id = event.sender_id
        group_id = getattr(event, "group_id", None)
        workspace_id = getattr(event, "workspace_id", None)
        if not sender_id or not group_id or not workspace_id:
            return

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
            return

        meeting_id = self._meeting_id_if_invited(user_data)
        if meeting_id is None:
            return

        full_name = _build_full_name(user_data)
        email = (user_data.get("email") or "").strip()
        phone = (user_data.get("phone") or "").strip() or None
        self.user_repo.save_user_on_chat(
            sender_id=sender_id,
            group_id=group_id,
            workspace_id=workspace_id,
            full_name=full_name or "—",
            email=email or None,
            phone=phone,
        )
        if email:
            self.storage.update_invited_contact(
                meeting_id=meeting_id,
                email=email,
                full_name=full_name or None,
                phone=phone,
            )
            logger.info(
                "Пользователь в списке приглашённых: sender_id=%s",
                sender_id,
            )

    def _meeting_id_if_invited(
        self,
        user_data: Dict[str, Optional[str]],
    ) -> Optional[int]:
        """
        Допуск по email: сверка со списком приглашённых (Invited по meeting_id).
        Возвращает meeting_id при совпадении, иначе None.
        """
        invited_list = self.meeting_repo.get_invited_list()
        meeting_info = self.meeting_repo.get_meeting_info()
        if not invited_list or not meeting_info:
            return None

        meeting_id = meeting_info.get("meeting_id")
        meeting_dt = self._parse_meeting_datetime_from_info(meeting_info)
        if meeting_id is None or meeting_dt is None:
            return None

        now = datetime.utcnow() if meeting_dt.tzinfo is None else datetime.now(meeting_dt.tzinfo)
        if meeting_dt < now:
            return None

        def get_str(d: dict, *keys: str) -> Optional[str]:
            for k in keys:
                v = d.get(k)
                if v is not None and str(v).strip():
                    return str(v).strip()
            return None

        user_email = self._normalize_email(get_str(user_data, "email"))
        if not user_email:
            logger.debug("allowed_check: у пользователя нет email")
            return None

        for inv in invited_list:
            if not isinstance(inv, dict):
                continue
            inv_email = self._normalize_email(get_str(inv, "email"))
            if inv_email and user_email == inv_email:
                return meeting_id

        logger.debug(
            "allowed_check: email [%s] не найден в invited (%s записей)",
            user_email,
            len(invited_list),
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
            logger.debug(
                "payload_check: sender_id=%s payload_type=%s payload_keys=%s",
                event.sender_id,
                type(payload).__name__,
                list(payload.keys()) if isinstance(payload, dict) else "не dict",
            )
            if not isinstance(payload, dict):
                logger.debug("payload_check: payload не является словарём")
                return None
            # 1) Классический формат: payload.messages[0].sender / .user
            messages = payload.get("messages")
            if messages and isinstance(messages, list) and len(messages) > 0:
                msg = messages[0]
                if isinstance(msg, dict):
                    sender = msg.get("sender") or msg.get("user") or msg
                    if sender and isinstance(sender, dict):
                        logger.debug(
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
                logger.debug("api_check: запрос к API для sender_id=%s", event.sender_id)
                user_info = get_user_info(event.sender_id)
                if user_info:
                    logger.debug("api_check: получены данные из API, keys=%s", list(user_info.keys()))
                    api_data = user_info_to_user_data(user_info)
                    logger.debug(
                        "api_check: преобразовано в user_data — full_name=%s email=%s",
                        _build_full_name(api_data),
                        api_data.get("email") or "нет",
                    )
                else:
                    logger.info("api_check: API вернул пустой результат")
            except Exception as e:
                logger.info("api_check: ошибка получения пользователя из API: %s", e, exc_info=True)
        user_data = _merge_user_data(payload_data, api_data)
        has_ident = bool(user_data and (user_data.get("email") or "").strip())
        logger.debug(
            "allowed_check: sender_id=%s payload=%s api=%s merged_has_fio_or_email=%s",
            event.sender_id,
            "есть" if payload_data else "нет",
            "есть" if api_data else "нет",
            has_ident,
        )
        if not has_ident:
            return None
        return user_data

    def sync_user_to_users_table(self, event: MessageBotEvent) -> None:
        """
        Сохраняет пользователя, начавшего чат с ботом, в таблицу users.
        Вызывать при каждом message/callback (если есть sender_id, group_id, workspace_id).
        """
        sender_id = event.sender_id
        group_id = getattr(event, "group_id", None)
        workspace_id = getattr(event, "workspace_id", None)
        if not sender_id or group_id is None or workspace_id is None:
            return
        user_data = self._get_user_data_from_event(event)
        full_name = _build_full_name(user_data)
        email = (user_data.get("email") or "").strip() if user_data else None
        phone = (user_data.get("phone") or "").strip() if user_data else None
        if not email and not phone and full_name == "—":
            email = ""  # сохраняем с пустым email, если нет данных
        try:
            self.user_repo.save_user_on_chat(
                sender_id=sender_id,
                group_id=group_id,
                workspace_id=workspace_id,
                full_name=full_name,
                email=email or None,
                phone=phone or None,
            )
        except Exception as e:
            logger.warning("Ошибка сохранения пользователя в users: %s", e)

    def check_user_allowed(self, event: MessageBotEvent) -> bool:
        """
        Проверяет допуск по email: пользователь в списке приглашённых или админ.
        """
        user_data = self._get_user_data_from_event(event)
        if user_data is None:
            logger.debug(
                "allowed_check: sender_id=%s — нет email (допуск только по email)",
                event.sender_id,
            )
            return False

        in_invited = self._meeting_id_if_invited(user_data) is not None
        email = (user_data.get("email") or "").strip().lower()
        is_admin = bool(email and self.meeting_repo.is_admin(email))
        allowed = in_invited or is_admin

        if allowed:
            reason = "приглашён" if in_invited else "админ"
            logger.info(
                "Пользователь допущен к совещанию: sender_id=%s (%s)",
                event.sender_id, reason
            )
        else:
            logger.info(
                "Пользователь НЕ допущен к совещанию: sender_id=%s (не найден в списке приглашённых или совещание в прошлом)",
                event.sender_id
            )
        return allowed

    def get_user_email(self, event: MessageBotEvent) -> Optional[str]:
        """Возвращает email пользователя из события (payload или API)."""
        user_data = self._get_user_data_from_event(event)
        if not user_data:
            return None
        email = (user_data.get("email") or "").strip()
        return email.lower() if email else None
    
    def get_user_fio(
        self,
        sender_id: int,
        event: Optional[MessageBotEvent] = None,
    ) -> Optional[str]:
        """
        Возвращает ФИО пользователя по sender_id для приветствия.
        Из users, payload или API.
        """
        if event is not None:
            group_id = getattr(event, "group_id", None)
            workspace_id = getattr(event, "workspace_id", None)
            if group_id is not None and workspace_id is not None:
                user = self.user_repo.get_by_chat(sender_id, group_id, workspace_id)
                if user and (user.get("full_name") or "").strip():
                    return (user.get("full_name") or "").strip()

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
                    return _build_full_name(merged)
            except Exception as e:
                logger.debug("Не удалось получить ФИО из API: %s", e)

        return None

    def _fio_from_message_payload(
        self,
        event: MessageBotEvent,
    ) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        Извлекает ФИО из payload события (messages[0].sender или messages[0]).
        SSE присылает last_name, first_name, middle_name — собираем в full_name.

        Returns:
            (full_name, сырые данные из payload).
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

            # SSE присылает last_name, first_name, middle_name
            ln = get_str(sender, "last_name", "lastName", "surname")
            fn = get_str(sender, "first_name", "firstName", "name")
            mn = get_str(sender, "middle_name", "middleName")
            parts = [p for p in (ln, fn, mn) if p]
            if not parts:
                return None, None

            full_name = " ".join(parts)
            data = {"last_name": ln, "first_name": fn, "middle_name": mn}
            return full_name, data
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
        Парсит дату/время совещания из meeting (БД).
        Поддерживает: datetime (ISO), date + time.
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
        """Возвращает дату/время активного совещания из БД или None."""
        return self.meeting_repo.get_meeting_datetime()

    def _get_meeting_id(self) -> Optional[int]:
        """Возвращает ID активного собрания или None."""
        info = self.meeting_repo.get_meeting_info()
        return info.get("meeting_id") if info else None

    def get_meeting_datetime_display(self) -> str:
        """
        Возвращает строку даты и времени совещания для отображения.
        Например: "15.02.2026, 10:00".
        """
        meeting_info = self.meeting_repo.get_meeting_info()
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

    def get_meeting_info(self) -> Dict[str, Any]:
        """Возвращает данные активного совещания (topic, date, time, place, link и т.д.)."""
        return self.meeting_repo.get_meeting_info()

    def get_invited_list(self) -> list:
        """Возвращает список приглашённых активного совещания."""
        return self.meeting_repo.get_invited_list()

    def get_voted_users(self) -> list:
        """
        Возвращает список проголосовавших по текущему (активному) собранию.
        """
        meeting_id = self._get_meeting_id()
        return self.storage.get_users_with_answers(meeting_id=meeting_id)

    def save_answer(
        self,
        sender_id: int,
        answer: str,
        group_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> bool:
        """
        Сохраняет ответ в Invited (по email и meeting_id)
        и при включённой настройке отправляет на бэкенд.
        """
        meeting_id = self._get_meeting_id()
        if not meeting_id:
            logger.error("Нет активного собрания")
            return False
        if group_id is None or workspace_id is None:
            logger.error("Нужны group_id и workspace_id для сохранения ответа")
            return False
        user = self.user_repo.get_by_chat(sender_id, group_id, workspace_id)
        if not user or not user.get("email"):
            logger.error("Пользователь не найден или нет email: sender_id=%s", sender_id)
            return False
        if not self.storage.update_invited_answer(
            email=user["email"],
            meeting_id=meeting_id,
            answer=answer,
            status="answered",
            full_name=user.get("full_name"),
            phone=user.get("phone"),
        ):
            logger.error(
                "Не удалось сохранить ответ: sender_id=%s, meeting_id=%s",
                sender_id, meeting_id,
            )
            return False
        return True
    
    def process_sse_event(self, event_data: Dict[str, Any]) -> None:
        """
        Обрабатывает событие из SSE и сохраняет данные пользователя.
        
        Args:
            event_data: Данные события из SSE.
        """
        try:
            logger.debug(
                "process_sse_event: type=%s keys=%s (content=%s)",
                event_data.get("type"),
                list(event_data.keys()),
                "str" if isinstance(event_data.get("content"), str) else type(event_data.get("content")),
            )
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
            
            # SSE присылает last_name, first_name, middle_name
            sse_data = {
                "last_name": (
                    sender_data.get("last_name") or
                    sender_data.get("surname") or
                    event_data.get("last_name")
                ),
                "first_name": (
                    sender_data.get("first_name") or
                    sender_data.get("name") or
                    event_data.get("first_name")
                ),
                "middle_name": (
                    sender_data.get("middle_name") or
                    event_data.get("middle_name")
                ),
            }
            full_name = _build_full_name(sse_data)

            # Данные пользователя в БД не сохраняем при входе в чат (SSE).
            # Сохранение выполняется только при голосовании (sync_user_from_event в handler).
            logger.debug(
                "SSE MESSAGE: sender_id=%s full_name=%s email=%s",
                sender_id,
                full_name,
                email or "нет",
            )
            logger.debug(
                "SSE MESSAGE: raw event keys=%s payload_keys=%s messages[0]=%s",
                list(event_data.keys()),
                list(event_data.get("payload", {}).keys()) if isinstance(event_data.get("payload"), dict) else "—",
                (event_data.get("payload", {}).get("messages") or [{}])[0] if event_data.get("payload") else "—",
            )
        
        except Exception as e:
            logger.error("Ошибка обработки SSE события: %s", e, exc_info=True)
