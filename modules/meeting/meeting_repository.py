"""
Репозиторий для работы с собраниями (Meeting) и приглашёнными (Invited).
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from db.models import Invited, Meeting, MeetingAdmin
from db.session import get_session_context

logger = logging.getLogger(__name__)


class MeetingRepository:
    """Репозиторий для Meeting и Invited."""

    def get_active_meeting(self) -> Optional[Meeting]:
        """Возвращает последнее созданное собрание (по id)."""
        with get_session_context() as session:
            stmt = select(Meeting).order_by(Meeting.id.desc()).limit(1)
            return session.scalar(stmt)

    def get_meeting_by_id(self, meeting_id: int) -> Optional[Meeting]:
        """Возвращает совещание по ID."""
        with get_session_context() as session:
            return session.scalar(select(Meeting).where(Meeting.id == meeting_id))

    def get_meeting_info(self) -> Dict[str, Any]:
        """
        Возвращает данные последнего собрания в формате словаря.
        (topic, date, time, place, link, url).
        """
        with get_session_context() as session:
            meeting = session.scalar(
                select(Meeting).order_by(Meeting.id.desc()).limit(1)
            )
            if not meeting:
                return {}
            return {
                "meeting_id": meeting.id,
                "topic": meeting.topic,
                "url": meeting.url,
                "date": meeting.date,
                "time": meeting.time,
                "place": meeting.place,
                "link": meeting.link,
            }

    def get_meeting_datetime(self) -> Optional[datetime]:
        """Возвращает datetime последнего собрания."""
        with get_session_context() as session:
            meeting = session.scalar(
                select(Meeting).order_by(Meeting.id.desc()).limit(1)
            )
            if not meeting:
                return None
            if meeting.date and meeting.time:
                return self._parse_datetime(meeting.date, meeting.time)
        return None

    def get_invited_list(
        self, meeting_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Возвращает список приглашённых в формате словарей.
        Если meeting_id не задан — для активного совещания.
        """
        with get_session_context() as session:
            if meeting_id is not None:
                meeting = session.scalar(
                    select(Meeting).where(Meeting.id == meeting_id)
                )
            else:
                meeting = session.scalar(
                    select(Meeting).order_by(Meeting.id.desc()).limit(1)
                )
            if not meeting:
                return []
            stmt = select(Invited).where(Invited.meeting_id == meeting.id)
            rows = session.scalars(stmt).all()
            return [
                {
                    "full_name": r.full_name or "",
                    "email": r.email or "",
                    "phone": r.phone or "",
                    "answer": r.answer or "",
                }
                for r in rows
            ]

    def save_admin(
        self,
        email: str,
        full_name: Optional[str] = None,
    ) -> MeetingAdmin:
        """Добавляет администратора (общий для всех собраний)."""
        with get_session_context() as session:
            admin = MeetingAdmin(
                email=email.strip().lower(),
                full_name=full_name,
            )
            session.add(admin)
            return admin

    def get_admin_fio(self, email: Optional[str] = None) -> Optional[str]:
        """
        Возвращает ФИО админа для приветствия по email.
        """
        if not email:
            return None
        with get_session_context() as session:
            stmt = select(MeetingAdmin).where(
                MeetingAdmin.email == email.strip().lower(),
            )
            admin = session.scalar(stmt)
            if not admin:
                return None
            return (admin.full_name or "").strip() or None

    def is_admin(self, email: str) -> bool:
        """Проверяет, является ли email администратором."""
        with get_session_context() as session:
            stmt = select(MeetingAdmin).where(
                MeetingAdmin.email == email.strip().lower(),
            )
            return session.scalar(stmt) is not None

    def save_meeting(
        self,
        topic: Optional[str] = None,
        url: Optional[str] = None,
        date: Optional[str] = None,
        time: Optional[str] = None,
        place: Optional[str] = None,
        link: Optional[str] = None,
    ) -> int:
        """Обновляет последнее собрание или создаёт новое."""
        with get_session_context() as session:
            meeting = session.scalar(
                select(Meeting).order_by(Meeting.id.desc()).limit(1)
            )
            if meeting:
                if topic is not None:
                    meeting.topic = topic
                if url is not None:
                    meeting.url = url
                if date is not None:
                    meeting.date = date
                if time is not None:
                    meeting.time = time
                if place is not None:
                    meeting.place = place
                if link is not None:
                    meeting.link = link
            else:
                meeting = Meeting(
                    topic=topic,
                    url=url,
                    date=date,
                    time=time,
                    place=place,
                    link=link,
                )
                session.add(meeting)
            session.flush()
            return meeting.id

    def update_active_meeting(
        self,
        topic: str,
        date: str,
        time: str,
        place: Optional[str] = None,
        link: Optional[str] = None,
    ) -> int:
        """
        Обновляет последнее собрание. Вызывает ValueError, если собраний нет.
        Возвращает ID обновлённого собрания.
        """
        with get_session_context() as session:
            meeting = session.scalar(
                select(Meeting).order_by(Meeting.id.desc()).limit(1)
            )
            if not meeting:
                raise ValueError("Нет активного собрания для изменения")
            meeting.topic = topic.strip() or None
            meeting.date = date.strip() or None
            meeting.time = time.strip() or None
            meeting.place = place.strip() if place else None
            meeting.link = link.strip() if link else None
            session.flush()
            return meeting.id

    def create_new_meeting(
        self,
        topic: str,
        date: str,
        time: str,
        place: Optional[str] = None,
        link: Optional[str] = None,
    ) -> int:
        """
        Создаёт новое собрание с заданными полями.

        Только собрание (Meeting). Таблица invited не заполняется —
        приглашённых добавляют отдельно по команде /приглашенные.
        Возвращает ID созданного совещания.
        """
        with get_session_context() as session:
            meeting = Meeting(
                topic=topic.strip() or None,
                date=date.strip() or None,
                time=time.strip() or None,
                place=place.strip() if place else None,
                link=link.strip() if link else None,
            )
            session.add(meeting)
            session.flush()
            return meeting.id

    def save_invited(
        self,
        meeting_id: int,
        full_name: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> Invited:
        """
        Добавляет приглашённого к совещанию.

        Вызывается только при явном добавлении пользователя (например,
        через команду /приглашенные). При создании собрания не вызывается.
        """
        with get_session_context() as session:
            invited = Invited(
                meeting_id=meeting_id,
                full_name=full_name,
                email=email,
                phone=phone,
            )
            session.add(invited)
            return invited

    @staticmethod
    def _parse_datetime(date_str: str, time_str: str) -> Optional[datetime]:
        """Парсит date и time в datetime."""
        try:
            date_str = str(date_str).strip()
            time_str = str(time_str).strip()
            if "." in date_str and len(date_str) >= 8:
                parts = date_str.split(".")
                if len(parts) == 3:
                    day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                    if len(parts[2]) == 2:
                        year += 2000 if year < 50 else 1900
                else:
                    return None
            else:
                dt_date = datetime.strptime(date_str[:10], "%Y-%m-%d")
                day, month, year = dt_date.day, dt_date.month, dt_date.year
            if time_str.count(":") >= 2:
                t = datetime.strptime(time_str, "%H:%M:%S")
            else:
                t = datetime.strptime(time_str, "%H:%M")
            return datetime(year, month, day, t.hour, t.minute, t.second)
        except (ValueError, TypeError):
            return None
