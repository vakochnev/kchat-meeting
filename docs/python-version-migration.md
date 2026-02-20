# Переход между версиями Python

Документация по смене версии Python в проекте kchat-meeting.

## Текущая целевая версия: Python 3.11

---

## Переход на Python 3.11 (с 3.12 или другой версии)

### 1. Файлы проекта, связанные с версией Python

| Файл | Назначение |
|------|------------|
| `.python-version` | Версия для uv, pyenv, редакторов |
| `pyproject.toml` | `requires-python` — минимальная версия |
| `Dockerfile` | Базовый образ (например, `python:3.11-slim`) |
| `README.md` | Требования для пользователей |
| `uv.lock` | Lock-файл зависимостей (пересоздаётся через `uv lock`) |

### 2. Установка Python 3.11

**Debian/Ubuntu:**
```bash
sudo apt update
sudo apt install python3.11 python3.11-venv python3.11-dev
```

**Fedora/RHEL:**
```bash
sudo dnf install python3.11
```

**macOS (Homebrew):**
```bash
brew install python@3.11
```

**Проверка:**
```bash
python3.11 --version  # Должно вывести Python 3.11.x
```

### 3. Обновление файлов проекта

#### `.python-version`
```
3.11
```

#### `pyproject.toml`
```toml
requires-python = ">=3.11"
```

#### `Dockerfile`
```dockerfile
FROM python:3.11-slim
# или
FROM <registry>/python:3.11-slim
```

### 4. Пересоздание окружения

```bash
cd kchat-meeting
rm -rf .venv
uv venv --python 3.11
uv sync
```

Если uv не находит 3.11 автоматически:
```bash
uv venv --python /usr/bin/python3.11
uv sync
```

### 5. Обновление lock-файла

```bash
uv lock
```

### 6. Проверка

```bash
uv run python --version   # 3.11.x
uv run python main.py     # Запуск бота
uv run pytest             # Тесты (если есть)
```

### 7. Docker

```bash
docker compose build --no-cache
```

---

## Переход на другую версию (общая схема)

1. Установить целевую версию Python.
2. Обновить `.python-version`.
3. Обновить `requires-python` в `pyproject.toml`.
4. Обновить образ в `Dockerfile`.
5. Обновить README (раздел требований).
6. Удалить `.venv` и выполнить `uv venv --python <версия>` и `uv sync`.
7. Выполнить `uv lock`.
8. Проверить работу приложения и тестов.
9. Проверить сборку Docker.

---

## Ограничения по версиям

- **messenger_bot_api** — проверять совместимость wheel с выбранной версией Python.
- **Python 3.12+** — новый синтаксис (например, `type`), при downgrade может потребоваться рефакторинг.
- **psycopg2-binary** — для PostgreSQL; есть сборки под разные версии Python.

---

## Чек-лист миграции

- [ ] Установлена целевая версия Python
- [ ] Обновлён `.python-version`
- [ ] Обновлён `pyproject.toml` (`requires-python`)
- [ ] Обновлён `Dockerfile`
- [ ] Обновлён README (при необходимости)
- [ ] Пересоздан `.venv`: `uv venv --python X.Y && uv sync`
- [ ] Выполнен `uv lock`
- [ ] Проверка: `uv run python main.py`
- [ ] Сборка Docker проходит успешно
- [ ] CI/CD (если есть) использует нужную версию Python
