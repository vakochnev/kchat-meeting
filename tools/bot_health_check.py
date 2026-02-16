#!/usr/bin/env python3
"""
Проверка жизни бота совещаний KChat.

Отправляет сообщение в чат и ожидает эхо от бота через SSE.
Если эхо есть — бот жив.

Вся конфигурация в .env:
  BOT_TOKEN, API_BASE_URL, SSE_BASE_URL
  HEALTH_CHECK_GROUP_ID (обязательно)
  HEALTH_CHECK_WORKSPACE_ID (опционально, по умолчанию -1)
  HEALTH_CHECK_TIMEOUT (опционально, по умолчанию 10)

Коды возврата:
  0 - бот работает ✅
  1 - бот не отвечает ❌
  2 - ошибка конфигурации

Примеры:
  uv run python tools/bot_health_check.py
  uv run python tools/bot_health_check.py -v
"""
from __future__ import annotations

import argparse
import json
import os
import random
import string
import sys
import threading
import time
from pathlib import Path

import requests

# Загрузка .env: корень проекта (tools/../) и текущая директория
try:
    from dotenv import load_dotenv
    project_root = Path(__file__).resolve().parent.parent
    load_dotenv(project_root / ".env", override=False)
    load_dotenv(Path.cwd() / ".env", override=False)
    load_dotenv(override=False)  # стандартный поиск dotenv
except ImportError:
    pass


# =============================================================================
# SSE Listener
# =============================================================================

