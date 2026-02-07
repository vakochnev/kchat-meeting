"""
Обработчик ответов Да/Нет.
"""
from typing import Dict, Any, Tuple, Optional, List

from messenger_bot_api import InlineMessageButton

from .base import AnswerHandler


class YesNoAnswerHandler(AnswerHandler):
    """Обработчик вопросов Да/Нет."""
    
    def validate(self, question: Dict[str, Any], value: Any) -> Tuple[bool, Optional[str]]:
        """Проверяет, что значение yes или no."""
        if value not in ("yes", "no"):
            return False, "Выберите Да или Нет"
        return True, None
    
    def format_value(self, question: Dict[str, Any], value: Any) -> str:
        """Возвращает Да или Нет."""
        return "Да" if value == "yes" else "Нет"
    
    def build_buttons(
        self,
        question: Dict[str, Any],
        question_id: str,
    ) -> List[InlineMessageButton]:
        """Создаёт кнопки Да/Нет."""
        return [
            InlineMessageButton(
                id=1,
                label="✅ Да",
                callback_message="✅ Да",
                callback_data=f"answer_{question_id}_yes"
            ),
            InlineMessageButton(
                id=2,
                label="❌ Нет",
                callback_message="❌ Нет",
                callback_data=f"answer_{question_id}_no"
            ),
        ]
