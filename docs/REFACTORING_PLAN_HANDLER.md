# План рефакторинга modules/meeting/handler.py

## Текущее состояние

- **Размер:** ~2028 строк, один класс `MeetingHandler` с 40+ методами.
- **Проблемы:**
  - Нарушение **Single Responsibility**: парсинг команд, контексты пользователя, приглашённые, участники, собрания, голосование, кнопки — всё в одном классе.
  - Длинные методы: `handle_message` (~316 строк), `_handle_command` (~100+ строк), `_handle_invited` (~185 строк), `_handle_participants` (~140 строк).
  - Дублирование: сброс/установка контекста участников и фильтра приглашённых повторяется в 10+ местах.
  - Жёсткая цепочка `if/elif` для разрешения команды и для диспетчеризации — сложно расширять (Open/Closed).
  - Утилиты парсинга списка приглашённых (`_parse_invited_line`, `_validate_invited_row`, `_parse_invited_list`) логически не привязаны к handler — их лучше вынести.
  - Смешение формирования UI (кнопки, тексты сообщений) с бизнес-логикой.

## Цели

- Упростить сопровождение и чтение кода.
- Соблюдать SOLID и паттерны проекта (Strategy, Factory, явное выделение ответственности).
- Сохранить текущее поведение (рефакторинг без изменения контрактов снаружи).

## Предлагаемая структура (паттерны и модули)

### 1. Контекст пользователя (State / хранилище)

**Модуль:** `modules/meeting/user_context.py`

**Класс:** `UserContextStore`

- Хранит `filter_context` (invited: voted/not_voted/None) и `participants_context` (bool) по `sender_id`.
- Методы: `set_participants_context(sender_id, value)`, `set_filter_context(sender_id, value)`, `get_...`, `reset_for_invited(sender_id)`, `reset_for_participants(sender_id)` (при необходимости).
- Убирает дублирование разбросанных обращений к `_user_filter_context` и `_user_participants_context` и централизует правила сброса.

**Паттерн:** по сути — State/хранилище контекста диалога.

---

### 2. Разрешение команды из текста (Chain of Responsibility / Strategy)

**Модуль:** `modules/meeting/command_resolver.py`

**Класс:** `CommandResolver`

- Вход: `(text_lower: str, sender_id: int | None, user_context: UserContextStore)`.
- Выход: `str | None` — идентификатор команды (`"start"`, `"invited"`, `"participants_page"`, `"invited_all"`, и т.д.) или `None`.
- Логика вынесена из начала `handle_message`: таблица COMMANDS, специальные правила (/приглашенные*, /участники, /участникиN, /неголосовали, /голосовали, /все, /N), обновление контекста внутри резолвера (вызовы `user_context.*`).
- Новые команды добавляются в одном месте (расширение без правок большого handler).

**Паттерн:** Chain of Responsibility (цепочка правил) или Strategy (стратегия разрешения команды).

---

### 3. Диспетчеризация команд (Command / таблица обработчиков)

**Модуль:** можно оставить в `handler.py` или вынести в `modules/meeting/command_dispatcher.py`.

**Идея:** словарь `command -> callable(event)` или класс `CommandDispatcher` с методом `dispatch(event, command)`.

- Вместо длинной цепочки `if command == "invited": ... elif command == "invited_not_voted": ...` — один вызов `dispatcher.dispatch(event, command)` или `handlers[command](event)`.
- Обработчики остаются методами `MeetingHandler` (например, `_handle_invited`, `_handle_participants`), но регистрируются в диспетчере. Так handler остаётся точкой входа, но диспетчеризация читается как одна таблица.

**Паттерн:** Command (объект команды/обработчик) + регистрация.

---

### 4. Обработка «Приглашённые» (Delegate / отдельный класс)

**Модуль:** `modules/meeting/invited_handler.py`

**Класс:** `InvitedHandler`

- Зависимости: `MeetingService`, `MeetingConfigManager`, потоки `AddInvitedFlow`, `EditDeleteInvitedFlow`, `SearchInvitedFlow`, `UserContextStore` (или только передача контекста снаружи), возможно общий парсер списка (см. п. 6).
- Методы: `handle_invited(event, skip_parse_and_save, filter_type, page)`, `handle_add(event)`, `handle_delete(event)`, `handle_search(event)`, `get_buttons(...)`, `format_list_paginated(...)`.
- Вся логика списка приглашённых, фильтров, пагинации и кнопок — в одном месте. В `MeetingHandler` остаётся только вызов `invited_handler.handle_invited(...)` и т.д.

**Паттерн:** Delegate / выделенная ответственность (SRP).

---

### 5. Обработка «Участники» (Delegate)

**Модуль:** `modules/meeting/participants_handler.py`

**Класс:** `ParticipantsHandler`

- Зависимости: `MeetingService`, `MeetingConfigManager`, потоки добавления/удаления/поиска постоянных участников, парсер списка (если общий).
- Методы: `handle_participants(event, skip_parse_and_save, page)`, `handle_add(event)`, `handle_delete(event)`, `handle_search(event)`, `get_buttons(...)`, `format_list_paginated(...)`.
- Аналогично InvitedHandler — одна зона ответственности.

