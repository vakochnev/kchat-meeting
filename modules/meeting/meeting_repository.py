"""
Репозиторий для работы с собраниями (Meeting) и приглашёнными (Invited).
"""
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from db.models import Invited, Meeting, MeetingAdmin, PermanentInvited, User
from db.session import get_session_context

logger = logging.getLogger(__name__)


def _normalize_phone(value: Optional[str]) -> Optional[str]:
    """
    Нормализует номер телефона к формату 79991234567 или короткому формату (5 цифр).
    Убирает все нецифровые символы, 8 в начале заменяет на 7.
    Поддерживает короткие номера (5 цифр) - возвращает как есть.
    """
    if not value or not value.strip():
        return None
    digits = re.sub(r"\D", "", value)
    if not digits:
        return None
    
    # Короткие номера (5 цифр) - возвращаем как есть
    if len(digits) == 5:
        return digits
    
    # Стандартные форматы мобильных номеров
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
        """Возвращает последнее собрание, если оно ещё не прошло."""
        with get_session_context() as session:
            meeting = session.scalar(
                select(Meeting).order_by(Meeting.id.desc()).limit(1)
            )
            if meeting and self._is_meeting_past(meeting):
                return None
            return meeting

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
        Если собрание уже прошло (дата/время в прошлом) — возвращает пустой словарь.
        """
        with get_session_context() as session:
            meeting = session.scalar(
                select(Meeting).order_by(Meeting.id.desc()).limit(1)
            )
            if not meeting:
                return {}
            if self._is_meeting_past(meeting):
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

    def get_meeting_info_include_past(self) -> Dict[str, Any]:
        """
        Возвращает данные последнего собрания, включая прошедшие.
        Используется для проверки «есть ли вообще собрание» (например, в /собрание).
        """
        with get_session_context() as session:
            meeting = session.scalar(
                select(Meeting).order_by(Meeting.id.desc()).limit(1)
            )
            if not meeting:
                return {}
            info = {
                "meeting_id": meeting.id,
                "topic": meeting.topic,
                "url": meeting.url,
                "date": meeting.date,
                "time": meeting.time,
                "place": meeting.place,
                "link": meeting.link,
            }
            info["is_past"] = self._is_meeting_past(meeting)
            return info

    @staticmethod
    def _is_meeting_past(meeting: "Meeting") -> bool:
        """Проверяет, прошло ли собрание (дата+время < текущий момент)."""
        if not meeting.date:
            return False
        meeting_dt = MeetingRepository._parse_datetime(
            meeting.date, meeting.time or "23:59"
        )
        if not meeting_dt:
            return False
        return meeting_dt < datetime.now()

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
        Добавляет флаг exists_in_users для каждого приглашённого.
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
            
            # Получаем множество email'ов пользователей из таблицы users
            users_emails = set()
            if rows:
                # Нормализуем email'ы из invited (убираем пробелы, приводим к нижнему регистру)
                emails_from_invited = {
                    (r.email or "").strip().lower() 
                    for r in rows 
                    if r.email and (r.email or "").strip()
                }
                logger.info(
                    "get_invited_list: нормализованные email'ы из invited (%d): %s",
                    len(emails_from_invited), emails_from_invited
                )
                if emails_from_invited:
                    # Получаем все email'ы из users и нормализуем их в Python
                    users_stmt = select(User.email).where(User.email.isnot(None))
                    all_users_emails_raw = session.scalars(users_stmt).all()
                    logger.info(
                        "get_invited_list: найдено %d email'ов в таблице users",
                        len(all_users_emails_raw)
                    )
                    # Нормализуем email'ы из users и фильтруем только те, что есть в invited
                    for email_raw in all_users_emails_raw:
                        if email_raw:
                            email_normalized = (email_raw or "").strip().lower()
                            logger.debug(
                                "get_invited_list: проверка email из users: raw=%s normalized=%s",
                                email_raw, email_normalized
                            )
                            if email_normalized and email_normalized in emails_from_invited:
                                users_emails.add(email_normalized)
                                logger.info(
                                    "get_invited_list: найден совпадающий email: %s",
                                    email_normalized
                                )
                    logger.info(
                        "get_invited_list: итоговые совпадающие email'ы в users (%d): %s",
                        len(users_emails), users_emails
                    )
            
            result = []
            for r in rows:
                email_normalized = (r.email or "").strip().lower() if r.email else ""
                exists_in_users = email_normalized in users_emails if email_normalized else False
                logger.info(
                    "get_invited_list: invited name='%s' email='%s' normalized='%s' exists_in_users=%s",
                    r.full_name, r.email, email_normalized, exists_in_users
                )
                result.append({
                    "full_name": r.full_name or "",
                    "email": r.email or "",
                    "phone": r.phone or "",
                    "answer": r.answer or "",
                    "exists_in_users": exists_in_users,
                })
            return result

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
            
            # Получаем множество email'ов пользователей из таблицы users
            users_emails = set()
            if results:
                # Нормализуем email'ы из результатов поиска (убираем пробелы, приводим к нижнему регистру)
                emails_from_results = {
                    (r.email or "").strip().lower() 
                    for r in results 
                    if r.email and (r.email or "").strip()
                }
                if emails_from_results:
                    # Получаем все email'ы из users и нормализуем их в Python
                    users_stmt = select(User.email).where(User.email.isnot(None))
                    all_users_emails_raw = session.scalars(users_stmt).all()
                    # Нормализуем email'ы из users и фильтруем только те, что есть в результатах поиска
                    for email_raw in all_users_emails_raw:
                        if email_raw:
                            email_normalized = (email_raw or "").strip().lower()
                            if email_normalized and email_normalized in emails_from_results:
                                users_emails.add(email_normalized)
            
            return [
                {
                    "full_name": r.full_name or "",
                    "email": r.email or "",
                    "phone": r.phone or "",
                    "answer": r.answer or "",
                    "exists_in_users": (
                        (r.email or "").strip().lower() in users_emails 
                        if r.email and (r.email or "").strip() 
                        else False
                    ),
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
        Автоматически добавляет постоянных приглашённых из таблицы permanent_invited.
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
            meeting_id = meeting.id
            
            # Автоматически добавляем постоянных приглашённых
            permanent_invited = session.scalars(select(PermanentInvited)).all()
            if permanent_invited:
                added_count = 0
                for perm_inv in permanent_invited:
                    invited = Invited(
                        meeting_id=meeting_id,
                        full_name=perm_inv.full_name,
                        email=perm_inv.email,
                        phone=perm_inv.phone,
                    )
                    try:
                        with session.begin_nested():
                            session.add(invited)
                            session.flush()
                        added_count += 1
                    except IntegrityError:
                        pass
                logger.info(
                    "create_new_meeting: добавлено постоянных приглашённых: %d из %d",
                    added_count, len(permanent_invited)
                )
            
            return meeting_id

    def copy_invited_to_meeting(
        self,
        source_meeting_id: int,
        target_meeting_id: int,
    ) -> int:
        """
        Копирует приглашённых из source в target с answer=None (статусы не копируются).
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
                    # Статусы (kchat_status, email_status, sms_status) не копируются
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

    def get_permanent_invited_list(self) -> List[Dict[str, Any]]:
        """
        Возвращает список постоянных приглашённых в формате словарей.
        """
        with get_session_context() as session:
            rows = session.scalars(select(PermanentInvited)).all()
            return [
                {
                    "full_name": r.full_name or "",
                    "email": r.email or "",
                    "phone": r.phone or "",
                }
                for r in rows
            ]

    def save_permanent_invited(
        self,
        full_name: str,
        email: str,
        phone: Optional[str] = None,
    ) -> bool:
        """
        Добавляет или обновляет постоянного приглашённого.
        Возвращает True если добавлен, False если обновлён.
        """
        with get_session_context() as session:
            email_norm = email.strip().lower()
            existing = session.scalar(
                select(PermanentInvited).where(
                    func.lower(PermanentInvited.email) == email_norm
                )
            )
            phone_norm = _normalize_phone(phone) if phone else None
            if existing:
                existing.full_name = full_name.strip() or None
                existing.phone = phone_norm
                logger.info("save_permanent_invited: обновлён %s", email_norm)
                return False
            else:
                perm_inv = PermanentInvited(
                    full_name=full_name.strip() or None,
                    email=email_norm,
                    phone=phone_norm,
                )
                session.add(perm_inv)
                logger.info("save_permanent_invited: добавлен %s", email_norm)
                return True

    def delete_permanent_invited(self, email: str) -> bool:
        """
        Удаляет постоянного приглашённого по email.
        Возвращает True если удалён, False если не найден.
        """
        with get_session_context() as session:
            email_norm = email.strip().lower()
            perm_inv = session.scalar(
                select(PermanentInvited).where(
                    func.lower(PermanentInvited.email) == email_norm
                )
            )
            if not perm_inv:
                return False
            session.delete(perm_inv)
            logger.info("delete_permanent_invited: удалён %s", email_norm)
            return True

    def search_permanent_invited(self, query: str) -> List[Dict[str, Any]]:
        """
        Ищет постоянных приглашённых по ФИО или email.
        Поиск выполняется на стороне Python для надёжности с NULL значениями.
        """
        query_lower = query.strip().lower()
        if not query_lower:
            return []
        
        all_permanent = self.get_permanent_invited_list()
        results = []
        
        for perm in all_permanent:
            full_name = (perm.get("full_name") or "").strip()
            email = (perm.get("email") or "").strip()
            
            full_name_lower = full_name.lower() if full_name else ""
            email_lower = email.lower() if email else ""
            
            if query_lower in full_name_lower or query_lower in email_lower:
                results.append(perm)
        
        return results
