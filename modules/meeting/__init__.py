"""
Модуль для работы с совещаниями.
"""
from .handler import MeetingHandler
from .storage import MeetingStorage
from .service import MeetingService
from .api_client import BackendAPIClient
from .config_manager import MeetingConfigManager

__all__ = [
    'MeetingHandler',
    'MeetingStorage',
    'MeetingService',
    'BackendAPIClient',
    'MeetingConfigManager',
]
