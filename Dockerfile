FROM docker-kchat.kalashnikovconcern.ru/python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Копируем зависимости
COPY requirements.txt .

# Копируем к-чат библиотеку
COPY libs/messenger_bot_api-2.0.5-py3-none-any.whl libs/

# Устанавливаем Python-зависимости (+ драйвер PostgreSQL для внешней БД)
RUN --mount=type=secret,id=pypi-username,env=PYPI_USERNAME \
    --mount=type=secret,id=pypi-password,env=PYPI_PASSWORD \
    export PIP_INDEX_URL="https://$PYPI_USERNAME:$PYPI_PASSWORD@repo-ci.kalashnikovconcern.ru/repository/kchat-pypi-g/simple" && \
    pip install --upgrade pip && \
    pip3 install --no-cache-dir -r requirements.txt && \
    pip3 uninstall opencv-python --yes && \
    pip3 install "opencv-python-headless==4.11.0.86"

# Копируем код приложения
COPY . .

# Директория для логов (при LOG_FILE)
RUN mkdir -p /app/logsroot@KK-SRV-KBOT1-T:/opt/kchat-meeting
