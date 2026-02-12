"""
Репозиторий для работы с пользователями (таблица users).
"""
import logging
from typing import Optional

from sqlalchemy import select

from db.models import User
from db.session import get_session_context

logger = logging.getLogger(__name__)


class UserRepository:
    """Репозиторий для User."""

    def save_user_on_chat(
        self,
        sender_id: int,
        group_id: int,
        workspace_id: int,
        full_name: str,
        email: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> Optional[User]:
        """
        Сохраняет или обновляет пользователя, начавшего чат с ботом.
        Уникальность по (sender_id, group_id, workspace_id).
        Возвращает User или None при ошибке.
        """
        if not full_name or not full_name.strip():
            full_name = "—"
        with get_session_context() as session:
            existing = session.scalar(
                select(User).where(
                    User.sender_id == sender_id,
                    User.group_id == group_id,
                    User.workspace_id == workspace_id,
                )
            )
            if existing:
                existing.full_name = full_name.strip()
                if email is not None:
                    existing.email = email.strip() or None
                if phone is not None:
                    existing.phone = phone.strip() or None
                session.flush()
                return existing
            user = User(
                sender_id=sender_id,
                group_id=group_id,
                workspace_id=workspace_id,
                full_name=full_name.strip(),
                email=email.strip() if email else None,
                phone=phone.strip() if phone else None,
            )
            session.add(user)
            session.flush()
            return user

    def get_by_chat(
        self,
        sender_id: int,
        group_id: int,
        workspace_id: int,
    ) -> Optional[dict]:
        """
        Возвращает данные пользователя по контексту чата.
        Возвращает dict с full_name, email, phone (не ORM-объект) — чтобы избежать
        DetachedInstanceError при доступе вне сессии.
        """
        with get_session_context() as session:
            user = session.scalar(
                select(User).where(
                    User.sender_id == sender_id,
                    User.group_id == group_id,
                    User.workspace_id == workspace_id,
                )
            )
            if user is None:
                return None
            return {
                "full_name": user.full_name,
                "email": user.email,
                "phone": user.phone,
            }
