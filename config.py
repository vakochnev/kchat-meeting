"""
Конфигурация бота совещаний.
"""
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

from dotenv import load_dotenv

try:
    import yaml
except ImportError:
    yaml = None

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
    
    # Настройки совещаний из config.yml
    meeting_settings: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Загружает настройки собраний из config.yml после инициализации."""
        self._load_meeting_settings()
    
    def _load_meeting_settings(self) -> None:
        """Загружает настройки собраний из config/meeting_settings.yml."""
        if yaml is None:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("PyYAML не установлен, настройки собраний не загружены")
            self.meeting_settings = {}
            return
        
        settings_file = self.base_dir / "config" / "meeting_settings.yml"
        if settings_file.exists():
            try:
                with open(settings_file, "r", encoding="utf-8") as f:
                    self.meeting_settings = yaml.safe_load(f) or {}
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(
                    "Не удалось загрузить настройки собраний из %s: %s",
                    settings_file, e
                )
                self.meeting_settings = {}
        else:
            self.meeting_settings = {}
    
    def get_meeting_schedules(self) -> List[Dict[str, Any]]:
        """Возвращает список расписаний собраний из конфигурации."""
        return self.meeting_settings.get("meetings", [])
    
    def validate(self) -> None:
        """Проверяет обязательные настройки."""
        if not self.bot_token:
            raise ValueError("BOT_TOKEN не указан")


# Глобальный экземпляр конфигурации
config = Config()
