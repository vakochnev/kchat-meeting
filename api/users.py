"""
API для получения информации о пользователях K-CHAT.
Заимствовано из проекта kchat-opros.
"""
import logging
from typing import Any, Dict, Optional

import requests

from config import config

logger = logging.getLogger(__name__)


# def _normalize_job_title(value: Any) -> Optional[str]:
#     """
#     Возвращает строку должности или None.
#     Числовые значения (ID должности, напр. 113) не считаются названием — отбрасываются.
#     """
#     if value is None:
#         return None
#     s = str(value).strip()
#     if not s or s.isdigit():
#         return None
#     return s


def get_user_info(user_id: int) -> Dict[str, Any]:
    """
    Получает информацию о пользователе по ID через API K-CHAT.

    Args:
        user_id: ID пользователя (sender_id из события).

    Returns:
        Словарь с полями пользователя (name, email, phone, username и т.д.)
        или пустой словарь при ошибке.
    """
    try:
        url = f"{config.api_base_url}/api/v1/users/getUser"
        headers = {"Authorization": config.bot_token}
        payload = {"userId": user_id}

        timeout = getattr(config, "request_timeout", 30)
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=timeout,
        )

        if response.status_code == 200:
            result = response.json()
            return result.get("user", {})
        logger.warning(
            "Ошибка получения информации о пользователе: %s",
            response.status_code,
        )
        return {}

    except requests.exceptions.Timeout:
        logger.error(
            "Таймаут при запросе информации о пользователе %s",
            user_id,
        )
        return {}
    except requests.exceptions.ConnectionError as e:
        logger.error(
            "Ошибка соединения при запросе информации о пользователе: %s",
            e,
        )
        return {}
    except Exception as e:
        logger.error(
            "Ошибка получения информации о пользователе: %s",
            e,
            exc_info=True,
        )
        return {}


def user_info_to_user_data(user_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Преобразует ответ API getUser в словарь полей.
    API может присылать name или отдельно last_name, first_name, middle_name.
    Результат используется в _merge_user_data; при сохранении в БД вызывается
    _build_full_name() для объединения в full_name.

    Args:
        user_info: Словарь из get_user_info (user из API).

    Returns:
        Словарь с ключами last_name, first_name, middle_name (формат из API),
        email, phone, username, job_title.
    """
    if not user_info:
        return {}

    def get_str(*keys: str) -> str:
        for k in keys:
            v = user_info.get(k)
            if v is not None and str(v).strip():
                return str(v).strip()
        return ""

    email = get_str("email") or ""
    username = (
        get_str("username", "login", "userName", "user_name")
        or (email.split("@")[0] if "@" in email else email)
        or ""
    )
    phone = get_str("phone", "phoneNumber") or None
    if phone == "":
        phone = None
    job_title = (#_normalize_job_title(
        user_info.get("job_title") or user_info.get("jobTitle") or user_info.get("position")
    )

    name = get_str("name")
    if name:
        name_parts = name.split(maxsplit=2)
        if len(name_parts) >= 3:
            last_name, first_name, middle_name = (
                name_parts[0], name_parts[1], name_parts[2]
            )
        elif len(name_parts) == 2:
            last_name, first_name = name_parts[0], name_parts[1]
            middle_name = ""
        elif len(name_parts) == 1:
            last_name = name_parts[0]
            first_name = ""
            middle_name = ""
        else:
            last_name = first_name = middle_name = ""
    else:
        last_name = get_str("last_name", "lastName", "surname")
        first_name = get_str("first_name", "firstName", "name")
        middle_name = get_str("middle_name", "middleName")

    return {
        "last_name": last_name or None,
        "first_name": first_name or None,
        "middle_name": middle_name or None,
        "email": email or None,
        "phone": phone,
        "username": username or None,
        "job_title": job_title,
    }
