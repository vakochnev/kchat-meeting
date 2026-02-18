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
from .search_invited_flow import SearchInvitedFlow
from .add_permanent_invited_flow import AddPermanentInvitedFlow
from .edit_delete_permanent_invited_flow import EditDeletePermanentInvitedFlow
from .search_permanent_invited_flow import SearchPermanentInvitedFlow
from .schedule_utils import calculate_next_meeting_date, format_date_for_meeting
from config import config

logger = logging.getLogger(__name__)


# Команды бота
COMMANDS = {
    "/start": "start",
    "/информация": "meeting",
    "/meeting": "meeting",
    "/приглашенные": "invited",
    "/участники": "participants",
    "/собрание": "meeting_menu",
    "собрание": "meeting_menu",  # без слэша (меню K-Chat)
    "собрание создать": "create_meeting",  # меню «Собрание» → «Создать»
    "/создать_собрание": "create_meeting",
    "/create_meeting": "create_meeting",
    "/отмена": "cancel",
    "/отмен": "cancel",
    "/cancel": "cancel",
    "/пропустить": "skip",
    "/skip": "skip",
    "/помощь": "help",
    "/help": "help",
    "/отправить": "send",
    "/неголосовали": "invited_not_voted",
    "/голосовали": "invited_voted",
    "/все": "invited_all",
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
        self.search_invited_flow = SearchInvitedFlow()
        self.add_permanent_invited_flow = AddPermanentInvitedFlow()
        self.edit_delete_permanent_invited_flow = EditDeletePermanentInvitedFlow()
        self.search_permanent_invited_flow = SearchPermanentInvitedFlow()
    
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
        if not command and text_lower.startswith("/участники"):
            command = "participants"
        if not command and text_lower.startswith("/неголосовали"):
            command = "invited_not_voted"
        if not command and text_lower.startswith("/голосовали"):
            command = "invited_voted"
        if not command and text_lower.startswith("/все"):
            command = "invited_all"

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
                if self.search_invited_flow.is_active(event):
                    self.search_invited_flow.cancel(event)
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

        # Ожидание строки поиска для приглашённых
        if self.search_invited_flow.is_active(event):
            meeting_info = self.service.get_meeting_info()
            meeting_id = meeting_info.get("meeting_id") if meeting_info else None
            if meeting_id:
                msg, done = self.search_invited_flow.process(
                    event,
                    text,
                    self.service.meeting_repo.search_invited,
                )
                # Если поиск завершён успешно (done=True) и есть результаты, показываем кнопки
                if done and not msg.startswith("❌"):
                    email = self.service.get_user_email(event)
                    is_admin = bool(email and self.service.meeting_repo.is_admin(email))
                    # Получаем все приглашённые для формирования кнопок
                    all_invited = self.service.get_invited_list()
                    has_any_invited = len(all_invited) > 0
                    buttons = self._get_invited_buttons(
                        all_invited, is_admin, has_any_invited=has_any_invited
                    )
                    if buttons:
                        try:
                            event.reply_text_message(MessageRequest(text=msg, buttons=buttons))
                        except Exception as e:
                            logger.error("Ошибка отправки результатов поиска с кнопками: %s", e)
                            event.reply_text(msg)
                    else:
                        event.reply_text(msg)
                else:
                    event.reply_text(msg)
                return
            else:
                msg = self.search_invited_flow.cancel(event)
                event.reply_text(msg)
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

        # Ожидание email для удаления постоянного участника
        if self.edit_delete_permanent_invited_flow.is_active(event):
            msg, done = self.edit_delete_permanent_invited_flow.process(
                event,
                text,
                self.service.meeting_repo.delete_permanent_invited,
            )
            event.reply_text(msg)
            if done:
                self._handle_participants(event, skip_parse_and_save=True)
            return

        # Ожидание строки поиска для постоянных участников
        if self.search_permanent_invited_flow.is_active(event):
            msg, done = self.search_permanent_invited_flow.process(
                event,
                text,
                self.service.meeting_repo.search_permanent_invited,
            )
            # Если поиск завершён успешно (done=True) и есть результаты, показываем кнопки
            if done and not msg.startswith("❌"):
                email = self.service.get_user_email(event)
                is_admin = bool(email and self.service.meeting_repo.is_admin(email))
                # Получаем всех постоянных участников для формирования кнопок
                all_participants = self.service.meeting_repo.get_permanent_invited_list()
                has_any_participants = len(all_participants) > 0
                buttons = self._get_participants_buttons(
                    all_participants, is_admin, has_any_participants=has_any_participants
                )
                if buttons:
                    try:
                        event.reply_text_message(MessageRequest(text=msg, buttons=buttons))
                    except Exception as e:
                        logger.error("Ошибка отправки результатов поиска с кнопками: %s", e)
                        event.reply_text(msg)
                else:
                    event.reply_text(msg)
            else:
                event.reply_text(msg)
            return

        # Ожидание списка постоянных участников (отдельным сообщением)
        if self.add_permanent_invited_flow.is_active(event):
            def save_permanent(full_name: str, email: str, phone: Optional[str] = None) -> bool:
                return self.service.meeting_repo.save_permanent_invited(full_name, email, phone)
            
            msg, done = self.add_permanent_invited_flow.process(
                event,
                text,
                self._parse_invited_list,
                save_permanent,
            )
            event.reply_text(msg)
            if done:
                self._handle_participants(event, skip_parse_and_save=True)
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
        # Подтверждение события (API может ожидать — без этого клиент «виснет»)
        if hasattr(event, "event_id") and getattr(event, "event_id", None) is not None:
            try:
                event.confirm_event_from_current_group(event.event_id)
            except Exception as e:
                logger.debug("confirm_event: %s", e)

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
        
        # Обработка callback для голосования (meeting_yes, meeting_no, и т.д.)
        if callback_data and callback_data.startswith("meeting_"):
            answer_key = callback_data[len("meeting_"):]
            if answer_key in (
                "yes", "no", "no_sick", "no_business_trip", "no_vacation"
            ):
                self._handle_attendance_answer(event, answer_key)
                return
        
        # Обработка остальных callback
        if callback_data == "meeting_create":
            logger.debug("handle_callback: вызов _handle_create_meeting")
            self._handle_create_meeting(event)
            return

        if callback_data == "meeting_edit":
            self._handle_edit_meeting(event)
            return

        if callback_data == "meeting_move":
            self._handle_move_meeting(event)
            return

        if callback_data == "invited_add":
            self._handle_invited_add(event)
            return

        if callback_data == "invited_delete":
            self._handle_invited_delete(event)
            return

        if callback_data == "invited_search":
            self._handle_invited_search(event)
            return

        if callback_data == "invited_filter_voted":
            self._handle_invited(event, filter_type="voted")
            return

        if callback_data == "invited_filter_not_voted":
            self._handle_invited(event, filter_type="not_voted")
            return

        if callback_data == "invited_filter_all":
            self._handle_invited(event, filter_type=None)
            return

        if callback_data == "participants_add":
            self._handle_participants_add(event)
            return

        if callback_data == "participants_delete":
            self._handle_participants_delete(event)
            return

        if callback_data == "participants_search":
            self._handle_participants_search(event)
            return
        
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

        elif command == "invited":
            self._handle_invited(event)

        elif command == "invited_not_voted":
            self._handle_invited(event, filter_type="not_voted")

        elif command == "invited_voted":
            self._handle_invited(event, filter_type="voted")

        elif command == "invited_all":
            self._handle_invited(event, filter_type=None)

        elif command == "participants":
            # Команда доступна только для админов (проверка уже есть в _handle_participants)
            self._handle_participants(event)

        elif command == "send":
            # Команда доступна только для админов
            self._handle_send(event)

        elif command == "meeting_menu":
            # Команда доступна только для админов
            email = self.service.get_user_email(event)
            is_admin = bool(email and self.service.meeting_repo.is_admin(email))
            if not is_admin:
                event.reply_text(
                    self.config.get_message("not_allowed")
                    or "❌ Команда доступна только администраторам."
                )
                return
            self._handle_meeting_menu(event)

        elif command == "create_meeting":
            self._handle_create_meeting(event)

        elif command == "cancel":
            self._handle_cancel(event)

        elif command == "help":
            self._show_help(event)
    
    def _create_meeting_from_schedule(
        self, event: MessageBotEvent, admin_email: str
    ) -> bool:
        """
        Создаёт новое собрание из настроек расписания для админа.
        Возвращает True если собрание создано, False если ошибка или нет настроек.
        """
        try:
            schedules = config.get_meeting_schedules()
            if not schedules:
                logger.debug("_create_meeting_from_schedule: нет настроек расписания")
                return False
            
            # Берём первое расписание из конфигурации
            meeting_config = schedules[0]
            schedule = meeting_config.get("schedule", {})
            topic = meeting_config.get("topic", "")
            place = meeting_config.get("place", "") or None
            link = meeting_config.get("link", "") or None
            
            # Вычисляем следующую дату собрания
            next_datetime = calculate_next_meeting_date(schedule)
            if not next_datetime:
                logger.warning("_create_meeting_from_schedule: не удалось вычислить дату собрания")
                return False
            
            date_str, time_str = format_date_for_meeting(next_datetime)
            
            # Создаём собрание (постоянные приглашённые добавляются автоматически)
            meeting_id = self.service.meeting_repo.create_new_meeting(
                topic=topic,
                date=date_str,
                time=time_str,
                place=place,
                link=link,
            )
            
            # Получаем информацию о приглашённых
            invited_list = self.service.meeting_repo.get_invited_list(meeting_id)
            invited_count = len(invited_list)
            
            # Формируем сообщение для админа
            message_parts = [
                "✅ **Собрание создано успешно!**",
                "",
                f"📋 **Тема:** {topic or '(не указана)'}",
                f"🕐 **Дата и время:** {date_str} {time_str}",
            ]
            
            if place:
                message_parts.append(f"📍 **Место:** {place}")
            if link:
                message_parts.append(f"🔗 **Ссылка:** {link}")
            
            message_parts.extend([
                "",
                f"👥 **Приглашено участников:** {invited_count}",
            ])
            
            if invited_count > 0:
                message_parts.append("")
                message_parts.append("**Список приглашённых:**")
                sorted_invited = sorted(
                    invited_list,
                    key=lambda x: ((x.get("full_name") or "").strip() or "—").upper(),
                )
                for i, inv in enumerate(sorted_invited[:20], 1):  # Показываем первые 20
                    name = inv.get("full_name") or "(без ФИО)"
                    email = inv.get("email") or ""
                    answer = inv.get("answer") or ""
                    # Явно проверяем exists_in_users, так как это ключевое поле для определения иконки
                    exists_in_users = bool(inv.get("exists_in_users", False))
                    
                    # Определяем иконку статуса
                    if self._answer_is_yes(answer):
                        icon = "✅ "
                    elif self._answer_is_no(answer):
                        icon = "❌ "
                    elif answer:
                        icon = "⏳ "
                    else:
                        # Не проголосовал: проверяем наличие в таблице users
                        if exists_in_users:
                            icon = "⏳ "
                        else:
                            icon = "❓ "
                    
                    part = f"{i}. {icon}{name}"
                    if email:
                        part += f" — {email}"
                    if answer:
                        part += f" ({answer})"
                    message_parts.append(part)
                
                if invited_count > 20:
                    message_parts.append(f"... и ещё {invited_count - 20} участников")
            
            message = "\n".join(message_parts)
            event.reply_text(message)
            
            # Автоматический вывод справки отключён; /помощь вызывается только по команде
            # self._show_help(event)
            
            logger.info(
                "_create_meeting_from_schedule: создано собрание id=%d, приглашено %d участников",
                meeting_id, invited_count
            )
            
            return True
            
        except Exception as e:
            logger.error(
                "_create_meeting_from_schedule: ошибка при создании собрания: %s",
                e, exc_info=True
            )
            event.reply_text(
                "❌ Ошибка при создании собрания из настроек расписания. "
                "Проверьте логи и настройки в config/meeting_settings.yml"
            )
            return False

    def _show_meeting_info_to_admin(self, event: MessageBotEvent, meeting_id: Optional[int] = None) -> None:
        """
        Показывает информацию о собрании админу: детали собрания и список приглашённых.
        """
        if meeting_id:
            meeting_info = self.service.meeting_repo.get_meeting_info_by_id(meeting_id)
            invited_list = self.service.meeting_repo.get_invited_list(meeting_id)
        else:
            meeting_info = self.service.get_meeting_info()
            invited_list = self.service.get_invited_list()
        
        if not meeting_info:
            event.reply_text("❌ Информация о собрании не найдена.")
            return
        
        topic = meeting_info.get("topic") or "Совещание"
        date_str = meeting_info.get("date") or ""
        time_str = meeting_info.get("time") or ""
        place = meeting_info.get("place") or ""
        link = meeting_info.get("link") or ""
        
        message_parts = [
            "📅 **Собрание уже запланировано**",
            "",
            f"📋 **{topic}**",
        ]
        
        if date_str or time_str:
            message_parts.append(f"🕐 **Дата и время:** {date_str} {time_str}".strip())
        if place:
            message_parts.append(f"📍 **Место:** {place}")
        if link:
            message_parts.append(f"🔗 **Ссылка:** {link}")
        
        invited_count = len(invited_list)
        message_parts.extend([
            "",
            f"👥 **Приглашено участников:** {invited_count}",
        ])
        
        if invited_count > 0:
            message_parts.append("")
            message_parts.append("**Список приглашённых:**")
            sorted_invited = sorted(
                invited_list,
                key=lambda x: ((x.get("full_name") or "").strip() or "—").upper(),
            )
            for i, inv in enumerate(sorted_invited[:20], 1):  # Показываем первые 20
                name = inv.get("full_name") or "(без ФИО)"
                email = inv.get("email") or ""
                answer = inv.get("answer") or ""
                # Явно проверяем exists_in_users, так как это ключевое поле для определения иконки
                exists_in_users = bool(inv.get("exists_in_users", False))
                
                logger.info(
                    "_show_meeting_info_to_admin: invited name='%s' email='%s' answer='%s' exists_in_users=%s (type=%s)",
                    name, email, answer, exists_in_users, type(inv.get("exists_in_users"))
                )
                
                # Определяем иконку статуса
                if self._answer_is_yes(answer):
                    icon = "✅ "
                elif self._answer_is_no(answer):
                    icon = "❌ "
                elif answer:
                    icon = "⏳ "
                else:
                    # Не проголосовал: проверяем наличие в таблице users
                    if exists_in_users:
                        icon = "⏳ "
                    else:
                        icon = "❓ "
                        logger.info(
                            "_show_meeting_info_to_admin: пользователь '%s' (%s) не найден в users, используем ❓",
                            name, email
                        )
                
                part = f"{i}. {icon}{name}"
                if email:
                    part += f" — {email}"
                if answer:
                    part += f" ({answer})"
                message_parts.append(part)
            
            if invited_count > 20:
                message_parts.append(f"... и ещё {invited_count - 20} участников")
        
        message = "\n".join(message_parts)
        event.reply_text(message)
        
        # Автоматический вывод справки отключён; /помощь вызывается только по команде
        # self._show_help(event)

    def _handle_start(self, event: MessageBotEvent) -> None:
        """Обрабатывает команду /start."""
        fio = self.service.get_user_fio(event.sender_id, event)
        if fio:
            greeting_tpl = self.config.get_message("greeting")
            greeting = greeting_tpl.format(fio=fio) if greeting_tpl else f"Здравствуйте, {fio}!"
        else:
            greeting = self.config.get_message("greeting_anonymous") or "Здравствуйте!"

        # Проверяем, является ли пользователь админом
        email = self.service.get_user_email(event)
        is_admin = email and self.service.meeting_repo.is_admin(email)
        
        # Если админ - обрабатываем отдельно
        if is_admin:
            existing_meeting = self.service.meeting_repo.get_active_meeting()
            if not existing_meeting:
                # Пытаемся создать собрание из настроек
                meeting_created = self._create_meeting_from_schedule(event, email)
                if meeting_created:
                    # Информация о созданном собрании уже отправлена в _create_meeting_from_schedule
                    return
                else:
                    # Не удалось создать собрание - показываем приветствие
                    event.reply_text(f"{greeting}\n\n⚠️ Не удалось создать собрание из настроек расписания.")
                    return
            else:
                # Собрание уже существует - показываем информацию о нём
                self._show_meeting_info_to_admin(event)
                return
        
        # Для не-админов: проверяем право голосования (только приглашённые)
        if self.service.check_user_can_vote(event):
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
        elif self.service.check_user_allowed(event):
            # Приглашённый, но не может голосовать (например, уже проголосовал)
            one_message = f"{greeting}\n\n{self.config.get_message('not_allowed')}"
            event.reply_text(one_message)
        else:
            one_message = f"{greeting}\n\n{self.config.get_message('not_allowed')}"
            event.reply_text(one_message)
    
    def _handle_meeting_menu(self, event: MessageBotEvent) -> None:
        """Команда /собрание — меню с кнопками: Создать, Изменить, Перенести."""
        self._show_meeting_menu(event)

    # ID кнопок меню собрания (100+) — не конфликтуют с кнопками голосования (1-5)
    _MEETING_BTN_CREATE = 100
    _MEETING_BTN_EDIT = 101
    _MEETING_BTN_MOVE = 102

    def _get_meeting_menu_buttons(self) -> list:
        """
        Формирует кнопки меню собрания.
        При наличии собрания: «Изменить», «Перенести». Иначе: только «Создать».
        """
        has_meeting = bool(self.service.meeting_repo.get_meeting_info())
        if has_meeting:
            return [
                InlineMessageButton(
                    id=self._MEETING_BTN_EDIT,
                    label="✏️ Изменить",
                    callback_message="✏️ Изменить",
                    callback_data="meeting_edit",
                ),
                InlineMessageButton(
                    id=self._MEETING_BTN_MOVE,
                    label="📅 Перенести",
                    callback_message="📅 Перенести",
                    callback_data="meeting_move",
                ),
            ]
        return [
            InlineMessageButton(
                id=self._MEETING_BTN_CREATE,
                label="✨ Создать",
                callback_message="✨ Создать",
                callback_data="meeting_create",
            ),
        ]

    def _show_meeting_menu(self, event: MessageBotEvent) -> None:
        """Отправляет меню собрания с кнопками (Создать, Изменить и Перенести при наличии собрания)."""
        message_parts = ["📋 **Собрание**"]
        
        # Добавляем информацию о текущем собрании
        meeting_info = self.service.get_meeting_info()
        if meeting_info:
            topic = meeting_info.get("topic")
            date_str = meeting_info.get("date") or ""
            time_str = meeting_info.get("time") or ""
            place = meeting_info.get("place") or ""
            link = meeting_info.get("link") or ""
            
            if topic:
                message_parts.append(f"📋 **Тема:** {topic}")
            if date_str or time_str:
                message_parts.append(f"🕐 **Дата и время:** {date_str} {time_str}".strip())
            if place:
                message_parts.append(f"📍 **Место:** {place}")
            if link:
                message_parts.append(f"🔗 **Ссылка:** {link}")
        
        message_parts.append("")
        message_parts.append("❓ /помощь — список команд")
        message_parts.append("\nВыберите действие:")
        
        message = "\n".join(message_parts)
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
            message = "ℹ️ Изменять нечего — активных собраний нет.\n\n❓ /помощь — список команд\n\nВыберите действие:"
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
            message = "ℹ️ Переносить нечего — активных собраний нет.\n\n❓ /помощь — список команд\n\nВыберите действие:"
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
        logger.debug("_handle_create_meeting: начало, sender_id=%s", event.sender_id)
        try:
            email = self.service.get_user_email(event)
            logger.debug("_handle_create_meeting: email=%s", email)
            if not email:
                logger.debug("_handle_create_meeting: нет email, отправка сообщения")
                event.reply_text(
                    "❌ Для создания собрания необходим email в профиле. "
                    "Укажите email в настройках K-Chat."
                )
                return
            is_admin = self.service.meeting_repo.is_admin(email)
            logger.debug("_handle_create_meeting: is_admin=%s", is_admin)
            if not is_admin:
                logger.debug("_handle_create_meeting: не админ, отправка сообщения")
                event.reply_text(
                    self.config.get_message("create_meeting_not_admin")
                    or "❌ Команда доступна только администраторам."
                )
                return
            meeting_info = self.service.meeting_repo.get_meeting_info()
            logger.debug("_handle_create_meeting: meeting_info=%s", bool(meeting_info))
            if meeting_info:
                logger.debug("_handle_create_meeting: собрание уже есть, отправка меню")
                message = (
                    "ℹ️ Собрание уже создано.\n\n"
                    "Для редактирования используйте кнопку «✏️ Изменить» или «📅 Перенести».\n\n"
                    "❓ /помощь — список команд"
                )
                buttons = self._get_meeting_menu_buttons()
                try:
                    event.reply_text_message(MessageRequest(text=message, buttons=buttons))
                    logger.debug("_handle_create_meeting: меню отправлено успешно")
                except Exception as e:
                    logger.error("Ошибка отправки меню собрания: %s", e, exc_info=True)
                    event.reply_text(message)
                return
            logger.debug("_handle_create_meeting: запуск create_meeting_flow.start")
            msg = self.create_meeting_flow.start(event)
            logger.debug("_handle_create_meeting: получен ответ от flow, отправка сообщения")
            event.reply_text(msg)
            logger.debug("_handle_create_meeting: завершено")
        except Exception as e:
            logger.exception("Ошибка в _handle_create_meeting: %s", e)
            try:
                event.reply_text("❌ Произошла ошибка при создании собрания. Попробуйте позже.")
            except Exception:
                pass

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
        elif self.add_permanent_invited_flow.is_active(event):
            msg = self.add_permanent_invited_flow.cancel(event)
            event.reply_text(msg)
        elif self.edit_delete_permanent_invited_flow.is_active(event):
            msg = self.edit_delete_permanent_invited_flow.cancel(event)
            event.reply_text(msg)
            self._handle_participants(event, skip_parse_and_save=True)
        elif self.search_permanent_invited_flow.is_active(event):
            msg = self.search_permanent_invited_flow.cancel(event)
            event.reply_text(msg)
        elif self.search_invited_flow.is_active(event):
            msg = self.search_invited_flow.cancel(event)
            event.reply_text(msg)
        else:
            # Нет активного диалога - выводим информативное сообщение
            event.reply_text(
                "ℹ️ Нет активного диалога для отмены.\n\n"
                "Команда /отмена используется для выхода из:\n"
                "• создания или редактирования собрания\n"
                "• добавления приглашённых или участников\n"
                "• поиска пользователей"
            )

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
        
        # Выводим справку после информации
        self._show_help(event)

    def _handle_attendance(self, event: MessageBotEvent) -> None:
        """
        Обрабатывает команду /участие: голосование о присутствии (кнопки Да/Нет).
        Только для приглашённых (админы не могут голосовать).
        """
        if self.service.check_user_can_vote(event):
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
        """
        Ответ «нет»: no или текст «Нет, не смогу», «Нет (Больничный)» и т.п.
        """
        if not answer:
            return False
        s = answer.strip().lower()
        if s == "no":
            return True
        if "нет" in s or "не смогу" in s:
            return True
        if any(x in s for x in ("больничный", "командировка", "отпуск")):
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

    # ID кнопок приглашённых (200+) — не конфликтуют с другими кнопками
    _INVITED_BTN_ADD = 200
    _INVITED_BTN_DELETE = 201
    _INVITED_BTN_SEARCH = 202
    _INVITED_BTN_NOT_VOTED = 203
    _INVITED_BTN_VOTED = 204
    _INVITED_BTN_ALL = 205

    def _get_invited_buttons(
        self,
        invited: list,
        is_admin: bool,
        filter_type: Optional[str] = None,
        has_any_invited: bool = False,
    ) -> list:
        """
        Формирует кнопки для экрана приглашённых.
        Без приглашённых и без фильтра: «Пригласить».
        С приглашёнными или при активном фильтре: основные кнопки (Добавить, Удалить, Поиск, фильтры).
        Только для админов.
        filter_type: None (все), "voted" (проголосовали), "not_voted" (не проголосовали).
        has_any_invited: есть ли вообще приглашённые в базе (до фильтрации).
        """
        if not is_admin:
            return []
        
        # Если есть активный фильтр или есть приглашённые в базе — показываем основные кнопки
        if filter_type is not None or has_any_invited or invited:
            buttons = [
                InlineMessageButton(
                    id=self._INVITED_BTN_ADD,
                    label="✨ Добавить",
                    callback_message="✨ Добавить",
                    callback_data="invited_add",
                ),
                InlineMessageButton(
                    id=self._INVITED_BTN_DELETE,
                    label="🗑 Удалить",
                    callback_message="🗑 Удалить",
                    callback_data="invited_delete",
                ),
                InlineMessageButton(
                    id=self._INVITED_BTN_SEARCH,
                    label="🔍 Поиск",
                    callback_message="🔍 Поиск",
                    callback_data="invited_search",
                ),
            ]
            # Кнопки фильтрации убраны — теперь команды в тексте сообщения
            # Фильтры доступны через команды /Все, /Не проголосовали и /Проголосовали
            return buttons
        
        # Если нет приглашённых и нет фильтра — показываем только "Пригласить"
        return [
            InlineMessageButton(
                id=self._INVITED_BTN_ADD,
                label="👋 Пригласить",
                callback_message="👋 Пригласить",
                callback_data="invited_add",
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

    def _handle_invited_search(self, event: MessageBotEvent) -> None:
        """Кнопка «Поиск» — запрос строки поиска для фильтрации приглашённых."""
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
        msg = self.search_invited_flow.start(event, meeting_id)
        event.reply_text(msg)

    def _handle_invited(
        self,
        event: MessageBotEvent,
        skip_parse_and_save: bool = False,
        filter_type: Optional[str] = None,
    ) -> None:
        """
        Обрабатывает команду /приглашенные: список приглашённых из БД.
        ✅/❌ — по полю answer в Invited.
        Админы: кнопки Пригласить/Добавить, Удалить, фильтры.
        skip_parse_and_save: True при вызове после add_invited_flow — только показ списка.
        filter_type: None (все), "voted" (проголосовали), "not_voted" (не проголосовали).
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

        all_invited = self.service.get_invited_list()
        has_any_invited = len(all_invited) > 0
        
        # Фильтрация по статусу голосования
        if filter_type == "voted":
            invited = [inv for inv in all_invited if inv.get("answer") or ""]
            filter_label = "✅ Проголосовали"
        elif filter_type == "not_voted":
            invited = [inv for inv in all_invited if not (inv.get("answer") or "").strip()]
            filter_label = "⏳ Не проголосовали"
        else:
            invited = all_invited
            filter_label = None
        
        dt_display = self.service.get_meeting_datetime_display()
        if filter_label:
            header = f"👥 **Приглашённые** — {filter_label} ({dt_display})\n" if dt_display else f"👥 **Приглашённые** — {filter_label}\n"
        else:
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
                exists_in_users = inv.get("exists_in_users", False)
                if self._answer_is_yes(answer):
                    icon = "✅ "
                elif self._answer_is_no(answer):
                    icon = "❌ "
                else:
                    # Не проголосовал: проверяем наличие в таблице users
                    if exists_in_users:
                        icon = "⏳ "
                    else:
                        icon = "❓ "
                part = f"{num} {icon}{fio}"
                if contact:
                    part += f" — {contact}"
                if answer:
                    part += f" ({answer})"
                lines.append(part)
        
        # Добавляем команды фильтрации в текст сообщения (только для админов)
        if is_admin and has_any_invited:
            # Добавляем пустую строку перед командами фильтрации
            lines.append("")
            # Если активен фильтр, показываем команду "Все"
            if filter_type is not None:
                lines.append("/все - все приглашенные")
            # Показываем команды фильтров, которые не активны
            if filter_type != "not_voted":
                lines.append("/неголосовали - приглашенные без отметки")
            if filter_type != "voted":
                lines.append("/голосовали - приглашенные с отметкой")
            # Добавляем команду помощи
            lines.append("/помощь - доступные команды")
        
        # Добавляем "Выберите действие:" перед кнопками (только для админов)
        if is_admin:
            lines.append("")
            lines.append("Выберите действие:")
        
        full_message = added_msg + "\n".join(lines)

        buttons = self._get_invited_buttons(
            invited, is_admin, filter_type=filter_type, has_any_invited=has_any_invited
        )
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
        answer: ключ кнопки (yes, no, no_sick, no_business_trip, no_vacation).
        Только для приглашённых (админы не могут голосовать).
        """
        # Проверяем право голосования (админы не могут голосовать)
        if not self.service.check_user_can_vote(event):
            event.reply_text(
                self.config.get_message("not_allowed")
                or "❌ Голосование доступно только приглашённым участникам."
            )
            return
        
        button_config = self.config.get_button(answer)
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
    
    # ID кнопок постоянных участников (300+) — не конфликтуют с другими кнопками
    _PARTICIPANTS_BTN_ADD = 300
    _PARTICIPANTS_BTN_DELETE = 301
    _PARTICIPANTS_BTN_SEARCH = 302

    def _get_participants_buttons(
        self,
        participants: list,
        is_admin: bool,
        has_any_participants: bool = False,
    ) -> list:
        """
        Формирует кнопки для экрана постоянных участников.
        Только для админов.
        """
        if not is_admin:
            return []
        
        # Если есть участники — показываем основные кнопки
        if has_any_participants or participants:
            return [
                InlineMessageButton(
                    id=self._PARTICIPANTS_BTN_ADD,
                    label="✨ Добавить",
                    callback_message="✨ Добавить",
                    callback_data="participants_add",
                ),
                InlineMessageButton(
                    id=self._PARTICIPANTS_BTN_DELETE,
                    label="🗑 Удалить",
                    callback_message="🗑 Удалить",
                    callback_data="participants_delete",
                ),
                InlineMessageButton(
                    id=self._PARTICIPANTS_BTN_SEARCH,
                    label="🔍 Поиск",
                    callback_message="🔍 Поиск",
                    callback_data="participants_search",
                ),
            ]
        
        # Если нет участников — показываем только "Добавить"
        return [
            InlineMessageButton(
                id=self._PARTICIPANTS_BTN_ADD,
                label="✨ Добавить",
                callback_message="✨ Добавить",
                callback_data="participants_add",
            ),
        ]

    def _handle_participants(
        self,
        event: MessageBotEvent,
        skip_parse_and_save: bool = False,
    ) -> None:
        """
        Обрабатывает команду /участники: список постоянных участников из БД.
        Только для админов.
        """
        email = self.service.get_user_email(event)
        is_admin = bool(email and self.service.meeting_repo.is_admin(email))
        
        if not is_admin:
            event.reply_text(
                self.config.get_message("not_allowed")
                or "❌ Команда доступна только администраторам."
            )
            return

        text = (event.message_text or "").strip()
        text_lower = text.lower()
        
        added_msg = ""
        if not skip_parse_and_save and is_admin:
            parsed = self._parse_invited_list(text)
            logger.debug("_handle_participants: parsed=%d записей", len(parsed))
            if parsed:
                try:
                    added_count = 0
                    updated_count = 0
                    for row in parsed:
                        full_name = row.get("full_name") or ""
                        email_val = row.get("email") or ""
                        phone = row.get("phone")
                        if not email_val:
                            continue
                        is_new = self.service.meeting_repo.save_permanent_invited(
                            full_name, email_val, phone
                        )
                        if is_new:
                            added_count += 1
                        else:
                            updated_count += 1
                    
                    parts = ["✅ **Данные сохранены.**"]
                    if added_count > 0:
                        parts.append(f"\nДобавлено: **{added_count}** чел.")
                    if updated_count > 0:
                        parts.append(f"Обновлено: **{updated_count}** чел.")
                    added_msg = "\n".join(parts) + "\n\n"
                except Exception as e:
                    logger.exception("Ошибка сохранения постоянных участников: %s", e)
                    added_msg = "❌ Ошибка при сохранении в базу данных.\n\n"
            elif "добавить" in text_lower:
                msg = self.add_permanent_invited_flow.start(event)
                event.reply_text(msg)
                return

        all_participants = self.service.meeting_repo.get_permanent_invited_list()
        has_any_participants = len(all_participants) > 0
        
        header = "👥 **Постоянные участники**\n"
        lines = [header]
        if not all_participants:
            lines.append("Список пуст.")
        else:
            sorted_participants = sorted(
                all_participants,
                key=lambda x: ((x.get("full_name") or "").strip() or "—").upper(),
            )
            for i, participant in enumerate(sorted_participants):
                num = f"{i + 1}."
                fio = (participant.get("full_name") or "").strip() or "—"
                contact = participant.get("email") or participant.get("phone") or ""
                part = f"{num} {fio}"
                if contact:
                    part += f" — {contact}"
                lines.append(part)
        
        # Добавляем команду помощи и текст перед кнопками (только для админов)
        if is_admin:
            lines.append("")
            lines.append("/помощь - доступные команды")
            lines.append("")
            lines.append("Выберите действие:")
        
        full_message = added_msg + "\n".join(lines)

        buttons = self._get_participants_buttons(
            all_participants, is_admin, has_any_participants=has_any_participants
        )
        if buttons:
            try:
                event.reply_text_message(MessageRequest(text=full_message, buttons=buttons))
            except Exception as e:
                logger.error("Ошибка отправки сообщения с кнопками: %s", e)
                event.reply_text(full_message)
        else:
            event.reply_text(full_message)

    def _handle_participants_add(self, event: MessageBotEvent) -> None:
        """Кнопка «Добавить» — запуск диалога добавления постоянных участников."""
        email = self.service.get_user_email(event)
        if not email or not self.service.meeting_repo.is_admin(email):
            event.reply_text(
                self.config.get_message("not_allowed")
                or "❌ Команда доступна только администраторам."
            )
            return
        msg = self.add_permanent_invited_flow.start(event)
        event.reply_text(msg)

    def _handle_participants_delete(self, event: MessageBotEvent) -> None:
        """Кнопка «Удалить» — запуск диалога удаления постоянного участника."""
        email = self.service.get_user_email(event)
        if not email or not self.service.meeting_repo.is_admin(email):
            event.reply_text(
                self.config.get_message("not_allowed")
                or "❌ Команда доступна только администраторам."
            )
            return
        msg = self.edit_delete_permanent_invited_flow.start(event)
        event.reply_text(msg)

    def _handle_participants_search(self, event: MessageBotEvent) -> None:
        """Кнопка «Поиск» — запрос строки поиска для фильтрации постоянных участников."""
        email = self.service.get_user_email(event)
        if not email or not self.service.meeting_repo.is_admin(email):
            event.reply_text(
                self.config.get_message("not_allowed")
                or "❌ Команда доступна только администраторам."
            )
            return
        msg = self.search_permanent_invited_flow.start(event)
        event.reply_text(msg)

    def _handle_send(self, event: MessageBotEvent) -> None:
        """
        Обрабатывает команду /отправить: отправка уведомлений о собрании.
        Только для админов. Пока в разработке.
        """
        email = self.service.get_user_email(event)
        if not email or not self.service.meeting_repo.is_admin(email):
            event.reply_text(
                self.config.get_message("not_allowed")
                or "❌ Команда доступна только администраторам."
            )
            return
        
        meeting_info = self.service.get_meeting_info()
        if not meeting_info:
            event.reply_text(
                "ℹ️ Собраний пока нет.\n\n"
                "📋 /собрание — создать собрание."
            )
            return
        
        # Пока функционал в разработке
        event.reply_text(
            "🚧 **Отправка уведомлений**\n\n"
            "⚠️ Функционал находится в разработке.\n\n"
            "В будущем здесь будет возможность отправки уведомлений о собрании:\n"
            "📧 по электронной почте\n"
            "💬 в чат пользователям K-Chat"
        )

    def _show_help(self, event: MessageBotEvent) -> None:
        """Показывает справку. Для админов — без строки /информация."""
        email = self.service.get_user_email(event)
        is_admin = bool(email and self.service.meeting_repo.is_admin(email))
        key = "help_admin" if is_admin else "help"
        message = self.config.get_message(key) or self.config.get_message("help")
        event.reply_text(message)
