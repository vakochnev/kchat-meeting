"""
Основной класс приложения бота совещаний.
"""
import logging
import threading
from typing import Callable, Optional, Dict, Any

from messenger_bot_api import (
    Application,
    MessageBotEvent,
    MessageHandler,
    ClickButtonEventHandler,
)

from config import config
from .sse_handler import SSEHandler

logger = logging.getLogger(__name__)


class BotApp:
    """Основной класс приложения бота совещаний."""
    
    def __init__(self):
        self._app: Optional[Application] = None
        self._message_handler: Optional[Callable] = None
        self._callback_handler: Optional[Callable] = None
        self._sse_handler: Optional[Callable[[Dict[str, Any]], None]] = None
        self._sse_thread: Optional[threading.Thread] = None
        self._sse_client: Optional[SSEHandler] = None
        self._running: bool = False
    
    def setup(
        self,
        message_handler: Callable[[MessageBotEvent], None],
        callback_handler: Callable[[MessageBotEvent], None],
        sse_handler: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        """Настраивает обработчики событий."""
        self._message_handler = message_handler
        self._callback_handler = callback_handler
        self._sse_handler = sse_handler
        
        # Передаём URL через request_kwargs
        request_kwargs = {
            "api_base_url": config.api_base_url,
            "sse_base_url": config.sse_base_url,
        }
        self._app = Application(
            token=config.bot_token,
            request_kwargs=request_kwargs
        )
        
        # Сначала callback (клики по кнопкам): иначе клик приходит как MESSAGE
        # и перехватывается MessageHandler, из-за чего ответ не сохраняется.
        self._app.add_handler(
            ClickButtonEventHandler(self._wrap_handler(callback_handler))
        )
        self._app.add_handler(
            MessageHandler(self._wrap_handler(message_handler))
        )
        
        logger.info("Бот совещаний настроен")
        
        # Запускаем SSE обработчик в отдельном потоке
        if sse_handler:
            self._start_sse_handler()
    
    def _start_sse_handler(self) -> None:
        """Запускает SSE обработчик в отдельном потоке."""
        if not self._sse_handler:
            return
        
        def sse_callback(event_data: Dict[str, Any]) -> None:
            """Callback для SSE событий."""
            try:
                self._sse_handler(event_data)
            except Exception as e:
                logger.error(
                    "Ошибка в SSE обработчике: %s",
                    e,
                    exc_info=True
                )
        
        self._sse_client = SSEHandler()
        self._sse_thread = threading.Thread(
            target=self._sse_client.connect,
            args=(sse_callback,),
            daemon=True,
            name="SSEHandler"
        )
        self._sse_thread.start()
        logger.info("SSE обработчик запущен")
    
    def _wrap_handler(self, handler: Callable) -> Callable:
        """Оборачивает обработчик в try-except."""
        def wrapper(event: MessageBotEvent) -> None:
            try:
                return handler(event)
            except Exception as e:
                logger.error(
                    "Ошибка в обработчике: %s",
                    e,
                    exc_info=True
                )
                try:
                    event.reply_text(
                        "❌ Произошла ошибка. Попробуйте позже."
                    )
                except Exception:
                    pass
        return wrapper
    
    def run(self) -> None:
        """Запускает бота."""
        if not self._app:
            raise RuntimeError("Бот не настроен. Вызовите setup() перед run()")
        
        logger.info("Запуск бота совещаний...")
        try:
            self._app.start()
        except RuntimeError as e:
            if "Fetching bot group states failed" in str(e):
                logger.warning(
                    "Не удалось получить состояния групп бота. "
                    "Возможно, бот не добавлен ни в одну группу или "
                    "проблемы с доступом к API. Продолжаем работу..."
                )
            else:
                raise
        
        # start() запускает потоки и сразу возвращается,
        # поэтому нужно держать основной поток живым
        import time
        import signal
        
        # Флаг для корректной остановки
        self._running = True
        
        def signal_handler(signum, frame):
            """Обработчик сигнала для корректной остановки."""
            logger.info("Получен сигнал остановки")
            self._running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        try:
            while self._running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            logger.info("Остановка по Ctrl+C")
        finally:
            self.stop()
    
    def stop(self) -> None:
        """Останавливает бота."""
        self._running = False
        
        if self._sse_client:
            logger.info("Остановка SSE обработчика...")
            self._sse_client.disconnect()
        
        if self._app:
            logger.info("Остановка бота совещаний...")
            if hasattr(self._app, 'stop'):
                self._app.stop()
