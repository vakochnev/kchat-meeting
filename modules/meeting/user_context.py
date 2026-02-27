"""
Хранилище контекста пользователя: фильтр приглашённых и режим просмотра участников.
Используется для корректной пагинации и команды /все.
"""
from typing import Optional


class UserContextStore:
    """
    Хранит по sender_id:
    - filter_context: активный фильтр приглашённых (None, "voted", "not_voted");
    - participants_context: пользователь просматривает список участников (True/False).
    """

    def __init__(self) -> None:
        self._filter_context: dict[int, Optional[str]] = {}
        self._participants_context: dict[int, bool] = {}

    def set_participants_context(self, sender_id: Optional[int], value: bool) -> None:
        """Устанавливает контекст просмотра участников."""
        if sender_id is not None:
            self._participants_context[sender_id] = value

    def get_participants_context(self, sender_id: Optional[int]) -> bool:
        """Возвращает True, если пользователь в контексте участников."""
        if sender_id is None:
            return False
        return self._participants_context.get(sender_id, False)

    def set_filter_context(self, sender_id: Optional[int], value: Optional[str]) -> None:
        """Устанавливает контекст фильтра приглашённых (None, "voted", "not_voted")."""
        if sender_id is not None:
            self._filter_context[sender_id] = value

    def get_filter_context(self, sender_id: Optional[int]) -> Optional[str]:
        """Возвращает текущий фильтр приглашённых для пользователя."""
        if sender_id is None:
            return None
        return self._filter_context.get(sender_id)

    def switch_to_invited(self, sender_id: Optional[int]) -> None:
        """Переход в режим приглашённых: сброс контекста участников."""
        if sender_id is not None:
            self._participants_context[sender_id] = False

    def switch_to_invited_list(self, sender_id: Optional[int]) -> None:
        """Переход к списку приглашённых без фильтра: сброс участников и фильтра."""
        if sender_id is not None:
            self._participants_context[sender_id] = False
            self._filter_context[sender_id] = None

    def switch_to_invited_with_filter(
        self, sender_id: Optional[int], filter_type: Optional[str]
    ) -> None:
        """Переход в режим приглашённых с заданным фильтром; сброс контекста участников."""
        if sender_id is not None:
            self._participants_context[sender_id] = False
            self._filter_context[sender_id] = filter_type

    def switch_to_invited_all(self, sender_id: Optional[int]) -> None:
        """Команда /все для приглашённых: сброс фильтра и контекста участников."""
        if sender_id is not None:
            self._filter_context[sender_id] = None
            self._participants_context[sender_id] = False

    def switch_to_participants(self, sender_id: Optional[int]) -> None:
        """Переход в режим участников."""
        if sender_id is not None:
            self._participants_context[sender_id] = True

    def reset_participants_for_page(self, sender_id: Optional[int]) -> None:
        """Сброс контекста участников при переходе на страницу приглашённых."""
        if sender_id is not None:
            self._participants_context[sender_id] = False
