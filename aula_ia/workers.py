"""Trabajo de Qt en segundo plano y cancelación cooperativa del entrenamiento."""
import threading

from PySide6.QtCore import QThread, Signal


class Worker(QThread):
    message = Signal(str)
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, function):
        super().__init__()
        self.function = function
        self.stop = threading.Event()

    def run(self):
        try:
            self.result.emit(self.function(self.message.emit, self.stop.is_set))
        except Exception as error:
            self.failed.emit(str(error))
