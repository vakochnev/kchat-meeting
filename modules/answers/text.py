"""
Обработчик текстовых ответов.
"""
from typing import Dict, Any, Tuple, Optional, List

from messenger_bot_api import InlineMessageButton

from .base import AnswerHandler


class TextAnswerHandler(AnswerHandler):
    """Обработчик вопросов с текстовым вводом."""
    
    def validate(self, question: Dict[str, Any], value: Any) -> Tuple[bool, Optional[str]]:
        """Проверяет длину текста."""
        if not isinstance(value, str):
            return False, "Введите текст"
        
        text = value.strip()
        
        if not text and question.get("required", True):
            return False, "Ответ не может быть пустым"
        
        min_len = question.get("min_length", 0)
        max_len = question.get("max_length", 10000)
        
        if len(text) < min_len:
            return False, f"Минимальная длина: {min_len} символов"
        
        if len(text) > max_len:
            return False, f"Максимальная длина: {max_len} символов"
        
        return True, None
    
    def format_value(self, question: Dict[str, Any], value: Any) -> str:
        """Возвращает текст, обрезая если слишком длинный."""
        text = str(value)
        if len(text) > 100:
            return text[:97] + "..."
        return text
    
    def build_buttons(
        self,
        question: Dict[str, Any],
        question_id: str,
    ) -> List[InlineMessageButton]:
        """Для текстового ввода кнопки не нужны."""
        return []
    
    def expects_text_input(self) -> bool:
        """Текстовый обработчик ожидает ввод."""
        return True
