"""
Конфигурация бота совещаний.
"""
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

# Загружаем .env
load_dotenv()


@dataclass
class Config:
    """Конфигурация приложения."""
    
    # Пути
    base_dir: Path = field(
        default_factory=lambda: Path(__file__).parent
    )
    meeting_dir: Path = field(
        default_factory=lambda: (
            Path(__file__).parent / "config" / "meeting"
        )
    )
    
    # Бот
    bot_token: str = field(
        default_factory=lambda: os.getenv("BOT_TOKEN", "")
    )
    
    # API URLs
    api_base_url: str = field(
        default_factory=lambda: os.getenv(
            "API_BASE_URL",
            "https://api.kchat.app"
        )
    )
    sse_base_url: str = field(
        default_factory=lambda: os.getenv(
            "SSE_BASE_URL",
            "https://pusher.kchat.app"
        )
    )
    # База данных
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            "sqlite:///meeting.db"
        )
    )
    
    # Логирование
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    log_file: Optional[str] = field(default_factory=lambda: os.getenv("LOG_FILE"))

    smtp_host: str = field(
        default_factory=lambda: os.getenv("SMTP_HOST", "")
    )
    smtp_port: str = field(
        default_factory=lambda: os.getenv("SMTP_PORT", "")
    )
    smtp_user: str = field(
        default_factory=lambda: os.getenv("SMTP_USER", "")
    )
    smtp_password: str = field(
        default_factory=lambda: os.getenv("SMTP_PASSWORD", "")
    )
    smtp_sender: str = field(
        default_factory=lambda: os.getenv("SMTP_SENDER", "")
    )

    email_template_path: str = field(
        default_factory=lambda: os.getenv("EMAIL_TEMPLATE_PATH", "")
    )
    
    # Настройки совещаний
    # (оставлено для совместимости, если понадобится)
    
    def validate(self) -> None:
        """Проверяет обязательные настройки."""
        if not self.bot_token:
            raise ValueError("BOT_TOKEN не указан")


# Глобальный экземпляр конфигурации
config = Config()
