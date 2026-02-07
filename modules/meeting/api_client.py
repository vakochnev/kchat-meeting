"""
Клиент для отправки данных на бэкенд API.
"""
import logging
from typing import Dict, Any, Optional

import requests

from config import config

logger = logging.getLogger(__name__)


class BackendAPIClient:
    """Клиент для взаимодействия с бэкенд API."""
    
    def __init__(self):
        self.base_url = config.backend_api_url
        self.timeout = 30
    
    def send_meeting_response(
        self,
        user_data: Dict[str, Any],
    ) -> bool:
        """
        Отправляет данные пользователя совещания на бэкенд.
        
        Передаёт все поля из таблицы meeting_users включая ответ.
        
        Args:
            user_data: Данные пользователя из MeetingUser (все поля).
            
        Returns:
            True если успешно отправлено, False в противном случае.
        """
        if not self.base_url:
            logger.warning("BACKEND_API_URL не указан в конфигурации")
            return False
        
        url = f"{self.base_url}/api/v1/meetings/responses"
        
        # Передаём все поля из таблицы
        payload = {
            "id": user_data.get("id"),
            "sender_id": user_data.get("sender_id"),
            "group_id": user_data.get("group_id"),
            "workspace_id": user_data.get("workspace_id"),
            "username": user_data.get("username"),
            "email": user_data.get("email"),
            "phone": user_data.get("phone"),
            "job_title": user_data.get("job_title"),
            "last_name": user_data.get("last_name"),
            "middle_name": user_data.get("middle_name"),
            "first_name": user_data.get("first_name"),
            "meeting_datetime": user_data.get("meeting_datetime"),
            "answer": user_data.get("answer"),
            "status": user_data.get("status"),
            "created_at": user_data.get("created_at"),
            "updated_at": user_data.get("updated_at"),
        }
        
        headers = {
            "Content-Type": "application/json",
        }
        
        # Если есть токен авторизации
        if (
            hasattr(config, "backend_api_token")
            and config.backend_api_token
        ):
            headers["Authorization"] = (
                f"Bearer {config.backend_api_token}"
            )
        
        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            
            if response.status_code in (200, 201):
                logger.info(
                    "Данные успешно отправлены на бэкенд: sender_id=%s",
                    user_data.get("sender_id")
                )
                return True
            else:
                logger.error(
                    "Ошибка отправки данных на бэкенд: HTTP %s, %s",
                    response.status_code,
                    response.text[:200]
                )
                return False
        
        except requests.exceptions.RequestException as e:
            logger.error("Ошибка запроса к бэкенду: %s", e)
            return False
