FROM docker-kchat.kalashnikovconcern.ru/python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Копируем зависимости
COPY requirements.txt .
COPY libs/ ./libs/

# Устанавливаем Python-зависимости (+ драйвер PostgreSQL для внешней БД)

RUN --mount=type=secret,id=pypi-username,env=PYPI_USERNAME \
    --mount=type=secret,id=pypi-password,env=PYPI_PASSWORD \
    export PIP_INDEX_URL="https://$PYPI_USERNAME:$PYPI_PASSWORD@repo-ci.kalashnikovconcern.ru/repository/kchat-pypi-g/simple" && \
    pip install --upgrade pip && \
    pip3 install --no-cache-dir -r requirements.txt && \
    pip3 uninstall opencv-python --yes && \
    pip3 install opencv-python-headless==4.11.0.86

# Копируем код приложения
COPY . .

# Директория для логов (при LOG_FILE)
RUN mkdir -p /app/logs

# Непривилегированный пользователь
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Миграции, seed meeting_admins, затем основной процесс
CMD alembic upgrade head && python tools/seed_meeting_admins.py && exec python main.py

