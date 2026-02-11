"""
Репозиторий для работы с собраниями (Meeting) и приглашёнными (Invited).
"""
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import json

from sqlalchemy import select

from db.models import Invited, Meeting
from db.session import get_session_context

from config import config

logger = logging.getLogger(__name__)


class MeetingRepository:
    """Репозиторий для Meeting и Invited."""

    def get_active_meeting(self) -> Optional[Meeting]:
        """Возвращает активное совещание (is_active=True)."""
        with get_session_context() as session:
            stmt = select(Meeting).where(Meeting.is_active == True)
            return session.scalar(stmt)

    def get_meeting_by_id(self, meeting_id: int) -> Optional[Meeting]:
        """Возвращает совещание по ID."""
        with get_session_context() as session:
            return session.scalar(select(Meeting).where(Meeting.id == meeting_id))

    def get_meeting_info(self) -> Dict[str, Any]:
        """
        Возвращает данные активного совещания в формате словаря.
        Аналог get_meeting_info из config (topic, date, time, place, goal, link, url).
        """
        meeting = self.get_active_meeting()
        if not meeting:
            return {}
        return {
            "topic": meeting.topic,
            "url": meeting.url,
            "date": meeting.date,
            "time": meeting.time,
            "datetime_utc": meeting.datetime_utc,
            "place": meeting.place,
            "goal": meeting.goal,
            "link": meeting.link,
            "connection_link": meeting.connection_link,
        }

    def get_meeting_datetime(self) -> Optional[datetime]:
        """Возвращает datetime активного совещания (для сопоставления с MeetingUser)."""
        meeting = self.get_active_meeting()
        if not meeting:
            return None
        if meeting.datetime_utc:
            return meeting.datetime_utc
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
        meeting = (
            self.get_meeting_by_id(meeting_id)
            if meeting_id is not None
            else self.get_active_meeting()
        )
        if not meeting:
            return []

        with get_session_context() as session:
            stmt = select(Invited).where(Invited.meeting_id == meeting.id)
            rows = session.scalars(stmt).all()
            return [
                {
                    "last_name": r.last_name,
                    "first_name": r.first_name,
                    "middle_name": r.middle_name,
                    "email": r.email or "",
                    "phone": r.phone or "",
                    "login": r.login or "",
                }
                for r in rows
            ]

    def save_meeting(
        self,
        topic: Optional[str] = None,
        url: Optional[str] = None,
        date: Optional[str] = None,
        time: Optional[str] = None,
        datetime_utc: Optional[datetime] = None,
        place: Optional[str] = None,
        goal: Optional[str] = None,
        link: Optional[str] = None,
        connection_link: Optional[str] = None,
        is_active: bool = True,
    ) -> int:
        """Создаёт или обновляет активное совещание."""
        with get_session_context() as session:
            meeting = session.scalar(
                select(Meeting).where(Meeting.is_active == True)
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
                if datetime_utc is not None:
                    meeting.datetime_utc = datetime_utc
                if place is not None:
                    meeting.place = place
                if goal is not None:
                    meeting.goal = goal
                if link is not None:
                    meeting.link = link
                if connection_link is not None:
                    meeting.connection_link = connection_link
                meeting.is_active = is_active
            else:
                meeting = Meeting(
                    topic=topic,
                    url=url,
                    date=date,
                    time=time,
                    datetime_utc=datetime_utc,
                    place=place,
                    goal=goal,
                    link=link,
                    connection_link=connection_link,
                    is_active=is_active,
                )
                session.add(meeting)
            session.flush()
            return meeting.id

    def save_invited(
        self,
        meeting_id: int,
        last_name: Optional[str] = None,
        first_name: Optional[str] = None,
        middle_name: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        login: Optional[str] = None,
    ) -> Invited:
        """Добавляет приглашённого к совещанию."""
        with get_session_context() as session:
            invited = Invited(
                meeting_id=meeting_id,
                last_name=last_name,
                first_name=first_name,
                middle_name=middle_name,
                email=email,
                phone=phone,
                login=login,
            )
            session.add(invited)
            return invited

    def import_from_invited_json(
        self, file_path: Optional[Path] = None
    ) -> tuple[int, int]:
        """
        Импортирует данные из invited.json в БД.
        Создаёт meeting и invited. Деактивирует предыдущее активное совещание.
        Returns:
            (meeting_id, invited_count)
        """
        path = file_path or (config.base_dir / "config" / "invited.json")
        if not path.exists():
            logger.warning("Файл invited.json не найден: %s", path)
            return 0, 0

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error("Ошибка чтения invited.json: %s", e)
            return 0, 0

        meeting_data = data.get("meeting", {})
        invited_data = data.get("invited", [])

        if not meeting_data and not invited_data:
            logger.info("invited.json пуст")
            return 0, 0

        date_str = meeting_data.get("date")
        time_str = meeting_data.get("time")
        datetime_utc = None
        if date_str and time_str:
            datetime_utc = self._parse_datetime(date_str, time_str)

        with get_session_context() as session:
            # Деактивируем все совещания
            for m in session.scalars(select(Meeting)).all():
                m.is_active = False

            meeting = Meeting(
                topic=meeting_data.get("topic"),
                url=meeting_data.get("url"),
                date=date_str,
                time=time_str,
                datetime_utc=datetime_utc,
                place=meeting_data.get("place"),
                goal=meeting_data.get("goal"),
                link=meeting_data.get("link"),
                connection_link=meeting_data.get("connection_link"),
                is_active=True,
            )
            session.add(meeting)
            session.flush()
            meeting_id = meeting.id

            count = 0
            for inv in invited_data:
                if not isinstance(inv, dict):
                    continue
                session.add(Invited(
                    meeting_id=meeting_id,
                    last_name=inv.get("last_name"),
                    first_name=inv.get("first_name"),
                    middle_name=inv.get("middle_name"),
                    email=inv.get("email") or "",
                    phone=inv.get("phone"),
                    login=inv.get("login"),
                ))
                count += 1

        logger.info("Импорт из invited.json: meeting_id=%s, invited=%s", meeting_id, count)
        return meeting_id, count

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
