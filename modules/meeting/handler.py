"""
Обработчик событий совещаний.
"""
import logging
from typing import Dict, Any

from messenger_bot_api import MessageBotEvent, InlineMessageButton, MessageRequest

from .service import MeetingService
from .config_manager import MeetingConfigManager
from .create_meeting_flow import CreateMeetingFlow

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
    
    def handle_message(self, event: MessageBotEvent) -> None:
        """Обрабатывает входящее сообщение."""
        if not self.service.check_user_allowed(event):
            event.reply_text(self.config.get_message("not_allowed"))
            return

        text = (event.message_text or "").strip()
        
        if not text:
            return
        
        logger.debug("Сообщение от %s: %s", event.sender_id, text[:50])
        
        text_lower = text.lower()
        command = COMMANDS.get(text_lower)
        if not command and text_lower.startswith("/приглашенные"):
            command = "invited"

        if command:
            if command == "skip" and self.create_meeting_flow.is_active(event):
                msg = self.create_meeting_flow.try_skip(event, self.service.meeting_repo.create_new_meeting)
                event.reply_text(msg[0])
                return
            if command == "skip":
                event.reply_text("Команда /пропустить доступна только для необязательных полей (место, ссылка).")
                return
            if command != "cancel" and self.create_meeting_flow.is_active(event):
                self.create_meeting_flow.cancel(event)
            self._handle_command(event, command)
            return

        # Пользователь в диалоге создания собрания — обрабатываем ввод
        if self.create_meeting_flow.is_active(event):
            msg, done = self.create_meeting_flow.process(
                event, text, self.service.meeting_repo.create_new_meeting
            )
            event.reply_text(msg)
            return

        self._show_help(event)
    
    def handle_callback(self, event: MessageBotEvent) -> None:
        """Обрабатывает callback от кнопки."""
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
            event.reply_text("⏳ Функция «Изменить» в разработке.")

        elif callback_data == "meeting_move":
            event.reply_text("⏳ Функция «Перенести» в разработке.")
        
        else:
            logger.warning("Неизвестный callback: %s", callback_data)
    
    def handle_sse_event(self, event_data: Dict[str, Any]) -> None:
        """
        Обрабатывает событие из SSE.
        
        Args:
            event_data: Данные события из SSE.
        """
        logger.debug("SSE событие получено: %s", event_data.get("type", "unknown"))
        
        # Обрабатываем событие через сервис
        self.service.process_sse_event(event_data)
        
        # Если это событие сообщения, можем проверить пользователя
        event_type = event_data.get("type")
        if event_type == "MESSAGE":
            # Здесь можно добавить логику проверки и опроса
            # Но обычно это делается при команде /start
            pass
    
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
        message = "📋 **Собрание**\n\nВыберите действие:"
        buttons = [
            InlineMessageButton(id=1, label="✨ Создать", callback_message="✨ Создать", callback_data="meeting_create"),
            InlineMessageButton(id=2, label="✏️ Изменить", callback_message="✏️ Изменить", callback_data="meeting_edit"),
            InlineMessageButton(id=3, label="📅 Перенести", callback_message="📅 Перенести", callback_data="meeting_move"),
        ]
        try:
            event.reply_text_message(MessageRequest(text=message, buttons=buttons))
        except Exception as e:
            logger.error("Ошибка отправки меню собрания: %s", e)
            event.reply_text(message)

    def _handle_create_meeting(self, event: MessageBotEvent) -> None:
        """
        Создание собрания — только для админов.
        Запускает пошаговый диалог ввода полей (вызов по /создать_собрание или кнопке Создать).
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
        msg = self.create_meeting_flow.start(event)
        event.reply_text(msg)

    def _handle_cancel(self, event: MessageBotEvent) -> None:
        """Команда /отмена — отмена диалога создания собрания."""
        if self.create_meeting_flow.is_active(event):
            msg = self.create_meeting_flow.cancel(event)
            event.reply_text(msg)
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

    def _handle_invited(self, event: MessageBotEvent) -> None:
        """
        Обрабатывает команду /приглашенные: список приглашённых из БД.
        Отметка по данным из БД: сопоставление по ФИО и дате совещания.
        ✅ если ответ «да», ❌ если «нет»; только у проголосовавших.
        """
        invited = self.service.get_invited_list()
        voted = self.service.get_voted_users()
        vote_by_fio = {}
        vote_by_email = {}
        vote_by_email_local = {}
        vote_by_phone = {}
        for v in voted:
            fio_str = v.get("fio") or ""
            fio_norm = self._normalize_fio(fio_str)
            if fio_norm:
                vote_by_fio[fio_norm] = v.get("answer")
            email_val = (v.get("email") or "").strip().lower()
            if email_val:
                vote_by_email[email_val] = v.get("answer")
                local = email_val.split("@")[0] if "@" in email_val else email_val
                if local:
                    vote_by_email_local[local] = v.get("answer")
            phone_val = (v.get("phone") or "").strip()
            if phone_val:
                vote_by_phone[phone_val] = v.get("answer")
        dt_display = self.service.get_meeting_datetime_display()
        header = f"👥 **Приглашённые** ({dt_display})" if dt_display else "👥 **Приглашённые**"
        lines = [header]
        for inv in invited:
            parts = [
                inv.get("last_name"),
                inv.get("first_name"),
                inv.get("middle_name"),
            ]
            parts = [p.strip() for p in parts if p and str(p).strip()]
            fio = " ".join(parts) if parts else "—"
            contact = inv.get("phone") or inv.get("email") or ""
            fio_norm = self._normalize_fio(fio)
            email_norm = (inv.get("email") or "").strip().lower()
            phone_val = (inv.get("phone") or "").strip()
            email_local = email_norm.split("@")[0] if "@" in email_norm else ""
            answer = (
                (vote_by_fio.get(fio_norm) if fio_norm else None)
                or (vote_by_email.get(email_norm) if email_norm else None)
                or (vote_by_email_local.get(email_local) if email_local else None)
                or (vote_by_phone.get(phone_val) if phone_val else None)
            )
            if answer is None and fio_norm and vote_by_fio:
                for voted_fio, ans in vote_by_fio.items():
                    if voted_fio in fio_norm or fio_norm in voted_fio:
                        answer = ans
                        break
            if self._answer_is_yes(answer or ""):
                icon = "✅ "
            elif self._answer_is_no(answer or ""):
                icon = "❌ "
            else:
                icon = ""
            lines.append(f"• {icon}{fio}" + (f" — {contact}" if contact else ""))
        event.reply_text("\n".join(lines))
    
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
        """Показывает справку."""
        message = self.config.get_message("help")
        event.reply_text(message)
