"""
Модуль для работы с совещаниями.
"""
from .handler import MeetingHandler
from .storage import MeetingStorage
from .service import MeetingService
from .config_manager import MeetingConfigManager

__all__ = [
    'MeetingHandler',
    'MeetingStorage',
    'MeetingService',
    'MeetingConfigManager',
]
