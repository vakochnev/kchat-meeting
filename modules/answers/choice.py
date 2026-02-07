"""
Обработчик ответов с выбором из вариантов.
"""
from typing import Dict, Any, Tuple, Optional, List

from messenger_bot_api import InlineMessageButton

from .base import AnswerHandler


class ChoiceAnswerHandler(AnswerHandler):
    """Обработчик вопросов с выбором из вариантов."""
    
    def validate(self, question: Dict[str, Any], value: Any) -> Tuple[bool, Optional[str]]:
        """Проверяет, что значение входит в допустимые варианты."""
        options = question.get("options", [])
        valid_values = [opt.get("value", opt.get("label")) for opt in options]
        
        if value not in valid_values:
            return False, "Выберите один из предложенных вариантов"
        
        return True, None
    
    def format_value(self, question: Dict[str, Any], value: Any) -> str:
        """Возвращает label для выбранного значения."""
        options = question.get("options", [])
        for opt in options:
            if opt.get("value", opt.get("label")) == value:
                return opt.get("label", str(value))
        return str(value)
    
    def build_buttons(
        self,
        question: Dict[str, Any],
        question_id: str,
    ) -> List[InlineMessageButton]:
        """Создаёт кнопки для каждого варианта."""
        buttons = []
        options = question.get("options", [])
        
        for i, opt in enumerate(options):
            label = opt.get("label", opt.get("value", f"Вариант {i+1}"))
            value = opt.get("value", label)
            
            buttons.append(InlineMessageButton(
                id=i + 1,
                label=label,
                callback_message=f"✅ {label}",
                callback_data=f"answer_{question_id}_{value}"
            ))
        
        return buttons
