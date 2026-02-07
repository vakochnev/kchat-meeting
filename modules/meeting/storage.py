"""
Хранилище данных совещаний.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select, or_

from db.models import MeetingUser
from db.session import get_session_context

logger = logging.getLogger(__name__)


class MeetingStorage:
    """Класс для работы с данными совещаний в БД."""
    
    def find_user(
        self,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        sender_id: Optional[int] = None,
    ) -> Optional[MeetingUser]:
        """
        Находит пользователя в таблице совещаний.
        
        Args:
            email: Email пользователя.
            phone: Телефон пользователя.
            sender_id: ID отправителя.
            
        Returns:
            MeetingUser или None если не найден.
        """
        if not email and not phone and not sender_id:
            return None
        
        with get_session_context() as session:
            stmt = select(MeetingUser)
            
            conditions = []
            if email:
                conditions.append(MeetingUser.email == email.lower())
            if phone:
                conditions.append(MeetingUser.phone == phone)
            if sender_id:
                conditions.append(MeetingUser.sender_id == sender_id)
            
            if conditions:
                stmt = stmt.where(or_(*conditions))
                user = session.scalar(stmt)
                if user is not None:
                    session.refresh(user)
                return user
            
            return None
    
    def is_user_allowed(
        self,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        sender_id: Optional[int] = None,
        group_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
    ) -> bool:
        """
        Проверяет, допущен ли пользователь к совещанию.
        Допуск только по записи текущего чата (sender_id + group_id + workspace_id).
        Если контекста чата нет — не допускаем (безопасно).
        """
        if sender_id is None:
            return False
        if group_id is None or workspace_id is None:
            return False

        with get_session_context() as session:
            stmt = select(MeetingUser).where(
                MeetingUser.sender_id == sender_id,
                MeetingUser.group_id == group_id,
                MeetingUser.workspace_id == workspace_id,
            )
            user = session.scalar(stmt)
            if user is None:
                return False
            return user.meeting_datetime is not None
    
    def save_user(
        self,
        sender_id: int,
        group_id: int,
        workspace_id: int,
        username: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        job_title: Optional[str] = None,
        last_name: Optional[str] = None,
        middle_name: Optional[str] = None,
        first_name: Optional[str] = None,
        meeting_datetime: Optional[datetime] = None,
    ) -> MeetingUser:
        """
        Сохраняет или обновляет данные пользователя из SSE.
        
        Args:
            sender_id: ID отправителя.
            group_id: ID группы.
            workspace_id: ID рабочего пространства.
            username: Имя пользователя.
            email: Email пользователя.
            phone: Телефон пользователя.
            job_title: Должность.
            last_name: Фамилия.
            middle_name: Отчество.
            first_name: Имя.
            meeting_datetime: Дата и время совещания.
            
        Returns:
            MeetingUser объект.
            
        Raises:
            Exception: При ошибке сохранения данных.
        """
        with get_session_context() as session:
            # Уникальность: пользователь + дата совещания (одна запись на голосование за дату)
            if meeting_datetime is not None:
                stmt = select(MeetingUser).where(
                    MeetingUser.sender_id == sender_id,
                    MeetingUser.group_id == group_id,
                    MeetingUser.workspace_id == workspace_id,
                    MeetingUser.meeting_datetime == meeting_datetime,
                )
                existing = session.scalar(stmt)
            else:
                # Без даты — ищем любую запись по чату (для обратной совместиости)
                stmt = select(MeetingUser).where(
                    MeetingUser.sender_id == sender_id,
                    MeetingUser.group_id == group_id,
                    MeetingUser.workspace_id == workspace_id,
                )
                existing = session.scalar(stmt)

            if existing:
                if username is not None:
                    existing.username = username
                if email is not None:
                    existing.email = email
                if phone is not None:
                    existing.phone = phone
                if job_title is not None:
                    existing.job_title = job_title
                if last_name is not None:
                    existing.last_name = last_name
                if middle_name is not None:
                    existing.middle_name = middle_name
                if first_name is not None:
                    existing.first_name = first_name
                if meeting_datetime is None:
                    existing.meeting_datetime = None
                elif existing.meeting_datetime is None:
                    existing.meeting_datetime = meeting_datetime
                existing.updated_at = datetime.utcnow()
                user = existing
            else:
                user = MeetingUser(
                    sender_id=sender_id,
                    group_id=group_id,
                    workspace_id=workspace_id,
                    username=username,
                    email=email,
                    phone=phone,
                    job_title=job_title,
                    last_name=last_name,
                    middle_name=middle_name,
                    first_name=first_name,
                    meeting_datetime=meeting_datetime,
                )
                session.add(user)

            logger.info(
                "Данные пользователя сохранены: sender_id=%s, meeting_datetime=%s",
                sender_id, meeting_datetime,
            )
            return user
    
    def update_user_answer(
        self,
        sender_id: int,
        answer: str,
        status: Optional[str] = None,
        group_id: Optional[int] = None,
        workspace_id: Optional[int] = None,
        meeting_datetime: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Обновляет ответ пользователя о присутствии на совещании.
        Поиск записи: sender_id + group_id + workspace_id + meeting_datetime
        (одно голосование на пользователя и дату совещания).

        Args:
            sender_id: ID отправителя.
            answer: Текст ответа (из answer_text в config).
            status: Статус отправки на бэкенд.
            group_id: ID группы.
            workspace_id: ID рабочего пространства.
            meeting_datetime: Дата и время совещания (из invited.json).

        Returns:
            Словарь с данными пользователя для бэкенда или None если запись не найдена.
        """
        with get_session_context() as session:
            # Только запись с той же датой совещания (не обновляем голос за другую дату)
            stmt = select(MeetingUser).where(MeetingUser.sender_id == sender_id)
            if group_id is not None and workspace_id is not None:
                stmt = stmt.where(
                    MeetingUser.group_id == group_id,
                    MeetingUser.workspace_id == workspace_id,
                )
            if meeting_datetime is not None:
                stmt = stmt.where(MeetingUser.meeting_datetime == meeting_datetime)
            user = session.scalar(stmt)
            if not user:
                logger.warning(
                    "Пользователь не найден: sender_id=%s, group_id=%s, workspace_id=%s, meeting_datetime=%s",
                    sender_id, group_id, workspace_id, meeting_datetime,
                )
                return None

            user.answer = answer
            if status:
                user.status = status
            if meeting_datetime is not None and user.meeting_datetime is None:
                user.meeting_datetime = meeting_datetime
            user.updated_at = datetime.utcnow()

            logger.info(
                "Ответ пользователя обновлён: sender_id=%s, answer=%s",
                sender_id, answer,
            )

            row = user
            return {
                "id": row.id,
                "sender_id": row.sender_id,
                "group_id": row.group_id,
                "workspace_id": row.workspace_id,
                "username": row.username,
                "email": row.email,
                "phone": row.phone,
                "job_title": row.job_title,
                "last_name": row.last_name,
                "middle_name": row.middle_name,
                "first_name": row.first_name,
                "meeting_datetime": (
                    row.meeting_datetime.isoformat()
                    if row.meeting_datetime else None
                ),
                "answer": row.answer,
                "status": row.status,
                "created_at": (
                    row.created_at.isoformat() if row.created_at else None
                ),
                "updated_at": (
                    row.updated_at.isoformat() if row.updated_at else None
                ),
            }
    
    def get_user(self, sender_id: int) -> Optional[MeetingUser]:
        """
        Возвращает данные пользователя по sender_id.
        
        Args:
            sender_id: ID отправителя.
            
        Returns:
            MeetingUser объект или None если не найден.
        """
        return self.find_user(sender_id=sender_id)

    def get_user_fio(self, sender_id: int) -> Optional[str]:
        """
        Возвращает ФИО пользователя по sender_id.
        Выполняется внутри сессии, возвращает простую строку — без detached-объектов.

        Returns:
            Строка "Фамилия Имя Отчество" или None.
        """
        with get_session_context() as session:
            stmt = select(MeetingUser).where(
                MeetingUser.sender_id == sender_id
            )
            user = session.scalar(stmt)
            if not user:
                return None
            parts = [
                user.last_name,
                user.first_name,
                user.middle_name,
            ]
            parts = [p.strip() for p in parts if p and p.strip()]
            return " ".join(parts) if parts else None
    
    def get_pending_users(self) -> List[MeetingUser]:
        """
        Возвращает пользователей с ответами, но без статуса отправки.
        
        Returns:
            Список MeetingUser объектов.
        """
        with get_session_context() as session:
            stmt = select(MeetingUser).where(
                MeetingUser.answer.isnot(None),
                or_(
                    MeetingUser.status.is_(None),
                    MeetingUser.status != "sent"
                )
            )
            return list(session.scalars(stmt).all())

    def get_users_with_answers(
        self,
        meeting_datetime: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Возвращает список проголосовавших (пользователей с заполненным answer).

        Args:
            meeting_datetime: Фильтр по дате совещания; если None — все голоса.

        Returns:
            Список словарей: fio, email, phone, answer (yes/no).
        """
        with get_session_context() as session:
            stmt = select(MeetingUser).where(MeetingUser.answer.isnot(None))
            rows = session.scalars(stmt).all()
            result = []
            meeting_date = (
                meeting_datetime.date()
                if meeting_datetime is not None else None
            )
            for row in rows:
                if meeting_date is not None:
                    if row.meeting_datetime is None:
                        continue
                    try:
                        row_date = (
                            row.meeting_datetime.date()
                            if hasattr(row.meeting_datetime, "date")
                            else row.meeting_datetime
                        )
                        if row_date != meeting_date:
                            continue
                    except (AttributeError, TypeError):
                        continue
                parts = [
                    row.last_name,
                    row.first_name,
                    row.middle_name,
                ]
                parts = [p.strip() for p in parts if p and str(p).strip()]
                fio = " ".join(parts) if parts else (row.email or str(row.sender_id))
                result.append({
                    "fio": fio,
                    "email": row.email,
                    "phone": row.phone,
                    "answer": row.answer or "",
                })
            return result
