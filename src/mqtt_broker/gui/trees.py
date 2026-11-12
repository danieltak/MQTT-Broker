from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import QHeaderView, QTreeWidget, QTreeWidgetItem

from ..models import ClientInfo, topic_matches

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
        self._filter = ""
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
            if self._filter:
                self._apply_filter(self._nodes[levels[0]])
        parent.setText(1, str(count))

    def set_filter(self, pattern: str) -> None:
        self._filter = pattern.strip()
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if item is not None:
                self._apply_filter(item)

    def _apply_filter(self, item: QTreeWidgetItem) -> bool:
        """Show the item if it or any descendant matches; returns its visibility."""
        visible = False
        for j in range(item.childCount()):
            child = item.child(j)
            if child is not None and self._apply_filter(child):
                visible = True
        topic = item.data(0, TOPIC_ROLE)
        if topic is not None and topic_matches(self._filter, topic):
            visible = True
        item.setHidden(not visible)
        return visible

    def visible_topics(self) -> list[str]:
        return [t for t in self.topics() if not self._nodes[t].isHidden()]

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

    def _top_items(self) -> list[QTreeWidgetItem]:
        return [item for i in range(self.topLevelItemCount()) if (item := self.topLevelItem(i)) is not None]

    def set_clients(self, clients: list[ClientInfo]) -> None:
        collapsed = {item.text(0) for item in self._top_items() if not item.isExpanded()}
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
        return [item.text(0) for item in self._top_items()]

    def subscriptions(self, client_id: str) -> list[str]:
        for item in self._top_items():
            if item.text(0) == client_id:
                children = (item.child(j) for j in range(item.childCount()))
                return [child.text(0) for child in children if child is not None]
        return []
