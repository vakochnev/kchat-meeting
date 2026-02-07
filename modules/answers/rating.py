"""
Обработчик ответов с рейтингом/оценкой.
"""
from typing import Dict, Any, Tuple, Optional, List

from messenger_bot_api import InlineMessageButton

from .base import AnswerHandler


class RatingAnswerHandler(AnswerHandler):
    """Обработчик вопросов с оценкой по шкале."""
    
    def validate(self, question: Dict[str, Any], value: Any) -> Tuple[bool, Optional[str]]:
        """Проверяет, что значение входит в допустимый диапазон."""
        try:
            val = int(value)
        except (ValueError, TypeError):
            return False, "Введите число"
        
        min_val = question.get("min", 1)
        max_val = question.get("max", 5)
        
        if not (min_val <= val <= max_val):
            return False, f"Выберите значение от {min_val} до {max_val}"
        
        return True, None
    
    def format_value(self, question: Dict[str, Any], value: Any) -> str:
        """Возвращает значение с меткой если есть."""
        labels = question.get("labels", {})
        label = labels.get(str(value))
        
        if label:
            return f"{value} ({label})"
        return str(value)
    
    def build_buttons(
        self,
        question: Dict[str, Any],
        question_id: str,
    ) -> List[InlineMessageButton]:
        """Создаёт кнопки для шкалы оценки."""
        buttons = []
        min_val = question.get("min", 1)
        max_val = question.get("max", 5)
        labels = question.get("labels", {})
        
        for val in range(min_val, max_val + 1):
            label = labels.get(str(val), str(val))
            
            buttons.append(InlineMessageButton(
                id=val,
                label=label,
                callback_message=f"✅ {label}",
                callback_data=f"answer_{question_id}_{val}"
            ))
        
        return buttons