**Паттерн:** Delegate / SRP.

---

### 6. Парсинг и валидация списка приглашённых

**Модуль:** `modules/meeting/invited_parser.py` (или расширить `validators.py`)

- Функции: `parse_invited_line(line: str) -> dict | None`, `validate_invited_row(row) -> (bool, str | None)`, `parse_invited_list(text: str) -> list[dict]`.
- Используются в `InvitedHandler`, `ParticipantsHandler` и, при необходимости, в handler при сохранении из команды /участники. Handler и оба под-обработчика получают парсер извне (или импортируют функции).

**Паттерн:** выделение утилит (читаемость, тестируемость).

---

### 7. Собрания и отмена (Meeting flows + Cancel)

- Логику создания/редактирования/переноса собрания и отмены диалогов можно оставить в `MeetingHandler`, но:
  - Отмену (`_handle_cancel`) упростить: один цикл по зарегистрированным flow и вызов «при отмене вернуться к X» (например, к списку участников или приглашённых), без дублирования `event.reply_text(msg); self._handle_participants(...)`.
- При желании можно ввести небольшой класс `CancelBehaviour` (flow -> действие при отмене), чтобы не плодить `elif self.add_permanent_invited_flow.is_active(event): ...`.

**Паттерн:** таблица «flow → действие при отмене» (упрощение, без обязательного нового класса).

---

### 8. Итоговая структура файлов

```
modules/meeting/
  user_context.py        # UserContextStore
  command_resolver.py    # CommandResolver
  command_dispatcher.py  # (опционально) CommandDispatcher
  invited_handler.py     # InvitedHandler
  participants_handler.py # ParticipantsHandler
  invited_parser.py       # parse_invited_line, validate_invited_row, parse_invited_list
  handler.py              # MeetingHandler (оркестратор: message → resolver → dispatcher → invited/participants/meeting)
```

- `handler.py` становится оркестратором: проверка прав, вызов `CommandResolver`, проверка активных flow (ввод в диалоге), вызов диспетчера команд или передача в нужный под-обработчик. Объём handler.py должен заметно уменьшиться (целевой порядок: 800–1200 строк с комментариями и пробелами, основная логика — в делегатах и резолвере).

---

## Порядок выполнения (по шагам)

1. **UserContextStore** — ввести `user_context.py`, перенести туда хранение и методы работы с контекстом, заменить в handler все обращения к `_user_filter_context` / `_user_participants_context` на вызовы `UserContextStore`. Проверить сценарии участники/приглашённые и /все, /2, /3.
2. **CommandResolver** — вынести разрешение команды в `command_resolver.py`, вызывать из `handle_message`; при необходимости передавать в event атрибуты (`_page_number`, `_filter_type`). Убедиться, что все команды (включая /все и пагинацию) работают как раньше.
3. **InvitedParser** — вынести парсинг и валидацию в `invited_parser.py`, заменить вызовы в handler (и позже в InvitedHandler/ParticipantsHandler) на импорт из этого модуля.
4. **InvitedHandler** — создать класс, перенести `_handle_invited`, `_get_invited_buttons`, `_format_invited_list_paginated`, `_handle_invited_add/delete/search`. В handler оставить вызовы вида `self.invited_handler.handle_invited(event, ...)`. Подключить `UserContextStore` и парсер там, где нужно.
5. **ParticipantsHandler** — создать класс, перенести `_handle_participants`, `_get_participants_buttons`, `_format_participants_list_paginated`, `_handle_participants_add/delete/search`. В handler — вызовы `self.participants_handler.handle_participants(event, ...)` и т.д.
6. **CommandDispatcher** (опционально) — заменить цепочку `if command == ...` в `_handle_command` на таблицу обработчиков или класс `CommandDispatcher`. Обработчики могут оставаться методами handler, которые делегируют в invited/participants.
7. **Упрощение _handle_cancel** — задать явную таблицу «flow → (message, callback для возврата)», чтобы при отмене не дублировать код.
8. **Чистка handler** — удалить перенесённый код, оставить только оркестрацию, вызов резолвера, flow-проверки и диспетчеризацию. Проверить линтер и тесты (если есть).

После каждого шага — запуск приложения и проверка основных сценариев (команды, приглашённые, участники, пагинация, отмена).

---

## Риски и ограничения

- Рефакторинг без изменения внешнего API (контракт `MeetingHandler.handle_message`, `handle_callback`, `handle_sse_event` не меняется).
- Не трогать потоки (CreateMeetingFlow, AddInvitedFlow и т.д.) — только использование их из handler и новых делегатов.
- Избегать «большого взрыва»: перенос по одному блоку с тестированием.

---

## Критерии готовности

- Код в handler читается как последовательность шагов: проверка прав → разрешение команды → обработка диалогов (flow) → диспетчеризация команды.
- Контекст участников/приглашённых меняется только в `UserContextStore` и в `CommandResolver`.
- Добавление новой текстовой команды = добавление правила в `CommandResolver` и обработчика в диспетчер (или в соответствующий Handler).
- Дублирование сброса/установки контекста устранено.
- Размер `handler.py` уменьшен; детали приглашённых и участников инкапсулированы в отдельных модулях.
