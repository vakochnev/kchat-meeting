FROM python:3.11-slim

WORKDIR /app

# Копируем зависимости
COPY requirements.txt .
COPY libs/ libs/

# Устанавливаем Python-зависимости (+ драйвер PostgreSQL для внешней БД)
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir psycopg2-binary \
    && pip install --no-cache-dir libs/messenger_bot_api-2.0.3-py3-none-any.whl

# Копируем код приложения
COPY config/ config/
COPY alembic/ alembic/
COPY alembic.ini .
COPY db/ db/
COPY modules/ modules/
COPY api/ api/
COPY main.py config.py .

# Директория для логов (при LOG_FILE)
RUN mkdir -p /app/logs

# Непривилегированный пользователь
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Миграции при старте, затем основной процесс
CMD alembic upgrade head && exec python main.py
