"""
Парсинг и валидация списка приглашённых (формат: ФИО | email | телефон).
Поддерживаемые разделители полей: ' | ', '|', ';'.
"""
import logging
import re
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Разделитель формата: ФИО | email | phone
INVITED_LINE_SEP = " | "


def _split_line(line: str) -> Optional[List[str]]:
    """Разбивает строку по первому найденному разделителю: ' | ', '|' или ';'."""
    if INVITED_LINE_SEP in line:
        return [p.strip() for p in line.split(INVITED_LINE_SEP, 2)]
    if "|" in line:
        return [p.strip() for p in line.split("|", 2)]
    if ";" in line:
        return [p.strip() for p in line.split(";", 2)]
    return None


def parse_invited_line(line: str) -> Optional[Dict[str, str]]:
    """
    Парсит строку формата: ФИО | email@example.com | +79991234567.
    Телефон может быть пустым. Принимает разделители: ' | ', '|', ';'.

    Returns:
        dict с ключами full_name, email, phone или None если строка невалидна.
    """
    if not line:
        return None
    parts = _split_line(line)
    if parts is None:
        return None
    full_name = (parts[0] or "").strip()
    if not full_name:
        return None
    email = (parts[1] if len(parts) > 1 else "").strip()
    phone = (parts[2] if len(parts) > 2 else "").strip()
    return {"full_name": full_name, "email": email or "", "phone": phone or ""}


def validate_invited_row(row: Dict[str, str]) -> Tuple[bool, Optional[str]]:
    """
    Валидирует запись приглашённого.
    Требуется: ФИО и хотя бы email или телефон.

    Returns:
        (is_valid, error_message)
    """
    full_name = (row.get("full_name") or "").strip()
    email = (row.get("email") or "").strip()
    phone = (row.get("phone") or "").strip()
    if not full_name:
        return False, "Пустое ФИО"
    if not email and not phone:
        return False, "Укажите email или телефон"
    if email and not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return False, f"Некорректный email: {email}"
    return True, None


def parse_invited_list(text: str) -> List[Dict[str, str]]:
    """
    Извлекает из текста список приглашённых в формате ФИО | email | phone.
    Каждая строка — один человек. Пропускает невалидные строки.
    """
    result: List[Dict[str, str]] = []
    lines = text.splitlines()
    logger.debug("parse_invited_list: строк=%d %r", len(lines), lines[:5])
    for line in lines:
        line = line.strip()
        if not line:
            continue
        parsed = parse_invited_line(line)
        if parsed:
            valid, err = validate_invited_row(parsed)
        else:
            valid, err = False, "не распознано"
        logger.debug(
            "parse_invited_list: line=%r -> parsed=%s valid=%s err=%s",
            line[:80], parsed, valid, err,
        )
        if parsed and valid:
            result.append(parsed)
    return result