class SSEListener:
    """Слушает SSE и ищет эхо-ответ на health check."""

    def __init__(
        self,
        sse_url: str,
        token: str,
        group_id: int,
        expected_id: str,
        timeout: float = 10.0,
        verbose: bool = False,
    ):
        self._url = f"{sse_url}/api/v2/events/bot"
        self._headers = {"Authorization": token, "Accept": "text/event-stream"}
        self._group_id = group_id
        self._expected_id = expected_id
        self._timeout = timeout
        self._verbose = verbose

        self.found = threading.Event()
        self._sent_time_ms = 0
        self._stop = threading.Event()
        self._connected = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Запускает listener."""
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._connected.wait(timeout=5)

    def stop(self) -> None:
        """Останавливает listener."""
        self._stop.set()

    def mark_sent(self) -> None:
        """Отмечает время отправки сообщения."""
        self._sent_time_ms = int(time.time() * 1000)

    def _run(self) -> None:
        """Основной цикл."""
        try:
            with requests.get(
                self._url,
                headers=self._headers,
                stream=True,
                timeout=self._timeout + 10,
            ) as resp:
                if resp.status_code != 200:
                    self._log(f"HTTP {resp.status_code}")
                    return

                self._connected.set()
                self._log("Connected")

                for line in resp.iter_lines(decode_unicode=True):
                    if self._stop.is_set() or self.found.is_set():
                        break
                    if line and line.startswith("data:"):
                        self._handle(line)
        except Exception as e:
            self._log(f"Error: {e}")
        finally:
            self._connected.set()

    def _handle(self, line: str) -> None:
        """Обрабатывает SSE строку."""
        try:
            data = json.loads(line[5:].strip())
            if content := data.get("content"):
                data = json.loads(content)

            payload = data.get("payload", {})
            if isinstance(payload, str):
                payload = json.loads(payload)

            messages = payload.get("messages", [])
            if not messages:
                return

            msg = messages[0]
            sender_id = msg.get("senderId", 0)
            group_id = data.get("groupId") or msg.get("groupId")
            msg_date = msg.get("date", 0)
            text = msg.get("message", "")

            # Эхо от бота: в нашей группе после отправки, содержит ID + OK
            is_echo = (
                sender_id < 0
                and group_id == self._group_id
                and msg_date >= self._sent_time_ms
                and self._expected_id in text
                and "OK" in text
            )

            if self._verbose:
                self._log(
                    f"sender={sender_id} group={group_id} "
                    f"match={is_echo} text='{text[:40]}'"
                )

            if is_echo:
                self._log("✓ Echo received!")
                self.found.set()

        except (json.JSONDecodeError, TypeError, KeyError):
            pass

    def _log(self, msg: str) -> None:
        """Логирует сообщение."""
        if self._verbose:
            print(f"  [SSE] {msg}", file=sys.stderr)


# =============================================================================
# Проверки
# =============================================================================

def send_message(
    api_url: str,
    token: str,
    workspace_id: int,
    group_id: int,
    text: str,
    verbose: bool,
) -> tuple[bool, str, int | None]:
    """Отправляет сообщение через Bot API. Возвращает (ok, err, message_id)."""
    url = f"{api_url}/botapi/v1/messages/sendTextMessage/{workspace_id}/{group_id}"
    payload = {"message": text, "clientRandomId": int(time.time())}
    headers = {"Authorization": token, "Content-Type": "application/json"}

    if verbose:
        print(f"[DEBUG] POST {url}", file=sys.stderr)

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            msg_id = data.get("messageId") or data.get("message_id")
            if verbose and msg_id is None:
                print(f"[DEBUG] sendTextMessage response (no messageId): {data!r}", file=sys.stderr)
            return True, "", msg_id
        return False, f"HTTP {resp.status_code}: {resp.text[:100]}", None
    except Exception as e:
        return False, str(e), None


def delete_messages(
    api_url: str,
    token: str,
    workspace_id: int,
    group_id: int,
    message_ids: list[int],
    verbose: bool,
) -> bool:
    """Удаляет сообщения через Bot API."""
    if not message_ids:
        return False
    url = f"{api_url}/botapi/v1/messages/deleteMessages/{workspace_id}/{group_id}"
    headers = {"Authorization": token, "Content-Type": "application/json"}
    payload = {"messageIds": message_ids}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        if verbose and resp.status_code != 200:
            print(f"[DEBUG] deleteMessages HTTP {resp.status_code}", file=sys.stderr)
        return resp.status_code == 200
    except Exception:
        return False


def generate_check_id() -> str:
    """Генерирует уникальный ID."""
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


def get_int_env(name: str, default: int = 0) -> int:
    """Получает int из env. Поддерживает пробелы и пустые значения."""
    val = os.getenv(name, "").strip()
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def get_float_env(name: str, default: float = 10.0) -> float:
    """Получает float из env."""
    try:
        return float(os.getenv(name, ""))
    except ValueError:
        return default


# =============================================================================
# Main
# =============================================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Проверка жизни бота совещаний KChat (конфигурация из .env)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    # Вся конфигурация из .env
    token = os.getenv("BOT_TOKEN", "").strip()
    api_url = os.getenv("API_BASE_URL", "https://api.kchat.app")
    sse_url = os.getenv("SSE_BASE_URL", "https://pusher.kchat.app")
    group_id = get_int_env("HEALTH_CHECK_GROUP_ID")
    workspace_id = get_int_env("HEALTH_CHECK_WORKSPACE_ID", -1)
    timeout = get_float_env("HEALTH_CHECK_TIMEOUT", 10.0)

    def log(msg: str, to_stderr: bool = True) -> None:
        if not args.quiet:
            print(msg, file=sys.stderr if to_stderr else sys.stdout)

    if not token:
        log("ERROR: BOT_TOKEN not set")
        print("DOWN", flush=True)
        return 2

    if not group_id:
        log("ERROR: need HEALTH_CHECK_GROUP_ID in .env")
        if args.verbose:
            log(f"  (group_id={group_id!r})")
        print("DOWN", flush=True)
        return 2

    # Step 1: Send message
    check_id = generate_check_id()
    log(f"Step 1: Sending [{check_id}]...")

    listener = SSEListener(
        sse_url=sse_url,
        token=token,
        group_id=group_id,
        expected_id=check_id,
        timeout=timeout,
        verbose=args.verbose,
    )
    listener.start()
    listener.mark_sent()

    ok, err, message_id = send_message(
        api_url,
        token,
        workspace_id,
        group_id,
        f"🔍 Health check [{check_id}]",
        args.verbose,
    )
    if not ok:
        listener.stop()
        log(f"  ✗ {err}")
        print("DOWN", flush=True)
        return 2
    log("  ✓ Sent")

    # Step 2: Ожидание эхо от бота
    log("Step 2: Waiting for echo...")
    if listener.found.wait(timeout=timeout):
        listener.stop()
        log("  ✓ Echo received")
        print("UP", flush=True)
        return 0

    listener.stop()
    # При таймауте удаляем отправленное сообщение (бот не ответил)
    if message_id is not None:
        try:
            mid = int(message_id)
            if delete_messages(api_url, token, workspace_id, group_id, [mid], args.verbose):
                log("  (сообщение удалено)")
        except (TypeError, ValueError):
            pass
    log("  ✗ No echo")
    print("DOWN", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
