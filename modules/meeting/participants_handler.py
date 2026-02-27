"""
Обработка команды /участники: список постоянных участников, кнопки, пагинация.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

from messenger_bot_api import MessageBotEvent, InlineMessageButton, MessageRequest

from .config_manager import MeetingConfigManager
from .service import MeetingService
from .user_context import UserContextStore
from .add_permanent_invited_flow import AddPermanentInvitedFlow
from .edit_delete_permanent_invited_flow import EditDeletePermanentInvitedFlow
from .search_permanent_invited_flow import SearchPermanentInvitedFlow
from .invited_parser import parse_invited_list

logger = logging.getLogger(__name__)

PARTICIPANTS_BTN_ADD = 300
PARTICIPANTS_BTN_DELETE = 301
PARTICIPANTS_BTN_SEARCH = 302


class ParticipantsHandler:
    """Обработка списка постоянных участников: показ, пагинация, кнопки, add/delete/search."""

    def __init__(
        self,
        service: MeetingService,
        config: MeetingConfigManager,
        user_context: UserContextStore,
        add_flow: AddPermanentInvitedFlow,
        delete_flow: EditDeletePermanentInvitedFlow,
        search_flow: SearchPermanentInvitedFlow,
    ) -> None:
        self.service = service
        self.config = config
        self._ctx = user_context
        self.add_flow = add_flow
        self.delete_flow = delete_flow
        self.search_flow = search_flow

    def handle_participants(
        self,
        event: MessageBotEvent,
        skip_parse_and_save: bool = False,
        page: Optional[int] = 1,
    ) -> None:
        """
        Обрабатывает команду /участники: список постоянных участников из БД.
        Только для админов.
        """
        self._ctx.switch_to_participants(getattr(event, "sender_id", None))

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
            parsed = parse_invited_list(text)
            logger.debug("ParticipantsHandler: parsed=%d записей", len(parsed))
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
                msg = self.add_flow.start(event)
                event.reply_text(msg)
                return

        all_participants = self.service.meeting_repo.get_permanent_invited_list()
        has_any_participants = len(all_participants) > 0

        header = "👥 **Постоянные участники**\n"
        lines = [header]

        total_count = len(all_participants)
        lines.append(f"👥 **Участников:** {total_count}")
        lines.append("")

        if not all_participants:
            lines.append("Список пуст.")
        else:
            if page is not None:
                list_lines, current_page, total_pages = self._format_list_paginated(
                    all_participants, page=page
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
                lines.extend(self._format_full_list(all_participants))

        if is_admin:
            lines.append("")
            lines.append("/помощь - доступные команды")
            lines.append("")
            lines.append("Выберите действие:")

        full_message = added_msg + "\n".join(lines)

        buttons = self.get_buttons(
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

    def _format_list_paginated(
        self, participants_list: List[Dict[str, Any]], page: int = 1
    ) -> Tuple[List[str], int, int]:
        """Форматирует список постоянных участников с пагинацией."""
        per_page = self.config.get_invited_per_page()
        total = len(participants_list)
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1
        page = max(1, min(page, total_pages))
        sorted_participants = sorted(
            participants_list,
            key=lambda x: ((x.get("full_name") or "").strip() or "—").upper(),
        )
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        page_items = sorted_participants[start_idx:end_idx]
        lines = []
        for i, participant in enumerate(page_items, start=start_idx + 1):
            fio = (participant.get("full_name") or "").strip() or "—"
            contact = participant.get("email") or participant.get("phone") or ""
            part = f"{i}. {fio}"
            if contact:
                part += f" — {contact}"
            lines.append(part)
        return lines, page, total_pages

    @staticmethod
    def _format_full_list(participants_list: List[Dict[str, Any]]) -> List[str]:
        """Форматирует полный список участников без пагинации."""
        lines = []
        sorted_participants = sorted(
            participants_list,
            key=lambda x: ((x.get("full_name") or "").strip() or "—").upper(),
        )
        for i, participant in enumerate(sorted_participants):
            fio = (participant.get("full_name") or "").strip() or "—"
            contact = participant.get("email") or participant.get("phone") or ""
            part = f"{i + 1}. {fio}"
            if contact:
                part += f" — {contact}"
            lines.append(part)
        return lines

    def get_buttons(
        self,
        participants: list,
        is_admin: bool,
        has_any_participants: bool = False,
    ) -> list:
        """Формирует кнопки для экрана постоянных участников."""
        if not is_admin:
            return []
        if has_any_participants or participants:
            return [
                InlineMessageButton(
                    id=PARTICIPANTS_BTN_ADD,
                    label="✨ Добавить",
                    callback_message="✨ Добавить",
                    callback_data="participants_add",
                ),
                InlineMessageButton(
                    id=PARTICIPANTS_BTN_DELETE,
                    label="🗑 Удалить",
                    callback_message="🗑 Удалить",
                    callback_data="participants_delete",
                ),
                InlineMessageButton(
                    id=PARTICIPANTS_BTN_SEARCH,
                    label="🔍 Поиск",
                    callback_message="🔍 Поиск",
                    callback_data="participants_search",
                ),
            ]
        return [
            InlineMessageButton(
                id=PARTICIPANTS_BTN_ADD,
                label="✨ Добавить",
                callback_message="✨ Добавить",
                callback_data="participants_add",
            ),
        ]

    def handle_add(self, event: MessageBotEvent) -> None:
        """Кнопка «Добавить» — запуск диалога добавления постоянных участников."""
        email = self.service.get_user_email(event)
        if not email or not self.service.meeting_repo.is_admin(email):
            event.reply_text(
                self.config.get_message("not_allowed")
                or "❌ Команда доступна только администраторам."
            )
            return
        msg = self.add_flow.start(event)
        event.reply_text(msg)

    def handle_delete(self, event: MessageBotEvent) -> None:
        """Кнопка «Удалить» — запуск диалога удаления постоянного участника."""
        email = self.service.get_user_email(event)
        if not email or not self.service.meeting_repo.is_admin(email):
            event.reply_text(
                self.config.get_message("not_allowed")
                or "❌ Команда доступна только администраторам."
            )
            return
        msg = self.delete_flow.start(event)
        event.reply_text(msg)

    def handle_search(self, event: MessageBotEvent) -> None:
        """Кнопка «Поиск» — запрос строки поиска для постоянных участников."""
        email = self.service.get_user_email(event)
        if not email or not self.service.meeting_repo.is_admin(email):
            event.reply_text(
                self.config.get_message("not_allowed")
                or "❌ Команда доступна только администраторам."
            )
            return
        msg = self.search_flow.start(event)
        event.reply_text(msg)
