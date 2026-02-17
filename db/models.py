"""
Модели базы данных (SQLAlchemy 2.0 / Mapped style).
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Базовый класс для моделей."""
    pass


class BaseModel(Base):
    """Базовый класс для моделей с общими полями id, created_at, updated_at."""

    __abstract__ = True

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        server_default=func.now(),
    )


class User(BaseModel):
    """Пользователь, начавший чат с ботом. Один на (sender_id, group_id, workspace_id)."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint(
            "sender_id", "group_id", "workspace_id",
            name="uq_users_sender_group_workspace",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sender_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    group_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    workspace_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    def __repr__(self) -> str:
        return f"<User(id={self.id}, sender_id={self.sender_id}, email={self.email})>"


class Meeting(BaseModel):
    """Совещание (собрание)."""

    __tablename__ = "meetings"

    topic: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    date: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # "16.02.2026"
    time: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # "10:00"
    place: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    link: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    invited = relationship(
        "Invited", back_populates="meeting", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Meeting(id={self.id}, topic={self.topic})>"


class MeetingAdmin(BaseModel):
    """Администратор (общий для всех собраний). Email и ФИО для приветствия."""

    __tablename__ = "meeting_admins"

    email: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:
        return f"<MeetingAdmin(id={self.id}, email={self.email})>"


class Invited(BaseModel):
    """
    Приглашённый на совещание.
    Объединяет список приглашённых и ответы о присутствии (answer, status).
    Связь: meeting.
    Дубликаты по (meeting_id, email) запрещены.
    """

    __tablename__ = "invited"
    __table_args__ = (UniqueConstraint("meeting_id", "email", name="uq_invited_meeting_email"),)

    meeting_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    answer: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    kchat_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    sms_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    meeting = relationship("Meeting", back_populates="invited")

    def __repr__(self) -> str:
        return f"<Invited(id={self.id}, meeting_id={self.meeting_id}, full_name={self.full_name})>"
