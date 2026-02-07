"""
Модели базы данных.
"""
import json
from datetime import datetime
from typing import Dict, Any

from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Базовый класс для моделей."""
    pass


class BaseModel(Base):
    """Базовый класс для моделей с общими полями."""
    
    __abstract__ = True
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


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
