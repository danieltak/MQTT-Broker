from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtGui import QFontDatabase

from ..models import PayloadFormat, StoredMessage, format_payload

_PREVIEW_CHARS = 200
_Index = QModelIndex | QPersistentModelIndex


class MessageTableModel(QAbstractTableModel):
    COLUMNS = ("Time", "Size", "QoS", "Retain", "Client", "Payload")
    PAYLOAD_COLUMN = 5

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._messages: list[StoredMessage] = []
        self._format = PayloadFormat.UTF8
        self._mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)

    @property
    def payload_format(self) -> PayloadFormat:
        return self._format

    def set_format(self, fmt: PayloadFormat) -> None:
        if fmt is not self._format:
            self._format = fmt
            if self._messages:
                top = self.index(0, self.PAYLOAD_COLUMN)
                bottom = self.index(len(self._messages) - 1, self.PAYLOAD_COLUMN)
                self.dataChanged.emit(top, bottom)

    def set_messages(self, messages: list[StoredMessage]) -> None:
        self.beginResetModel()
        self._messages = messages
        self.endResetModel()

    def messages(self) -> list[StoredMessage]:
        return self._messages

    def message_at(self, row: int) -> StoredMessage | None:
        return self._messages[row] if 0 <= row < len(self._messages) else None

    def rowCount(self, parent: _Index = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._messages)

    def columnCount(self, parent: _Index = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.COLUMNS[section]
        return None

    def payload_text(self, row: int) -> str:
        msg = self.message_at(row)
        return format_payload(msg.payload, self._format) if msg else ""

    def data(self, index: _Index, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        msg = self.message_at(index.row())
        if msg is None:
            return None
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            match col:
                case 0:
                    return msg.timestamp.astimezone().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                case 1:
                    return f"{len(msg.payload)} B"
                case 2:
                    return str(msg.qos)
                case 3:
                    return "yes" if msg.retain else ""
                case 4:
                    return msg.client_id
                case 5:
                    text = format_payload(msg.payload, self._format)
                    text = text.replace("\r", "").replace("\n", " \u23ce ")
                    return text if len(text) <= _PREVIEW_CHARS else text[:_PREVIEW_CHARS] + "\u2026"
        elif role == Qt.ItemDataRole.FontRole and col == self.PAYLOAD_COLUMN:
            return self._mono
        elif role == Qt.ItemDataRole.TextAlignmentRole and col in (1, 2, 3):
            return int(Qt.AlignmentFlag.AlignCenter)
        return None
