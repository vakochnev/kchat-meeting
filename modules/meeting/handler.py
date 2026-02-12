"""
Обработчик событий совещаний.
"""
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from messenger_bot_api import MessageBotEvent, InlineMessageButton, MessageRequest

from .service import MeetingService
from .config_manager import MeetingConfigManager
from .create_meeting_flow import CreateMeetingFlow
from .edit_meeting_flow import EditMeetingFlow
from .add_invited_flow import AddInvitedFlow
from .edit_delete_invited_flow import EditDeleteInvitedFlow

logger = logging.getLogger(__name__)


# Команды бота
COMMANDS = {
    "/start": "start",
    "/информация": "meeting",
    "/meeting": "meeting",
    "/участие": "attendance",
    "/приглашенные": "invited",
    "/собрание": "meeting_menu",
    "/создать_собрание": "create_meeting",
    "/create_meeting": "create_meeting",
    "/отмена": "cancel",
    "/отмен": "cancel",
    "/cancel": "cancel",
    "/пропустить": "skip",
    "/skip": "skip",
    "/помощь": "help",
    "/help": "help",
}


class MeetingHandler:
    """Главный обработчик событий бота совещаний."""
    
    def __init__(self):
        self.config = MeetingConfigManager()
        self.service = MeetingService(config_manager=self.config)
        self.create_meeting_flow = CreateMeetingFlow()
        self.edit_meeting_flow = EditMeetingFlow()
        self.add_invited_flow = AddInvitedFlow()
        self.edit_delete_invited_flow = EditDeleteInvitedFlow()
    
    def handle_message(self, event: MessageBotEvent) -> None:
        """Обрабатывает входящее сообщение."""
        text = (event.message_text or "").strip()
        logger.debug(
            "handle_message: sender_id=%s group_id=%s workspace_id=%s text_len=%d text=%r",
            getattr(event, "sender_id", None),
            getattr(event, "group_id", None),
            getattr(event, "workspace_id", None),
            len(text),
            text[:200] if text else "",
        )
        self.service.sync_user_to_users_table(event)
        if not self.service.check_user_allowed(event):
            event.reply_text(self.config.get_message("not_allowed"))
            return

        if not text:
            return
        
        text_lower = text.lower()
        command = COMMANDS.get(text_lower)
        if not command and text_lower.startswith("/приглашенные"):
            command = "invited"

        if command:
            if command == "skip":
                if self.create_meeting_flow.is_active(event):
                    move_from = self.create_meeting_flow.get_move_from_meeting_id(event)
                    if move_from is not None:

                        def create_and_copy_invited(*args, **kwargs):
                            new_id = self.service.meeting_repo.create_new_meeting(
                                *args, **kwargs
                            )
                            copied = self.service.meeting_repo.copy_invited_to_meeting(
                                move_from, new_id
                            )
                            return (new_id, copied)

                        create_fn = create_and_copy_invited
                    else:
                        create_fn = self.service.meeting_repo.create_new_meeting
                    msg = self.create_meeting_flow.try_skip(event, create_fn)
                    event.reply_text(msg[0])
                    return
                if self.edit_meeting_flow.is_active(event):
                    msg = self.edit_meeting_flow.try_skip(
                        event, self.service.meeting_repo.update_active_meeting
                    )
                    event.reply_text(msg[0])
                    return
                event.reply_text(
                    "Команда /пропустить доступна только для необязательных "
                    "полей (место, ссылка)."
                )
                return
            if command != "cancel":
                if self.create_meeting_flow.is_active(event):
                    self.create_meeting_flow.cancel(event)
                if self.edit_meeting_flow.is_active(event):
                    self.edit_meeting_flow.cancel(event)
                if self.add_invited_flow.is_active(event):
                    self.add_invited_flow.cancel(event)
                if self.edit_delete_invited_flow.is_active(event):
                    self.edit_delete_invited_flow.cancel(event)
            self._handle_command(event, command)
            return

        # Пользователь в диалоге создания собрания (или переноса) — обрабатываем ввод
        if self.create_meeting_flow.is_active(event):
            move_from = self.create_meeting_flow.get_move_from_meeting_id(event)
            if move_from is not None:

                def create_and_copy_invited(*args, **kwargs):
                    new_id = self.service.meeting_repo.create_new_meeting(*args, **kwargs)
                    copied = self.service.meeting_repo.copy_invited_to_meeting(
                        move_from, new_id
                    )
                    return (new_id, copied)

                create_fn = create_and_copy_invited
            else:
                create_fn = self.service.meeting_repo.create_new_meeting
            msg, done = self.create_meeting_flow.process(event, text, create_fn)
            event.reply_text(msg)
            return

        # Пользователь в диалоге редактирования собрания — обрабатываем ввод
        if self.edit_meeting_flow.is_active(event):
            msg, _ = self.edit_meeting_flow.process(
                event, text, self.service.meeting_repo.update_active_meeting
            )
            event.reply_text(msg)
            return

        # Ожидание email для удаления приглашённого
        if self.edit_delete_invited_flow.is_active(event):
            msg, done = self.edit_delete_invited_flow.process(
                event,
                text,
                self.service.meeting_repo.delete_invited_by_email,
            )
            event.reply_text(msg)
            if done:
                self._handle_invited(event, skip_parse_and_save=True)
            return

        # Ожидание списка приглашённых (отдельным сообщением)
        add_invited_active = self.add_invited_flow.is_active(event)
        logger.debug(
            "handle_message: add_invited_flow.is_active=%s",
            add_invited_active,
        )
        if add_invited_active:
            msg, done = self.add_invited_flow.process(
                event,
                text,
                self._parse_invited_list,
                self.service.meeting_repo.save_invited_batch,
            )
            event.reply_text(msg)
            if done:
                self._handle_invited(event, skip_parse_and_save=True)
            return

        # Список без /приглашенные добавить — парсим и сохраняем, если админ и есть собрание
        meeting_info = self.service.get_meeting_info()
        meeting_id = meeting_info.get("meeting_id") if meeting_info else None
        email = self.service.get_user_email(event)
        is_admin = bool(email and self.service.meeting_repo.is_admin(email))
        if is_admin and meeting_id:
            parsed = self._parse_invited_list(text)
            if parsed:
                try:
                    added = self.service.meeting_repo.save_invited_batch(
                        meeting_id, parsed
                    )
                    if added > 0:
                        event.reply_text(
                            f"✅ **Данные сохранены.** ✨ Добавлено: **{added}** чел."
                        )
                        self._handle_invited(event, skip_parse_and_save=True)
                    return
                except Exception as e:
                    logger.exception("Ошибка сохранения приглашённых: %s", e)
                    event.reply_text("❌ Ошибка при сохранении в базу данных.")
                    return

        self._show_help(event)
    
    def handle_callback(self, event: MessageBotEvent) -> None:
        """Обрабатывает callback от кнопки."""
        self.service.sync_user_to_users_table(event)
        if not self.service.check_user_allowed(event):
            event.reply_text(self.config.get_message("not_allowed"))
            return

        # callback_data: из selected_button (messenger_bot_api) или атрибута event
        sb = getattr(event, "selected_button", None)
        callback_data = (
            (sb.callback_data if sb else None)
            or getattr(event, "callback_data", None)
            or ""
        )
        logger.debug("Callback от %s: %s", event.sender_id, callback_data)
        
        if callback_data == "meeting_yes":
            self._handle_attendance_answer(event, "yes")
        
        elif callback_data == "meeting_no":
            self._handle_attendance_answer(event, "no")

        elif callback_data == "meeting_create":
            self._handle_create_meeting(event)

        elif callback_data == "meeting_edit":
            self._handle_edit_meeting(event)

        elif callback_data == "meeting_move":
            self._handle_move_meeting(event)

        elif callback_data == "invited_add":
            self._handle_invited_add(event)

        elif callback_data == "invited_delete":
            self._handle_invited_delete(event)
        
        else:
            logger.warning("Неизвестный callback: %s", callback_data)
    
    def handle_sse_event(self, event_data: Dict[str, Any]) -> None:
        """
        Обрабатывает событие из SSE (логирование, sync).
        Добавление приглашённых — только через MessageHandler в ответ на команду
        /приглашенные (избегаем повторной записи при получении старых сообщений).
        """
        self.service.process_sse_event(event_data)
    
    def _handle_command(self, event: MessageBotEvent, command: str) -> None:
        """Обрабатывает команду."""
        if command == "start":
            self._handle_start(event)
        
        elif command == "meeting":
            self._handle_meeting_check(event)

        elif command == "attendance":
            self._handle_attendance(event)

        elif command == "invited":
            self._handle_invited(event)

        elif command == "meeting_menu":
            self._handle_meeting_menu(event)

        elif command == "create_meeting":
            self._handle_create_meeting(event)

        elif command == "cancel":
            self._handle_cancel(event)

        elif command == "help":
            self._show_help(event)
    
    def _handle_start(self, event: MessageBotEvent) -> None:
        """Обрабатывает команду /start."""
        fio = self.service.get_user_fio(event.sender_id, event)
        if fio:
            greeting_tpl = self.config.get_message("greeting")
            greeting = greeting_tpl.format(fio=fio) if greeting_tpl else f"Здравствуйте, {fio}!"
        else:
            greeting = self.config.get_message("greeting_anonymous") or "Здравствуйте!"

        if self.service.check_user_allowed(event):
            welcome_part = self.config.get_message("welcome_without_fio") or (
                "📅 Вы приглашены на совещание.\n"
                "Планируете ли вы присутствовать на совещании?"
            )
            # Добавляем информацию о совещании (дата, время, тема)
            meeting_info = self.service.get_meeting_info()
            meeting_details = []
            topic = meeting_info.get("topic")
            if topic:
                meeting_details.append(f"**{topic}**")
            date_str = meeting_info.get("date") or ""
            time_str = meeting_info.get("time") or ""
            if date_str or time_str:
                meeting_details.append(f"🕐 Дата и время: {date_str} {time_str}".strip())
            if meeting_details:
                meeting_info_text = "\n".join(meeting_details)
                welcome_part = f"{welcome_part}\n\n{meeting_info_text}"
            one_message = f"{greeting}\n\n{welcome_part}"
            self.service.ask_attendance(event, message=one_message)
        else:
            one_message = f"{greeting}\n\n{self.config.get_message('not_allowed')}"
            event.reply_text(one_message)
    
    def _handle_meeting_menu(self, event: MessageBotEvent) -> None:
        """Команда /собрание — меню с кнопками: Создать, Изменить, Перенести."""
        self._show_meeting_menu(event)

    def _get_meeting_menu_buttons(self) -> list:
        """
        Формирует кнопки меню собрания.
        При наличии собрания: «Изменить», «Перенести». Иначе: только «Создать».
        """
        has_meeting = bool(self.service.meeting_repo.get_meeting_info())
        if has_meeting:
            return [
                InlineMessageButton(
                    id=2, label="✏️ Изменить",
                    callback_message="✏️ Изменить", callback_data="meeting_edit"
                ),
                InlineMessageButton(
                    id=3, label="📅 Перенести",
                    callback_message="📅 Перенести", callback_data="meeting_move"
                ),
            ]
        return [
            InlineMessageButton(
                id=1, label="✨ Создать",
                callback_message="✨ Создать", callback_data="meeting_create"
            ),
        ]

    def _show_meeting_menu(self, event: MessageBotEvent) -> None:
        """Отправляет меню собрания с кнопками (Создать, Изменить и Перенести при наличии собрания)."""
        message = "📋 **Собрание**\n\nВыберите действие:"
        buttons = self._get_meeting_menu_buttons()
        try:
            event.reply_text_message(MessageRequest(text=message, buttons=buttons))
        except Exception as e:
            logger.error("Ошибка отправки меню собрания: %s", e)
            event.reply_text(message)

    def _handle_edit_meeting(self, event: MessageBotEvent) -> None:
        """
        Редактирование собрания — только для админов.
        Если активного собрания нет — сообщение и кнопки меню.
        Иначе — диалог редактирования (как при создании).
        """
        email = self.service.get_user_email(event)
        if not email:
            event.reply_text(
                "❌ Для изменения собрания необходим email в профиле. "
                "Укажите email в настройках K-Chat."
            )
            return
        if not self.service.meeting_repo.is_admin(email):
            event.reply_text(
                self.config.get_message("create_meeting_not_admin")
                or "❌ Команда доступна только администраторам."
            )
            return
        meeting_info = self.service.meeting_repo.get_meeting_info()
        if not meeting_info:
            message = "ℹ️ Изменять нечего — активных собраний нет.\n\nВыберите действие:"
            buttons = self._get_meeting_menu_buttons()
            try:
                event.reply_text_message(MessageRequest(text=message, buttons=buttons))
            except Exception as e:
                logger.error("Ошибка отправки меню собрания: %s", e)
                event.reply_text(message)
            return
        msg = self.edit_meeting_flow.start(event, meeting_info)
        event.reply_text(msg)

    def _handle_move_meeting(self, event: MessageBotEvent) -> None:
        """
        Перенос собрания — создание нового с копированием приглашённых (status сброшен).
        Только для админов, только при наличии текущего собрания.
        """
        email = self.service.get_user_email(event)
        if not email:
            event.reply_text(
                "❌ Для переноса собрания необходим email в профиле. "
                "Укажите email в настройках K-Chat."
            )
            return
        if not self.service.meeting_repo.is_admin(email):
            event.reply_text(
                self.config.get_message("create_meeting_not_admin")
                or "❌ Команда доступна только администраторам."
            )
            return
        meeting_info = self.service.meeting_repo.get_meeting_info()
        if not meeting_info:
            message = "ℹ️ Переносить нечего — активных собраний нет.\n\nВыберите действие:"
            buttons = self._get_meeting_menu_buttons()
            try:
                event.reply_text_message(MessageRequest(text=message, buttons=buttons))
            except Exception as e:
                logger.error("Ошибка отправки меню собрания: %s", e)
                event.reply_text(message)
            return
        meeting_id = meeting_info.get("meeting_id")
        msg = self.create_meeting_flow.start(
            event,
            move_from_meeting_id=meeting_id,
            move_from_meeting_info=meeting_info,
        )
        event.reply_text(msg)

    def _handle_create_meeting(self, event: MessageBotEvent) -> None:
        """
        Создание собрания — только для админов.
        Запускает пошаговый диалог ввода полей (вызов по /создать_собрание или кнопке Создать).
        Если собрание уже есть — сообщение и предложение «Изменить».
        """
        email = self.service.get_user_email(event)
        if not email:
            event.reply_text(
                "❌ Для создания собрания необходим email в профиле. "
                "Укажите email в настройках K-Chat."
            )
            return
        if not self.service.meeting_repo.is_admin(email):
            event.reply_text(
                self.config.get_message("create_meeting_not_admin")
                or "❌ Команда доступна только администраторам."
            )
            return
        meeting_info = self.service.meeting_repo.get_meeting_info()
        if meeting_info:
            message = (
                "ℹ️ Собрание уже создано.\n\n"
                "Для редактирования используйте кнопку «✏️ Изменить» или «📅 Перенести»."
            )
            buttons = [
                InlineMessageButton(
                    id=2, label="✏️ Изменить",
                    callback_message="✏️ Изменить", callback_data="meeting_edit"
                ),
                InlineMessageButton(
                    id=3, label="📅 Перенести",
                    callback_message="📅 Перенести", callback_data="meeting_move"
                ),
            ]
            try:
                event.reply_text_message(MessageRequest(text=message, buttons=buttons))
            except Exception as e:
                logger.error("Ошибка отправки меню собрания: %s", e)
                event.reply_text(message)
            return
        msg = self.create_meeting_flow.start(event)
        event.reply_text(msg)

    def _handle_cancel(self, event: MessageBotEvent) -> None:
        """Команда /отмена — отмена активного диалога."""
        if self.create_meeting_flow.is_active(event):
            msg = self.create_meeting_flow.cancel(event)
            event.reply_text(msg)
            self._show_help(event)
        elif self.edit_meeting_flow.is_active(event):
            msg = self.edit_meeting_flow.cancel(event)
            event.reply_text(msg)
            self._show_help(event)
        elif self.add_invited_flow.is_active(event):
            msg = self.add_invited_flow.cancel(event)
            event.reply_text(msg)
        elif self.edit_delete_invited_flow.is_active(event):
            msg = self.edit_delete_invited_flow.cancel(event)
            event.reply_text(msg)
            self._handle_invited(event, skip_parse_and_save=True)
        else:
            event.reply_text("Нет активного диалога для отмены.")

    def _handle_meeting_check(self, event: MessageBotEvent) -> None:
        """
        Обрабатывает команду /информация: информация о совещании из БД
        (дата, время, место, цель, ссылка на подключение). Без вопросов и кнопок.
        """
        meeting_info = self.service.get_meeting_info()
        topic = meeting_info.get("topic") or "Совещание"
        date_str = meeting_info.get("date") or ""
        time_str = meeting_info.get("time") or ""
        place = meeting_info.get("place") or ""
        link = meeting_info.get("link") or ""
        url = meeting_info.get("url") or ""

        parts = [f"📅 **{topic}**"]
        if date_str or time_str:
            parts.append(f"🕐 Дата и время: {date_str} {time_str}".strip())
        if place:
            parts.append(f"📍 Место: {place}")
        if link:
            parts.append(f"🔗 Подключение: {link}")
        if url:
            parts.append(f"🌐 Ссылка: {url}")

        message = "\n".join(parts) if len(parts) > 1 else (
            parts[0] if parts else "Информация о совещании не задана."
        )
        event.reply_text(message)

    def _handle_attendance(self, event: MessageBotEvent) -> None:
        """
        Обрабатывает команду /участие: голосование о присутствии (кнопки Да/Нет).
        Только для приглашённых.
        """
        if self.service.check_user_allowed(event):
            message = (
                self.config.get_message("welcome_without_fio")
                or "Планируете ли вы присутствовать на совещании?"
            )
            self.service.ask_attendance(event, message=message)
        else:
            event.reply_text(self.config.get_message("not_allowed"))

    @staticmethod
    def _normalize_fio(fio: str) -> str:
        """Нормализует ФИО для сопоставления: пробелы, регистр."""
        if not fio or not isinstance(fio, str):
            return ""
        return " ".join(fio.strip().split()).lower()

    @staticmethod
    def _answer_is_yes(answer: str) -> bool:
        """Ответ «да»: yes или текст вроде «Да, буду присутствовать»."""
        if not answer:
            return False
        s = answer.strip().lower()
        if s == "yes":
            return True
        if "да" in s and "не смогу" not in s and "нет" not in s:
            return True
        return False

    @staticmethod
    def _answer_is_no(answer: str) -> bool:
        """Ответ «нет»: no или текст вроде «Нет, не смогу присутствовать»."""
        if not answer:
            return False
        s = answer.strip().lower()
        if s == "no":
            return True
        if "нет" in s or "не смогу" in s:
            return True
        return False

    # Разделитель формата: ФИО | email | phone (поддержка " | " и "|")
    INVITED_LINE_SEP = " | "

    @staticmethod
    def _parse_invited_line(line: str) -> Optional[Dict[str, str]]:
        """
        Парсит строку формата: ФИО | email@example.com | +79991234567.
        Телефон может быть пустым: ФИО | email |  или ФИО | email.
        Принимает разделители " | " или "|".

        Returns:
            dict с ключами full_name, email, phone или None если строка невалидна.
        """
        if not line or "|" not in line:
            return None
        # Делим по первому " | " или по "|" (гибкий парсинг)
        if MeetingHandler.INVITED_LINE_SEP in line:
            parts = [p.strip() for p in line.split(MeetingHandler.INVITED_LINE_SEP, 2)]
        else:
            parts = [p.strip() for p in line.split("|", 2)]
        full_name = (parts[0] or "").strip()
        if not full_name:
            return None
        email = (parts[1] if len(parts) > 1 else "").strip()
        phone = (parts[2] if len(parts) > 2 else "").strip()
        return {"full_name": full_name, "email": email or "", "phone": phone or ""}

    @staticmethod
    def _validate_invited_row(row: Dict[str, str]) -> Tuple[bool, Optional[str]]:
        """
        Валидирует запись приглашённого.
        Требуется: ФИО и хотя бы email или телефон.

        Returns:
            (is_valid, error_message)
        """
        full_name = (row.get("full_name") or "").strip()
        email = (row.get("email") or "").strip()
        phone = (row.get("phone") or "").strip()
        if not full_name:
            return False, "Пустое ФИО"
        if not email and not phone:
            return False, "Укажите email или телефон"
        if email and not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            return False, f"Некорректный email: {email}"
        return True, None

    def _parse_invited_list(self, text: str) -> List[Dict[str, str]]:
        """
        Извлекает из текста список приглашённых в формате ФИО | email | phone.
        Каждая строка — один человек. Пропускает невалидные строки.
        """
        result: List[Dict[str, str]] = []
        lines = text.splitlines()
        logger.debug("_parse_invited_list: строк=%d %r", len(lines), lines[:5])
        for line in lines:
            line = line.strip()
            if not line:
                continue
            parsed = self._parse_invited_line(line)
            if parsed:
                valid, err = self._validate_invited_row(parsed)
            else:
                valid, err = False, "не распознано"
            logger.debug(
                "_parse_invited_list: line=%r -> parsed=%s valid=%s err=%s",
                line[:80], parsed, valid, err,
            )
            if parsed and valid:
                result.append(parsed)
        return result

    def _get_invited_buttons(
        self,
        invited: list,
        is_admin: bool,
    ) -> list:
        """
        Формирует кнопки для экрана приглашённых.
        Без приглашённых: «Пригласить». С приглашёнными: «Добавить», «Удалить».
        Только для админов.
        """
        if not is_admin:
            return []
        if not invited:
            return [
                InlineMessageButton(
                    id=1,
                    label="👋 Пригласить",
                    callback_message="👋 Пригласить",
                    callback_data="invited_add",
                ),
            ]
        return [
            InlineMessageButton(
                id=1,
                label="✨ Добавить",
                callback_message="✨ Добавить",
                callback_data="invited_add",
            ),
            InlineMessageButton(
                id=2,
                label="🗑 Удалить",
                callback_message="🗑 Удалить",
                callback_data="invited_delete",
            ),
        ]

    def _handle_invited_add(self, event: MessageBotEvent) -> None:
        """
        Кнопка «Пригласить»/«Добавить» — запуск диалога добавления списка приглашённых.
        """
        meeting_info = self.service.get_meeting_info()
        if not meeting_info:
            event.reply_text(
                "ℹ️ Собраний пока нет.\n\n"
                "📋 /собрание — создать собрание."
            )
            return
        email = self.service.get_user_email(event)
        if not email or not self.service.meeting_repo.is_admin(email):
            event.reply_text(
                self.config.get_message("not_allowed")
                or "❌ Команда доступна только администраторам."
            )
            return
        meeting_id = meeting_info.get("meeting_id")
        msg = self.add_invited_flow.start(event, meeting_id)
        event.reply_text(msg)

    def _handle_invited_delete(self, event: MessageBotEvent) -> None:
        """Кнопка «Удалить» — запрос email и удаление приглашённого."""
        meeting_info = self.service.get_meeting_info()
        if not meeting_info:
            event.reply_text(
                "ℹ️ Собраний пока нет.\n\n"
                "📋 /собрание — создать собрание."
            )
            return
        email = self.service.get_user_email(event)
        if not email or not self.service.meeting_repo.is_admin(email):
            event.reply_text(
                self.config.get_message("not_allowed")
                or "❌ Команда доступна только администраторам."
            )
            return
        meeting_id = meeting_info.get("meeting_id")
        msg = self.edit_delete_invited_flow.start(event, meeting_id)
        event.reply_text(msg)

    def _handle_invited(
        self,
        event: MessageBotEvent,
        skip_parse_and_save: bool = False,
    ) -> None:
        """
        Обрабатывает команду /приглашенные: список приглашённых из БД.
        ✅/❌ — по полю answer в Invited.
        Админы: кнопки Пригласить/Добавить, Изменить, Удалить.
        skip_parse_and_save: True при вызове после add_invited_flow — только показ списка.
        """
        meeting_info = self.service.get_meeting_info()
        if not meeting_info:
            event.reply_text(
                "ℹ️ Собраний пока нет.\n\n"
                "📋 /собрание — создать собрание."
            )
            return

        text = (event.message_text or "").strip()
        text_lower = text.lower()
        meeting_id = meeting_info.get("meeting_id")
        email = self.service.get_user_email(event)
        is_admin = bool(email and self.service.meeting_repo.is_admin(email))
        logger.debug(
            "_handle_invited: meeting_id=%s email=%s is_admin=%s skip=%s text_len=%d",
            meeting_id, email, is_admin, skip_parse_and_save, len(text),
        )

        added_msg = ""
        if not skip_parse_and_save and is_admin and meeting_id:
            parsed = self._parse_invited_list(text)
            logger.debug("_handle_invited: parsed=%d записей", len(parsed))
            if parsed:
                try:
                    added = self.service.meeting_repo.save_invited_batch(
                        meeting_id, parsed
                    )
                    added_msg = (
                        f"✅ **Данные сохранены.**\n\n"
                        f"Добавлено приглашённых: **{added}** чел.\n\n"
                    )
                except Exception as e:
                    logger.exception("Ошибка сохранения приглашённых: %s", e)
                    added_msg = "❌ Ошибка при сохранении в базу данных.\n\n"
            elif "добавить" in text_lower:
                msg = self.add_invited_flow.start(event, meeting_id)
                event.reply_text(msg)
                return

        invited = self.service.get_invited_list()
        dt_display = self.service.get_meeting_datetime_display()
        header = f"👥 **Приглашённые** ({dt_display})\n" if dt_display else "👥 **Приглашённые**\n"
        lines = [header]
        if not invited:
            #lines.append("")
            lines.append("Список пуст.")
        else:
            sorted_invited = sorted(
                invited,
                key=lambda x: ((x.get("full_name") or "").strip() or "—").upper(),
            )
            for i, inv in enumerate(sorted_invited):
                num = f"{i + 1}."
                fio = (inv.get("full_name") or "").strip() or "—"
                contact = inv.get("email") or inv.get("phone") or ""
                answer = inv.get("answer") or ""
                if self._answer_is_yes(answer):
                    icon = "✅ "
                elif self._answer_is_no(answer):
                    icon = "❌ "
                else:
                    icon = ""
                part = f"{num} {icon}{fio}"
                if contact:
                    part += f" — {contact}"
                if answer:
                    part += f" ({answer})"
                lines.append(part)
        full_message = added_msg + "\n".join(lines)

        buttons = self._get_invited_buttons(invited, is_admin)
        if buttons:
            try:
                event.reply_text_message(MessageRequest(text=full_message, buttons=buttons))
            except Exception as e:
                logger.error("Ошибка отправки сообщения с кнопками: %s", e)
                event.reply_text(full_message)
        else:
            event.reply_text(full_message)
    
    def _handle_attendance_answer(
        self,
        event: MessageBotEvent,
        answer: str,
    ) -> None:
        """
        Обрабатывает ответ пользователя о присутствии.
        По образцу kchat-opros: сначала отправляем уведомление пользователю,
        затем сохраняем в таблицу (чтобы пользователь всегда видел ответ).
        """
        button_key = "yes" if answer == "yes" else "no"
        button_config = self.config.get_button(button_key)
        answer_text = (
            button_config.get("answer_text", answer)
            if button_config
            else answer
        )
        message_template = self.config.get_message("answer_success")
        success_message = (
            message_template.format(answer=answer_text)
            if message_template and "{answer}" in message_template
            else message_template or "✅ Данные успешно сохранены."
        )
        error_msg = (
            self.config.get_message("answer_error")
            or "❌ Не удалось сохранить ответ в базу. Попробуйте позже."
        )
        try:
            event.reply_text(success_message)
            group_id = getattr(event, "group_id", None)
            workspace_id = getattr(event, "workspace_id", None)
            # Сохраняем данные пользователя в БД только в момент голосования
            self.service.sync_user_from_event(event)
            saved = self.service.save_answer(
                event.sender_id,
                answer_text,
                group_id=group_id,
                workspace_id=workspace_id,
            )
            if not saved:
                logger.warning(
                    "Ответ не сохранён в таблицу: sender_id=%s",
                    event.sender_id,
                )
                event.reply_text(error_msg)
            else:
                self._show_help(event)
        except Exception as e:
            logger.exception("Ошибка при сохранении ответа: %s", e)
            try:
                event.reply_text(error_msg)
            except Exception:
                logger.exception("Не удалось отправить сообщение об ошибке")
    
    def _show_help(self, event: MessageBotEvent) -> None:
        """Показывает справку. Для админов — без строки /информация."""
        email = self.service.get_user_email(event)
        is_admin = bool(email and self.service.meeting_repo.is_admin(email))
        key = "help_admin" if is_admin else "help"
        message = self.config.get_message(key) or self.config.get_message("help")
        event.reply_text(message)
