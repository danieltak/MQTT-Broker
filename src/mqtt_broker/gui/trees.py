from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import QHeaderView, QTreeWidget, QTreeWidgetItem

from ..models import ClientInfo

TOPIC_ROLE = Qt.ItemDataRole.UserRole


class TopicTree(QTreeWidget):
    """Topics shown as a hierarchy of '/'-separated levels with per-topic message counts."""

    topicSelected = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setHeaderLabels(["Topic", "Msgs"])
        self.setUniformRowHeights(True)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)
        self.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        header = self.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._nodes: dict[str, QTreeWidgetItem] = {}
        self.currentItemChanged.connect(self._on_current_changed)

    def _node(self, path: str, label: str, parent: QTreeWidgetItem | None) -> QTreeWidgetItem:
        item = self._nodes.get(path)
        if item is None:
            item = QTreeWidgetItem([label or "(empty)", ""])
            item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if parent is None:
                self.addTopLevelItem(item)
            else:
                parent.addChild(item)
                parent.setExpanded(True)
            self._nodes[path] = item
        return item

    def update_topic(self, topic: str, count: int) -> None:
        parent: QTreeWidgetItem | None = None
        levels = topic.split("/")
        for depth, level in enumerate(levels):
            parent = self._node("/".join(levels[: depth + 1]), level, parent)
        assert parent is not None
        if parent.data(0, TOPIC_ROLE) is None:
            parent.setData(0, TOPIC_ROLE, topic)
            font = QFont(parent.font(0))
            font.setBold(True)
            parent.setFont(0, font)
            parent.setToolTip(0, topic)
        parent.setText(1, str(count))

    def topic_item(self, topic: str) -> QTreeWidgetItem | None:
        item = self._nodes.get(topic)
        return item if item is not None and item.data(0, TOPIC_ROLE) == topic else None

    def topics(self) -> list[str]:
        return sorted(t for t in self._nodes if self.topic_item(t) is not None)

    def selected_topic(self) -> str | None:
        item = self.currentItem()
        return item.data(0, TOPIC_ROLE) if item is not None else None

    def select_topic(self, topic: str) -> None:
        item = self.topic_item(topic)
        if item is not None:
            self.setCurrentItem(item)

    def clear_topics(self) -> None:
        self._nodes.clear()
        self.clear()

    def _on_current_changed(self, current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None) -> None:
        self.topicSelected.emit(current.data(0, TOPIC_ROLE) if current is not None else None)


class ClientsTree(QTreeWidget):
    """Clients as top-level rows with their subscriptions as children."""

    CONNECTED = QColor("#4ade80")
    DISCONNECTED = QColor("#9aa0aa")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setHeaderLabels(["Client / Subscription", "Address / QoS", "Status", "Since"])
        self.setUniformRowHeights(True)
        self.setAlternatingRowColors(True)
        header = self.header()
        header.setStretchLastSection(True)
        for col in (0, 1, 2):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)

    def set_clients(self, clients: list[ClientInfo]) -> None:
        collapsed = {
            self.topLevelItem(i).text(0)
            for i in range(self.topLevelItemCount())
            if not self.topLevelItem(i).isExpanded()
        }
        self.clear()
        for info in clients:
            status = "Connected" if info.connected else "Disconnected"
            item = QTreeWidgetItem([
                info.client_id,
                info.address,
                status,
                info.connected_at.astimezone().strftime("%H:%M:%S"),
            ])
            item.setForeground(2, QBrush(self.CONNECTED if info.connected else self.DISCONNECTED))
            if not info.connected:
                item.setForeground(0, QBrush(self.DISCONNECTED))
            for topic, qos in sorted(info.subscriptions.items()):
                item.addChild(QTreeWidgetItem([topic, f"QoS {qos}", "", ""]))
            self.addTopLevelItem(item)
            item.setExpanded(info.client_id not in collapsed)

    def client_ids(self) -> list[str]:
        return [self.topLevelItem(i).text(0) for i in range(self.topLevelItemCount())]

    def subscriptions(self, client_id: str) -> list[str]:
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if item.text(0) == client_id:
                return [item.child(j).text(0) for j in range(item.childCount())]
        return []
