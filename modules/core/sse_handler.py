"""
Обработчик SSE событий.
"""
import json
import logging
import time
from typing import Callable, Optional

import requests

from config import config

logger = logging.getLogger(__name__)


class SSEHandler:
    """Обработчик Server-Sent Events для получения сообщений."""
    
    def __init__(self):
        self._running = False
        self._session: Optional[requests.Session] = None
    
    def connect(self, on_message: Callable[[dict], None]) -> None:
        """Подключается к SSE и обрабатывает события."""
        url = f"{config.sse_base_url}/api/v2/events/bot"
        headers = {
            "Authorization": config.bot_token,
            "Accept": "text/event-stream",
        }
        
        self._running = True
        self._session = requests.Session()
        
        while self._running:
            try:
                logger.info("Подключение к SSE: %s", url)
                
                with self._session.get(url, headers=headers, stream=True, timeout=300) as response:
                    if response.status_code != 200:
                        logger.error("SSE ошибка: HTTP %s", response.status_code)
                        time.sleep(5)
                        continue
                    
                    logger.info("SSE подключен")
                    
                    for line in response.iter_lines(decode_unicode=True):
                        if not self._running:
                            break
                        
                        if not line or not line.startswith("data:"):
                            continue
                        
                        try:
                            data = json.loads(line[5:].strip())
                            logger.debug(
                                "SSE raw: keys=%s type=%s",
                                list(data.keys()) if isinstance(data, dict) else type(data),
                                data.get("type") if isinstance(data, dict) else "—",
                            )
                            on_message(data)
                        except json.JSONDecodeError:
                            continue
            
            except requests.exceptions.Timeout:
                logger.warning("SSE timeout, переподключение...")
            except requests.exceptions.ConnectionError as e:
                logger.error("SSE connection error: %s", e)
                time.sleep(5)
            except Exception as e:
                logger.error("SSE error: %s", e, exc_info=True)
                time.sleep(5)
    
    def disconnect(self) -> None:
        """Отключается от SSE."""
        self._running = False
        if self._session:
            self._session.close()
