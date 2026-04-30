from PySide6.QtCore import QObject, Signal




class Logger(QObject):
    message_requested = Signal(str)
    error_message_requested = Signal(str)
    
    def message(self, text: str):
        self.message_requested.emit(text)

    def error_message(self, text: str):
        self.message_requested.emit(text)


logger = Logger()