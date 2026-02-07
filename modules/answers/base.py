"""
Базовый класс обработчика ответов.
"""
from typing import Dict, Any, Tuple, Optional, List

from messenger_bot_api import InlineMessageButton


class AnswerHandler:
    """Базовый обработчик ответов на вопросы."""
    
    def validate(self, question: Dict[str, Any], value: Any) -> Tuple[bool, Optional[str]]:
        """
        Валидирует ответ.
        
        Returns:
            (is_valid, error_message)
        """
        return True, None
    
    def format_value(self, question: Dict[str, Any], value: Any) -> str:
        """Форматирует значение для отображения."""
        return str(value)
    
    def build_buttons(
        self,
        question: Dict[str, Any],
        question_id: str,
    ) -> List[InlineMessageButton]:
        """Создаёт кнопки для вопроса."""
        return []
    
    def expects_text_input(self) -> bool:
        """Возвращает True если ожидается текстовый ввод."""
        return False
