"""
Обработчики типов ответов.
"""
from .base import AnswerHandler
from .choice import ChoiceAnswerHandler
from .rating import RatingAnswerHandler
from .text import TextAnswerHandler
from .yes_no import YesNoAnswerHandler

ANSWER_HANDLERS = {
    "choice": ChoiceAnswerHandler(),
    "rating": RatingAnswerHandler(),
    "text": TextAnswerHandler(),
    "yes_no": YesNoAnswerHandler(),
}


def get_answer_handler(question_type: str) -> AnswerHandler:
    """Возвращает обработчик для типа вопроса."""
    return ANSWER_HANDLERS.get(question_type, AnswerHandler())


__all__ = [
    'AnswerHandler',
    'ChoiceAnswerHandler',
    'RatingAnswerHandler',
    'TextAnswerHandler',
    'YesNoAnswerHandler',
    'ANSWER_HANDLERS',
    'get_answer_handler',
]
