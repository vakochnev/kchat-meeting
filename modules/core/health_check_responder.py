"""
Health check responder — эхо на сообщения проверки жизни бота.

Слушает SSE напрямую (как в kchat-bot), обходя общий поток.
При получении "Health check [XXX]" отправляет "✅ Health check [XXX] OK"
и удаляет оба сообщения (health check и эхо) через deleteMessages API.
"""
import json
import logging
import re
import threading
import time
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

# Паттерн для health check: "Health check [ABC123]" или "🔍 Health check [ABC123]"
HEALTH_CHECK_PATTERN = re.compile(r"Health check \[([A-Z0-9]+)\]")


class HealthCheckResponder:
    """
    Отвечает эхо на health check сообщения.
    Слушает SSE в отдельном потоке (как в kchat-bot).
    """

    MAX_MESSAGE_AGE_SEC = 60
    MAX_CACHE_SIZE = 100

    def __init__(
        self,
        token: str,
        api_base_url: str,
        sse_base_url: str,
    ) -> None:
        self._token = token
        self._api_url = api_base_url.rstrip("/")
        self._sse_url = sse_base_url.rstrip("/")
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._session = requests.Session()
        self._cache: Dict[str, float] = {}
        self._cache_lock = threading.Lock()

    def start(self) -> None:
        """Запускает responder в отдельном потоке с собственным SSE соединением."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="HealthCheck-Responder",
            daemon=True,
        )
        self._thread.start()
        logger.info("[HEALTH_CHECK] Responder запущен")

    def stop(self) -> None:
        """Останавливает responder."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        self._session.close()
        logger.info("[HEALTH_CHECK] Responder остановлен")

    def _run(self) -> None:
        """Подключение к SSE с переподключением."""
        while not self._stop.is_set():
            try:
                self._listen_sse()
            except Exception as e:
                if not self._stop.is_set():
                    logger.warning("[HEALTH_CHECK] SSE ошибка: %s", e)
                    time.sleep(5)

    def _listen_sse(self) -> None:
        """Слушает SSE поток."""
        url = f"{self._sse_url}/api/v2/events/bot"
        headers = {"Authorization": self._token, "Accept": "text/event-stream"}
        with self._session.get(
            url, headers=headers, stream=True, timeout=120
        ) as resp:
            if resp.status_code != 200:
                logger.warning("[HEALTH_CHECK] SSE HTTP %s", resp.status_code)
                return
            for line in resp.iter_lines(decode_unicode=True):
                if self._stop.is_set():
                    break
                if line and line.startswith("data:"):
                    self._handle_sse_line(line)

    def _handle_sse_line(self, line: str) -> None:
        """Обрабатывает строку SSE."""
        try:
            data = json.loads(line[5:].strip())
            if content := data.get("content"):
                data = json.loads(content) if isinstance(content, str) else content
            payload = data.get("payload", {})
            if isinstance(payload, str):
                payload = json.loads(payload) if payload else {}
            messages = payload.get("messages", [])
            if not messages:
                return
            msg = messages[0] if isinstance(messages[0], dict) else {}
            self._process_message(
                sender_id=msg.get("senderId", 0),
                workspace_id=data.get("workspaceId") or data.get("workspace_id", -1),
                group_id=data.get("groupId") or msg.get("groupId"),
                text=msg.get("message", ""),
                date_ms=msg.get("date", 0),
                message_id=msg.get("id") or msg.get("messageId"),
            )
        except (json.JSONDecodeError, TypeError, KeyError):
            pass

    def _process_message(
        self,
        sender_id: int,
        workspace_id: Any,
        group_id: Any,
        text: str,
        date_ms: int,
        message_id: Optional[Any] = None,
    ) -> None:
        """Обрабатывает сообщение: если health check — отправляет эхо и удаляет оба сообщения."""
        if sender_id >= 0 or "OK" in text:
            return
        if not group_id:
            return
        try:
            workspace_id = int(workspace_id) if workspace_id is not None else -1
            group_id = int(group_id)
        except (TypeError, ValueError):
            return

        match = HEALTH_CHECK_PATTERN.search(text)
        if not match:
            return

        check_id = match.group(1)

        age_sec = (time.time() * 1000 - date_ms) / 1000
        if age_sec > self.MAX_MESSAGE_AGE_SEC:
            return

        with self._cache_lock:
            if check_id in self._cache:
                return
            self._cache[check_id] = time.time()
            self._cleanup_cache()

        logger.info("[HEALTH_CHECK] Получен [%s], отправляем эхо", check_id)
        echo_message_id = self._send_echo(workspace_id, group_id, check_id)
        if message_id is not None or echo_message_id is not None:
            self._delete_messages(workspace_id, group_id, message_id, echo_message_id)

    def _cleanup_cache(self) -> None:
        """Очищает старые записи из кэша."""
        if len(self._cache) <= self.MAX_CACHE_SIZE:
            return
        sorted_items = sorted(self._cache.items(), key=lambda x: x[1])
        for check_id, _ in sorted_items[: len(self._cache) // 2]:
            del self._cache[check_id]

    def _send_echo(self, workspace_id: int, group_id: int, check_id: str) -> Optional[int]:
        """Отправляет эхо-ответ в чат. Возвращает message_id эхо или None."""
        url = f"{self._api_url}/botapi/v1/messages/sendTextMessage/{workspace_id}/{group_id}"
        payload = {
            "message": f"✅ Health check [{check_id}] OK",
            "clientRandomId": int(time.time()),
        }
        headers = {"Authorization": self._token, "Content-Type": "application/json"}

        try:
            resp = self._session.post(url, json=payload, headers=headers, timeout=10)
            if resp.status_code == 200:
                logger.info("[HEALTH_CHECK] Эхо отправлено [%s]", check_id)
                try:
                    data = resp.json()
                    return data.get("messageId") or data.get("message_id")
                except (json.JSONDecodeError, TypeError):
                    pass
            logger.warning("[HEALTH_CHECK] Ошибка эхо: HTTP %s", resp.status_code)
        except Exception as e:
            logger.warning("[HEALTH_CHECK] Ошибка эхо: %s", e)
        return None

    def _delete_messages(
        self,
        workspace_id: int,
        group_id: int,
        incoming_id: Optional[Any],
        echo_id: Optional[Any],
    ) -> None:
        """Удаляет health check и эхо сообщения через Bot API."""
        ids: list[int] = []
        for x in (incoming_id, echo_id):
            if x is not None:
                try:
                    ids.append(int(x))
                except (TypeError, ValueError):
                    pass
        if not ids:
            return
        url = f"{self._api_url}/botapi/v1/messages/deleteMessages/{workspace_id}/{group_id}"
        headers = {"Authorization": self._token, "Content-Type": "application/json"}
        payload = {"messageIds": ids}

        try:
            resp = self._session.post(url, json=payload, headers=headers, timeout=10)
            if resp.status_code == 200:
                logger.debug("[HEALTH_CHECK] Удалены сообщения: %s", ids)
            else:
                logger.warning("[HEALTH_CHECK] Ошибка удаления: HTTP %s", resp.status_code)
        except Exception as e:
            logger.warning("[HEALTH_CHECK] Ошибка удаления: %s", e)
