"""
Валидаторы ввода для диалогов (по образцу kchat-bot).
"""
import re
from datetime import date, datetime, timedelta
from typing import Optional, Tuple


def validate_meeting_time(value: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Валидирует время собрания. Принимает разделители: ":", "-", " ", "." или без разделителя.
    Некорректные символы отбрасываются (оставляются только цифры).

    Returns:
        (is_valid, normalized_value_or_error_message, error_message)
        При успехе: (True, "HH:MM", None)
        При ошибке: (False, None, "сообщение об ошибке")
    """
    if not value or not str(value).strip():
        return False, None, "❌ Время не может быть пустым"

    raw = str(value).strip()
    digits = re.sub(r"\D", "", raw)

    if not digits:
        return False, None, "❌ Введите время цифрами в формате ЧЧ:ММ (например: 10:00)"

    # Нормализация: заменяем разделители на ":"
    normalized_input = re.sub(r"[-:\s.]+", ":", raw).strip(":-. ")
    parts = [p for p in re.split(r"[-:\s.]+", raw) if p]

    if len(parts) >= 2:
        # Есть разделитель: "10:30", "10-30", "10 00"
        try:
            h, m = int(parts[0]), int(parts[1])
        except ValueError:
            h, m = None, None
    else:
        # Без разделителя: "1030", "930", "10"
        if len(digits) == 1:
            h, m = int(digits), 0
        elif len(digits) == 2:
            h, m = int(digits), 0
        elif len(digits) == 3:
            h, m = int(digits[0]), int(digits[1:3])
        elif len(digits) >= 4:
            h, m = int(digits[:2]), int(digits[2:4])
        else:
            h, m = None, None

    if h is None or m is None:
        return False, None, "❌ Неверный формат времени. Используйте ЧЧ:ММ (например: 10:00)"

    if not (0 <= h <= 23):
        return False, None, "❌ Часы должны быть от 0 до 23"
    if not (0 <= m <= 59):
        return False, None, "❌ Минуты должны быть от 0 до 59"

    result = f"{h:02d}:{m:02d}"
    return True, result, None


def validate_meeting_date(value: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Валидирует дату собрания в формате ДД.ММ.ГГГГ (или ДД.ММ.ГГ).
    Принимает разделители: точка, дефис, слэш.

    Returns:
        (is_valid, normalized_value_or_error_message, error_message)
        При успехе: (True, "DD.MM.YYYY", None)
        При ошибке: (False, None, "сообщение об ошибке")
    """
    if not value or not str(value).strip():
        return False, None, "❌ Дата не может быть пустой"

    normalized = str(value).strip().replace("-", ".").replace("/", ".")

    try:
        parsed = datetime.strptime(normalized, "%d.%m.%Y").date()
    except ValueError:
        try:
            parsed = datetime.strptime(normalized, "%d.%m.%y").date()
        except ValueError:
            return False, None, "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ (например: 16.02.2026)"

    today = date.today()
    if parsed < today:
        return False, None, "❌ Дата собрания не может быть в прошлом"

    max_date = today + timedelta(days=30)
    if parsed > max_date:
        return False, None, "❌ Дата не может быть более чем на 30 дней вперёд"

    result = parsed.strftime("%d.%m.%Y")
    return True, result, None
