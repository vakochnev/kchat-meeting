"""
Обработка команды /приглашенные: список приглашённых, кнопки, пагинация.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

from messenger_bot_api import MessageBotEvent, InlineMessageButton, MessageRequest

from .config_manager import MeetingConfigManager
from .service import MeetingService
from .add_invited_flow import AddInvitedFlow
from .edit_delete_invited_flow import EditDeleteInvitedFlow
from .search_invited_flow import SearchInvitedFlow
from .invited_parser import parse_invited_list
from .schedule_utils import calculate_next_meeting_date, format_date_for_meeting
from config import config

logger = logging.getLogger(__name__)

INVITED_BTN_ADD = 200
INVITED_BTN_DELETE = 201
INVITED_BTN_SEARCH = 202
INVITED_BTN_CREATE_SCHEDULE = 210
INVITED_BTN_CREATE_MANUAL = 211
INVITED_BTN_CREATE_CANCEL = 212


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


def _answer_is_no(answer: str) -> bool:
    """Ответ «нет»: no или текст «Нет, не смогу», «Нет (Больничный)» и т.п."""
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


class InvitedHandler:
    """Обработка списка приглашённых: показ, пагинация, кнопки, add/delete/search."""

    def __init__(
        self,
        service: MeetingService,
        config: MeetingConfigManager,
        add_invited_flow: AddInvitedFlow,
        edit_delete_invited_flow: EditDeleteInvitedFlow,
        search_invited_flow: SearchInvitedFlow,
    ) -> None:
        self.service = service
        self.config = config
        self.add_invited_flow = add_invited_flow
        self.edit_delete_invited_flow = edit_delete_invited_flow
        self.search_invited_flow = search_invited_flow

    def _get_next_schedule_info(self) -> Optional[Dict[str, Any]]:
        """
        Возвращает информацию о ближайшем собрании по расписанию или None.
        Результат: {topic, date_str, time_str, place, link, schedule_config}.
        """
        schedules = config.get_meeting_schedules()
        if not schedules:
            return None
        meeting_cfg = schedules[0]
        schedule = meeting_cfg.get("schedule", {})
        next_dt = calculate_next_meeting_date(schedule)
        if not next_dt:
            return None
        date_str, time_str = format_date_for_meeting(next_dt)
        return {
            "topic": meeting_cfg.get("topic", ""),
            "date_str": date_str,
            "time_str": time_str,
            "place": meeting_cfg.get("place", "") or None,
            "link": meeting_cfg.get("link", "") or None,
            "schedule_config": meeting_cfg,
        }

    def _reply_no_meeting(self, event: MessageBotEvent) -> None:
        """
        Ответ на /приглашенные когда нет активного собрания.
        Админу предлагает создать собрание (по расписанию с кнопками или вручную).
        Обычному пользователю — информативное сообщение.
        """
        email = self.service.get_user_email(event)
        is_admin = bool(email and self.service.meeting_repo.is_admin(email))

        if not is_admin:
            event.reply_text(
                "👥 **Приглашённые**\n\n"
                "Список приглашённых формируется при создании собрания.\n"
                "Сейчас активных собраний нет."
            )
            return

        schedule_info = self._get_next_schedule_info()
        if schedule_info:
            topic = schedule_info["topic"] or "(не указана)"
            date_str = schedule_info["date_str"]
            time_str = schedule_info["time_str"]
            place = schedule_info.get("place")
            link = schedule_info.get("link")

            lines = [
                "👥 **Приглашённые**\n",
                "Список приглашённых формируется при создании собрания.",
                "Сейчас активных собраний нет.\n",
                "📅 **Ближайшее собрание по расписанию:**",
                f"📌 Тема: {topic}",
                f"🕐 Дата и время: {date_str}, {time_str}",
            ]
            if place:
                lines.append(f"📍 Место: {place}")
            if link:
                lines.append(f"🔗 Ссылка: {link}")
            lines.append("")
            lines.append("Создать собрание по расписанию?")

            buttons = [
                InlineMessageButton(
                    id=INVITED_BTN_CREATE_SCHEDULE,
                    label="✨ Создать",
                    callback_message="✨ Создать",
                    callback_data="create_meeting_schedule",
                ),
                InlineMessageButton(
                    id=INVITED_BTN_CREATE_CANCEL,
                    label="❌ Отменить",
                    callback_message="❌ Отменить",
                    callback_data="create_meeting_cancel",
                ),
            ]
            try:
                event.reply_text_message(
                    MessageRequest(text="\n".join(lines), buttons=buttons)
                )
            except Exception as e:
                logger.error("Ошибка отправки предложения создания: %s", e)
                event.reply_text("\n".join(lines))
        else:
            event.reply_text(
                "👥 **Приглашённые**\n\n"
                "Список приглашённых формируется при создании собрания.\n"
                "Сейчас активных собраний нет.\n\n"
                "📋 /собрание — создать собрание"
            )

    def handle_invited(
        self,
        event: MessageBotEvent,
        skip_parse_and_save: bool = False,
        filter_type: Optional[str] = None,
        page: Optional[int] = 1,
    ) -> None:
        """
        Обрабатывает команду /приглашенные: список приглашённых из БД.
        skip_parse_and_save: True при вызове после add_invited_flow — только показ.
        filter_type: None (все), "voted", "not_voted".
        """
        meeting_info = self.service.get_meeting_info()
        if not meeting_info:
            self._reply_no_meeting(event)
            return

        text = (event.message_text or "").strip()
        text_lower = text.lower()
        meeting_id = meeting_info.get("meeting_id")
        email = self.service.get_user_email(event)
        is_admin = bool(email and self.service.meeting_repo.is_admin(email))
        logger.debug(
            "InvitedHandler.handle_invited: meeting_id=%s is_admin=%s skip=%s",
            meeting_id, is_admin, skip_parse_and_save,
        )

        added_msg = ""
        if not skip_parse_and_save and is_admin and meeting_id:
            parsed = parse_invited_list(text)
            logger.debug("InvitedHandler.handle_invited: parsed=%d записей", len(parsed))
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

        if filter_type == "voted":
            invited = [inv for inv in all_invited if inv.get("answer") or ""]
            filter_label = "✅ Проголосовали"
        elif filter_type == "not_voted":
            invited = [
                inv for inv in all_invited
                if not (inv.get("answer") or "").strip()
            ]
            filter_label = "⏳ Не проголосовали"
        else:
            invited = all_invited
            filter_label = None

        dt_display = self.service.get_meeting_datetime_display()
        total_count = len(all_invited)
        filtered_count = len(invited)

        if filter_label:
            header = (
                f"👥 **Приглашённые** — {filter_label} ({dt_display})\n"
                if dt_display
                else f"👥 **Приглашённые** — {filter_label}\n"
            )
        else:
            header = (
                f"👥 **Приглашённые** ({dt_display})\n"
                if dt_display
                else "👥 **Приглашённые**\n"
            )

        lines = [header]
        if filter_label:
            if filter_type == "voted":
                lines.append(f"👥 **Проголосовали:** {filtered_count}")
            elif filter_type == "not_voted":
                lines.append(f"👥 **Не проголосовали:** {filtered_count}")
            else:
                lines.append(f"👥 **Приглашено участников:** {filtered_count}")
        else:
            lines.append(f"👥 **Приглашено участников:** {total_count}")
        lines.append("")

        if not invited:
            lines.append("Список пуст.")
        else:
            if page is not None:
                list_lines, current_page, total_pages = self._format_list_paginated(
                    invited, page=page
                )
                lines.extend(list_lines)
                if total_pages > 1:
                    page_items = []
                    for p in range(1, total_pages + 1):
                        page_items.append(str(p) if p == current_page else f"/{p}")
                    page_items.append("/все")
                    lines.append("")
                    lines.append(f"Страницы: {' '.join(page_items)}")
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
                    if _answer_is_yes(answer):
                        icon = "✅ "
                    elif _answer_is_no(answer):
                        icon = "❌ "
                    elif exists_in_users:
                        icon = "⏳ "
                    else:
                        icon = "⚠️ "
                    part = f"{num} {icon}{fio}"
                    if contact:
                        part += f" — {contact}"
                    if answer:
                        part += f" ({answer})"
                    lines.append(part)
                lines.append("")
                lines.append("❓ /помощь — список команд")

        if is_admin and has_any_invited:
            lines.append("")
            if filter_type is not None:
                lines.append("/все - все приглашенные")
            if filter_type != "not_voted":
                lines.append("/неголосовали - приглашенные без отметки")
            if filter_type != "voted":
                lines.append("/голосовали - приглашенные с отметкой")
        if is_admin:
            lines.append("")
            lines.append("❓ /помощь — список команд")
            lines.append("")
            lines.append("Выберите действие:")

        full_message = added_msg + "\n".join(lines)
        buttons = self.get_buttons(
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

    def _format_list_paginated(
        self, invited_list: List[Dict[str, Any]], page: int = 1
    ) -> Tuple[List[str], int, int]:
        """Форматирует список приглашённых с пагинацией."""
        per_page = self.config.get_invited_per_page()
        total = len(invited_list)
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1
        page = max(1, min(page, total_pages))
        sorted_invited = sorted(
            invited_list,
            key=lambda x: ((x.get("full_name") or "").strip() or "—").upper(),
        )
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        page_items = sorted_invited[start_idx:end_idx]
        lines = []
        for i, inv in enumerate(page_items, start=start_idx + 1):
            name = inv.get("full_name") or "(без ФИО)"
            email = inv.get("email") or ""
            answer = inv.get("answer") or ""
            exists_in_users = bool(inv.get("exists_in_users", False))
            if _answer_is_yes(answer):
                icon = "✅ "
            elif _answer_is_no(answer):
                icon = "❌ "
            elif answer:
                icon = "⏳ "
            else:
                icon = "⏳ " if exists_in_users else "⚠️ "
            part = f"{i}. {icon}{name}"
            if email:
                part += f" — {email}"
            if answer:
                part += f" ({answer})"
            lines.append(part)
        return lines, page, total_pages

    def format_list_paginated(
        self, invited_list: List[Dict[str, Any]], page: int = 1
    ) -> Tuple[List[str], int, int]:
        """Публичный метод для пагинации списка приглашённых (для экрана информации о собрании)."""
        return self._format_list_paginated(invited_list, page=page)

    def format_full_list(self, invited_list: List[Dict[str, Any]]) -> List[str]:
        """Форматирует полный список приглашённых без пагинации (для экрана информации о собрании)."""
        lines = []
        sorted_invited = sorted(
            invited_list,
            key=lambda x: ((x.get("full_name") or "").strip() or "—").upper(),
        )
        for i, inv in enumerate(sorted_invited):
            name = inv.get("full_name") or "(без ФИО)"
            email = inv.get("email") or ""
            answer = inv.get("answer") or ""
            exists_in_users = bool(inv.get("exists_in_users", False))
            if _answer_is_yes(answer):
                icon = "✅ "
            elif _answer_is_no(answer):
                icon = "❌ "
            elif answer:
                icon = "⏳ "
            else:
                icon = "⏳ " if exists_in_users else "⚠️ "
            part = f"{i + 1}. {icon}{name}"
            if email:
                part += f" — {email}"
            if answer:
                part += f" ({answer})"
            lines.append(part)
        return lines

    def get_buttons(
        self,
        invited: list,
        is_admin: bool,
        filter_type: Optional[str] = None,
        has_any_invited: bool = False,
    ) -> list:
        """Формирует кнопки для экрана приглашённых."""
        if not is_admin:
            return []
        if filter_type is not None or has_any_invited or invited:
            return [
                InlineMessageButton(
                    id=INVITED_BTN_ADD,
                    label="✨ Добавить",
                    callback_message="✨ Добавить",
                    callback_data="invited_add",
                ),
                InlineMessageButton(
                    id=INVITED_BTN_DELETE,
                    label="🗑 Удалить",
                    callback_message="🗑 Удалить",
                    callback_data="invited_delete",
                ),
                InlineMessageButton(
                    id=INVITED_BTN_SEARCH,
                    label="🔍 Поиск",
                    callback_message="🔍 Поиск",
                    callback_data="invited_search",
                ),
            ]
        return [
            InlineMessageButton(
                id=INVITED_BTN_ADD,
                label="👋 Пригласить",
                callback_message="👋 Пригласить",
                callback_data="invited_add",
            ),
        ]

    def handle_add(self, event: MessageBotEvent) -> None:
        """Кнопка «Пригласить»/«Добавить» — запуск диалога добавления приглашённых."""
        meeting_info = self.service.get_meeting_info()
        if not meeting_info:
            event.reply_text(
                "ℹ️ Собраний пока нет.\n\n📋 /собрание — создать собрание."
            )
            return
        email = self.service.get_user_email(event)
        if not email or not self.service.meeting_repo.is_admin(email):
            event.reply_text(
                self.config.get_message("not_allowed")
                or "❌ Команда доступна только администраторам."
            )
            return
        msg = self.add_invited_flow.start(event, meeting_info.get("meeting_id"))
        event.reply_text(msg)

    def handle_delete(self, event: MessageBotEvent) -> None:
        """Кнопка «Удалить» — запрос email и удаление приглашённого."""
        meeting_info = self.service.get_meeting_info()
        if not meeting_info:
            event.reply_text(
                "ℹ️ Собраний пока нет.\n\n📋 /собрание — создать собрание."
            )
            return
        email = self.service.get_user_email(event)
        if not email or not self.service.meeting_repo.is_admin(email):
            event.reply_text(
                self.config.get_message("not_allowed")
                or "❌ Команда доступна только администраторам."
            )
            return
        msg = self.edit_delete_invited_flow.start(event, meeting_info.get("meeting_id"))
        event.reply_text(msg)

    def handle_search(self, event: MessageBotEvent) -> None:
        """Кнопка «Поиск» — запрос строки поиска для приглашённых."""
        meeting_info = self.service.get_meeting_info()
        if not meeting_info:
            event.reply_text(
                "ℹ️ Собраний пока нет.\n\n📋 /собрание — создать собрание."
            )
            return
        email = self.service.get_user_email(event)
        if not email or not self.service.meeting_repo.is_admin(email):
            event.reply_text(
                self.config.get_message("not_allowed")
                or "❌ Команда доступна только администраторам."
            )
            return
        msg = self.search_invited_flow.start(event, meeting_info.get("meeting_id"))
        event.reply_text(msg)
