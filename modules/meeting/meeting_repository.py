"""
Репозиторий для работы с собраниями (Meeting) и приглашёнными (Invited).
"""
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from db.models import Invited, Meeting, MeetingAdmin
from db.session import get_session_context

logger = logging.getLogger(__name__)


def _normalize_phone(value: Optional[str]) -> Optional[str]:
    """
    Нормализует номер телефона к формату 79991234567.
    Убирает все нецифровые символы, 8 в начале заменяет на 7.
    """
    if not value or not value.strip():
        return None
    digits = re.sub(r"\D", "", value)
    if not digits:
        return None
    if len(digits) == 10 and digits[0] == "9":
        return "7" + digits
    if len(digits) == 11 and digits[0] == "8":
        return "7" + digits[1:]
    if len(digits) == 11 and digits[0] == "7":
        return digits
    if len(digits) >= 11:
        # Берём 11 цифр (7 + 10 цифр номера)
        if digits[0] == "7":
            return digits[:11]
        if digits[0] == "8":
            return "7" + digits[1:11]
    return None


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

    def get_meeting_info_by_id(self, meeting_id: int) -> Dict[str, Any]:
        """Возвращает данные собрания по ID в формате словаря."""
        meeting = self.get_meeting_by_id(meeting_id)
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

    def search_invited(
        self, meeting_id: int, query: str
    ) -> List[Dict[str, Any]]:
        """
        Ищет приглашённых по вхождению query в ФИО или email.
        Поиск регистронезависимый, работает с NULL значениями.
        """
        from sqlalchemy import func, or_
        
        query_lower = query.strip().lower()
        if not query_lower:
            return []
        
        with get_session_context() as session:
            meeting = session.scalar(
                select(Meeting).where(Meeting.id == meeting_id)
            )
            if not meeting:
                return []
            
            # Получаем всех приглашённых для этого собрания
            all_invited = session.scalars(
                select(Invited).where(Invited.meeting_id == meeting.id)
            ).all()
            
            # Фильтруем в Python для надёжности (работает с NULL и пробелами)
            results = []
            for inv in all_invited:
                full_name_lower = (inv.full_name or "").strip().lower()
                email_lower = (inv.email or "").strip().lower()
                
                if query_lower in full_name_lower or query_lower in email_lower:
                    results.append(inv)
            
            return [
                {
                    "full_name": r.full_name or "",
                    "email": r.email or "",
                    "phone": r.phone or "",
                    "answer": r.answer or "",
                }
                for r in results
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

    def copy_invited_to_meeting(
        self,
        source_meeting_id: int,
        target_meeting_id: int,
    ) -> int:
        """
        Копирует приглашённых из source в target с status=invited, answer=None.
        Возвращает количество скопированных записей.
        """
        with get_session_context() as session:
            stmt = select(Invited).where(Invited.meeting_id == source_meeting_id)
            source_rows = session.scalars(stmt).all()
            copied = 0
            for inv in source_rows:
                new_inv = Invited(
                    meeting_id=target_meeting_id,
                    full_name=inv.full_name,
                    email=inv.email,
                    phone=inv.phone,
                    answer=None,
                    status="invited",
                )
                try:
                    with session.begin_nested():
                        session.add(new_inv)
                        session.flush()
                    copied += 1
                except IntegrityError:
                    pass
            logger.info(
                "copy_invited_to_meeting: source=%s target=%s copied=%d",
                source_meeting_id, target_meeting_id, copied,
            )
            return copied

    def save_invited_batch(
        self,
        meeting_id: int,
        rows: list,
    ) -> int:
        """
        Сохраняет приглашённых в таблицу invited в одной транзакции.
        Дубликаты исключаются на уровне БД (UNIQUE constraint).
        rows: список dict с ключами full_name, email, phone.
        """
        if not rows:
            logger.debug("save_invited_batch: rows пуст")
            return 0
        added = 0
        with get_session_context() as session:
            for row in rows:
                email = (row.get("email") or "").strip() or None
                full_name = (row.get("full_name") or "").strip() or None
                raw_phone = (row.get("phone") or "").strip() or None
                phone = _normalize_phone(raw_phone) if raw_phone else None
                if not full_name:
                    continue
                invited = Invited(
                    meeting_id=meeting_id,
                    full_name=full_name,
                    email=email,
                    phone=phone,
                )
                try:
                    with session.begin_nested():
                        session.add(invited)
                        session.flush()
                    added += 1
                except IntegrityError:
                    pass
            logger.info(
                "save_invited_batch: meeting_id=%s, добавлено %d записей",
                meeting_id, added,
            )
        return added

    def delete_invited_by_email(
        self,
        meeting_id: int,
        email: str,
    ) -> bool:
        """
        Удаляет приглашённого по meeting_id и email.
        Возвращает True если запись найдена и удалена, False иначе.
        """
        if not email or not email.strip():
            return False
        email_norm = email.strip().lower()
        with get_session_context() as session:
            stmt = select(Invited).where(
                Invited.meeting_id == meeting_id,
                func.lower(Invited.email) == email_norm,
            )
            invited = session.scalar(stmt)
            if not invited:
                return False
            session.delete(invited)
            logger.info(
                "delete_invited_by_email: meeting_id=%s email=%s",
                meeting_id, email_norm,
            )
            return True

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
