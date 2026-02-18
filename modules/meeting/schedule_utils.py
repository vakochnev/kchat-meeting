"""
Утилиты для работы с расписанием собраний из конфигурации.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def calculate_next_meeting_date(schedule: Dict[str, Any]) -> Optional[datetime]:
    """
    Вычисляет следующую дату собрания на основе расписания.
    
    Поддерживает типы:
    - weekly: день недели (0=понедельник, 6=воскресенье) и время
    - daily: каждый день в указанное время
    
    Args:
        schedule: словарь с полями type, time и опционально day_of_week
        
    Returns:
        datetime объект с датой и временем следующего собрания или None при ошибке
    """
    schedule_type = schedule.get("type", "").lower()
    time_str = schedule.get("time", "").strip()
    
    if not time_str:
        logger.warning("calculate_next_meeting_date: время не указано в расписании")
        return None
    
    # Парсим время
    try:
        if ":" in time_str:
            parts = time_str.split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
        else:
            # Если время без разделителя (например "1100")
            if len(time_str) >= 4:
                hour = int(time_str[:2])
                minute = int(time_str[2:4])
            else:
                logger.warning("calculate_next_meeting_date: некорректный формат времени: %s", time_str)
                return None
    except (ValueError, IndexError) as e:
        logger.warning("calculate_next_meeting_date: ошибка парсинга времени %s: %s", time_str, e)
        return None
    
    if not (0 <= hour <= 23) or not (0 <= minute <= 59):
        logger.warning("calculate_next_meeting_date: некорректное время: %02d:%02d", hour, minute)
        return None
    
    now = datetime.now()
    today = now.date()
    
    if schedule_type == "daily":
        # Каждый день в указанное время
        next_date = datetime.combine(today, datetime.min.time().replace(hour=hour, minute=minute))
        # Если время уже прошло сегодня, берём завтра
        if next_date <= now:
            next_date += timedelta(days=1)
        return next_date
    
    elif schedule_type == "weekly":
        # Каждую неделю в указанный день недели
        day_of_week = schedule.get("day_of_week")
        if day_of_week is None:
            logger.warning("calculate_next_meeting_date: day_of_week не указан для weekly")
            return None
        
        try:
            day_of_week = int(day_of_week)
        except (ValueError, TypeError):
            logger.warning("calculate_next_meeting_date: некорректный day_of_week: %s", day_of_week)
            return None
        
        if not (0 <= day_of_week <= 6):
            logger.warning("calculate_next_meeting_date: day_of_week вне диапазона 0-6: %s", day_of_week)
            return None
        
        # Текущий день недели (0=понедельник, 6=воскресенье)
        current_weekday = today.weekday()
        
        # Вычисляем количество дней до следующего нужного дня недели
        days_ahead = day_of_week - current_weekday
        
        # Если день уже прошёл на этой неделе или сегодня этот день, но время уже прошло
        target_date = today + timedelta(days=days_ahead)
        target_datetime = datetime.combine(target_date, datetime.min.time().replace(hour=hour, minute=minute))
        
        if target_datetime <= now:
            # Берём следующий раз (через неделю)
            target_date += timedelta(days=7)
            target_datetime = datetime.combine(target_date, datetime.min.time().replace(hour=hour, minute=minute))
        
        return target_datetime
    
    elif schedule_type == "cron":
        # Cron пока не поддерживается (требуется библиотека croniter)
        logger.warning("calculate_next_meeting_date: тип 'cron' пока не поддерживается")
        return None
    
    else:
        logger.warning("calculate_next_meeting_date: неизвестный тип расписания: %s", schedule_type)
        return None


def format_date_for_meeting(dt: datetime) -> tuple[str, str]:
    """
    Форматирует datetime в формат даты и времени для собрания.
    
    Returns:
        (date_str, time_str) где date_str в формате "DD.MM.YYYY", time_str в формате "HH:MM"
    """
    date_str = dt.strftime("%d.%m.%Y")
    time_str = dt.strftime("%H:%M")
    return (date_str, time_str)
