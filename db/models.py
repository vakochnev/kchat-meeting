"""
Модели базы данных.
"""
import json
from datetime import datetime
from typing import Dict, Any

from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Базовый класс для моделей."""
    pass


class BaseModel(Base):
    """Базовый класс для моделей с общими полями."""
    
    __abstract__ = True
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Meeting(BaseModel):
    """Совещание (собрание)."""
    
    __tablename__ = "meetings"
    
    topic = Column(String(500), nullable=True)
    url = Column(String(500), nullable=True)
    date = Column(String(50), nullable=True)  # "16.02.2026"
    time = Column(String(50), nullable=True)  # "10:00"
    datetime_utc = Column(DateTime, nullable=True, index=True)  # разобранные дата+время
    place = Column(String(255), nullable=True)
    link = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)  # текущее активное совещание
    
    invited = relationship("Invited", back_populates="meeting", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<Meeting(id={self.id}, topic={self.topic})>"


class Invited(BaseModel):
    """Приглашённый на совещание."""
    
    __tablename__ = "invited"
    
    meeting_id = Column(Integer, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    last_name = Column(String(100), nullable=True)
    first_name = Column(String(100), nullable=True)
    middle_name = Column(String(100), nullable=True)
    email = Column(String(255), nullable=True, index=True)
    phone = Column(String(50), nullable=True)
    login = Column(String(100), nullable=True)
    
    meeting = relationship("Meeting", back_populates="invited")
    
    def __repr__(self) -> str:
        return f"<Invited(id={self.id}, {self.last_name} {self.first_name})>"


class MeetingUser(BaseModel):
    """Данные пользователя совещания из SSE событий."""
    
    __tablename__ = "meeting_users"
    
    # Данные из SSE
    sender_id = Column(Integer, nullable=False, index=True)
    group_id = Column(Integer, nullable=False, index=True)
    workspace_id = Column(Integer, nullable=False, index=True)
    username = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True, index=True)
    phone = Column(String(50), nullable=True, index=True)
    job_title = Column(String(255), nullable=True)
    last_name = Column(String(100), nullable=True)
    middle_name = Column(String(100), nullable=True)
    first_name = Column(String(100), nullable=True)
    
    # Данные совещания
    meeting_datetime = Column(DateTime, nullable=True, index=True)
    
    # Ответ пользователя
    answer = Column(String(50), nullable=True)  # "yes" или "no"
    status = Column(String(50), nullable=True)  # статус отправки на бэкенд
    
    def __repr__(self) -> str:
        return (
            f"<MeetingUser(id={self.id}, sender_id={self.sender_id}, "
            f"email={self.email}, answer={self.answer}, status={self.status})>"
        )
