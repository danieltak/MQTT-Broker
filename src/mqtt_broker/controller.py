from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from .broker_service import BrokerService, BrokerStartError
from .models import StoredMessage
from .store import ClientRegistry, MessageStore


class BrokerController(QObject):
    """Qt bridge for BrokerService; signals emitted from the broker thread are queued to the GUI thread."""

    messageReceived = Signal(object)
    clientsChanged = Signal()
    runningChanged = Signal(bool)
    errorOccurred = Signal(str)

    def __init__(self, max_messages: int = 1000, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.store = MessageStore(max_messages)
        self.clients = ClientRegistry()
        self.service = BrokerService(self.store, self.clients, listener=self)

    @property
    def running(self) -> bool:
        return self.service.running

    def start(self, host: str, port: int) -> bool:
        try:
            self.service.start(host, port)
        except BrokerStartError as exc:
            self.errorOccurred.emit(str(exc))
            return False
        self.runningChanged.emit(True)
        return True

    def stop(self) -> None:
        if self.service.running:
            self.service.stop()
            self.runningChanged.emit(False)

    def set_max_messages(self, value: int) -> None:
        self.store.set_max_messages(value)

    # BrokerListener

    def on_message(self, message: StoredMessage) -> None:
        self.messageReceived.emit(message)

    def on_clients_changed(self) -> None:
        self.clientsChanged.emit()
