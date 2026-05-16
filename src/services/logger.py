
import logging

from PySide6.QtCore import QObject, Signal

from src.settings import STATUS_BAR_TIMEOUT


logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s %(message)s',
    handlers=[
        # logging.FileHandler('anaouder_app.log'),
        logging.StreamHandler()
    ],
    force=True
)

class AppLogger(QObject):
    message_requested = Signal(str, int)
    error_message_requested = Signal(str, int)


    def __init__(self):
        super().__init__()
        self.log = logging.getLogger(__name__)


    def _format_message(self, text: str, caller_name: str | None = None) -> str:
        if caller_name:
            text = f"[{caller_name}] {text}"
        return text


    def message(
            self,
            text: str,
            caller_name: str | None = None,
            timeout: int | None = None
            ) -> None:
        text = self._format_message(text, caller_name)
        self.message_requested.emit(text, timeout or STATUS_BAR_TIMEOUT)
        self.log.info(text)


    def error(
            self,
            text: str,
            caller_name: str | None = None,
            timeout: int | None = None
            ) -> None:
        text = self._format_message(text, caller_name)
        self.error_message_requested.emit(text, timeout or STATUS_BAR_TIMEOUT)
        self.log.error(text)
    

    def warning(
            self,
            text: str,
            caller_name: str | None = None,
            show_status: bool = False,
            timeout: int | None = None
            ) -> None:
        text = self._format_message(text, caller_name)
        self.log.warning(text)

        if show_status:
            self.error_message_requested.emit(text, timeout or STATUS_BAR_TIMEOUT)


    def debug(
            self,
            text: str,
            caller_name: str | None = None,
            ) -> None:
        """Debug messages are not displayed in the UI"""
        text = self._format_message(text, caller_name)
        self.log.debug(text)
            


logger = AppLogger()