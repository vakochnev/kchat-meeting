"""
Хранилище данных приглашённых (Invited).
Работает с объединённой таблицей invited (список + ответы).
"""
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select

from db.models import Invited
from db.session import get_session_context

logger = logging.getLogger(__name__)


class MeetingStorage:
    """Работа с Invited (приглашённые + ответы)."""

    def __init__(
        self,
        meeting_repo: Optional[Any] = None,
        user_repo: Optional[Any] = None,
    ) -> None:
        self._meeting_repo = meeting_repo
        self._user_repo = user_repo

    def update_invited_contact(
        self,
        meeting_id: int,
        email: str,
        full_name: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> bool:
        """Обновляет full_name и phone в Invited при первом обращении."""
        if not email or not email.strip():
            return False
        email_norm = email.strip().lower()
        with get_session_context() as session:
            stmt = select(Invited).where(
                Invited.meeting_id == meeting_id,
                func.lower(Invited.email) == email_norm,
            )
            inv = session.scalar(stmt)
            if not inv:
                return False
            if full_name is not None:
                inv.full_name = full_name.strip() or inv.full_name
            if phone is not None:
                inv.phone = phone.strip() or inv.phone
            session.flush()
            return True

    def update_invited_answer(
        self,
        email: str,
        meeting_id: int,
        answer: str,
        status: Optional[str] = None,
        full_name: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> bool:
        """
        Обновляет ответ приглашённого. Поиск по email + meeting_id.
        Возвращает True при успехе, False если запись не найдена.
        """
        if not email or not email.strip():
            return False
        email_norm = email.strip().lower()
        with get_session_context() as session:
            stmt = select(Invited).where(
                Invited.meeting_id == meeting_id,
                func.lower(Invited.email) == email_norm,
            )
            inv = session.scalar(stmt)
            if not inv:
                logger.warning(
                    "Invited не найден: email=%s, meeting_id=%s",
                    email_norm, meeting_id,
                )
                return False
            inv.answer = answer
            if status:
                inv.status = status
            if full_name is not None:
                inv.full_name = full_name.strip() or inv.full_name
            if phone is not None:
                inv.phone = phone.strip() or inv.phone
            session.flush()
            return True

    def get_users_with_answers(
        self,
        meeting_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Список проголосовавших (Invited с заполненным answer).
        """
        with get_session_context() as session:
            stmt = select(Invited).where(Invited.answer.isnot(None))
            if meeting_id is not None:
                stmt = stmt.where(Invited.meeting_id == meeting_id)
            rows = session.scalars(stmt).all()
            return [
                {
                    "fio": (row.full_name or "").strip() or (row.email or str(row.id) or "—"),
                    "email": row.email,
                    "phone": row.phone,
                    "answer": row.answer or "",
                }
                for row in rows
            ]
