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
    
    # Настройки совещаний
    # (оставлено для совместимости, если понадобится)
    
    def validate(self) -> None:
        """Проверяет обязательные настройки."""
        if not self.bot_token:
            raise ValueError("BOT_TOKEN не указан")
        if not self.meeting_dir.exists():
            self.meeting_dir.mkdir(parents=True, exist_ok=True)


# Глобальный экземпляр конфигурации
config = Config()
