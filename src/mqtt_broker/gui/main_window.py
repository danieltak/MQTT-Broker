from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QItemSelection, Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTableView,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..config import AppConfig, load_config, save_config
from ..controller import BrokerController
from ..exporter import export_csv
from ..models import PayloadFormat, StoredMessage, format_payload
from ..network import BindOption, list_bind_options
from ..store import MAX_HISTORY, MIN_HISTORY
from .message_model import MessageTableModel
from .trees import ClientsTree, TopicTree

REFRESH_INTERVAL_MS = 100


def _panel() -> tuple[QWidget, QVBoxLayout, QHBoxLayout]:
    panel = QWidget(objectName="Panel")
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(10, 8, 10, 10)
    layout.setSpacing(8)
    header = QHBoxLayout()
    header.setSpacing(6)
    layout.addLayout(header)
    return panel, layout, header


def _shrinkable(label: QLabel) -> QLabel:
    # Long text must not raise the window's minimum width
    label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    label.setMinimumWidth(0)
    return label


def _repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class MainWindow(QMainWindow):
    def __init__(
        self,
        controller: BrokerController | None = None,
        config_path: Path | None = None,
        bind_options: Callable[[], list[BindOption]] = list_bind_options,
    ) -> None:
        super().__init__()
        self._config_path = config_path
        self.config = load_config(config_path)
        self.controller = controller or BrokerController(self.config.max_messages)
        self.controller.set_max_messages(self.config.max_messages)
        self._bind_options = bind_options
        self._dirty_topics: set[str] = set()
        self._clients_dirty = False

        self.setWindowTitle("MQTT Broker")
        self.resize(1280, 760)
        self._build_ui()
        self._populate_interfaces(self.config.host)
        self._connect_signals()

        self._timer = QTimer(self, interval=REFRESH_INTERVAL_MS)
        self._timer.timeout.connect(self._flush)
        self._timer.start()
        self._set_running_ui(False)
        self._update_stats()

    # UI construction

    def _build_ui(self) -> None:
        self.setDockOptions(
            QMainWindow.DockOption.AnimatedDocks
            | QMainWindow.DockOption.AllowNestedDocks
            | QMainWindow.DockOption.AllowTabbedDocks
        )
        self.toolbar = self._build_toolbar()
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)

        self.topics_dock = self._dock("Topics", self._build_topics_panel())
        self.messages_dock = self._dock("Messages", self._build_messages_panel())
        self.payload_dock = self._dock("Payload", self._build_payload_panel())
        self.clients_dock = self._dock("Clients", self._build_clients_panel())
        self._docks = [self.topics_dock, self.messages_dock, self.payload_dock, self.clients_dock]
        self.reset_layout()
        self._build_menu()

        self.stats_label = _shrinkable(QLabel(objectName="Muted"))
        self.error_label = _shrinkable(QLabel(objectName="ErrorLabel"))
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.statusBar().addWidget(self.stats_label, 1)
        self.statusBar().addWidget(self.error_label, 1)

    def _dock(self, title: str, widget: QWidget) -> QDockWidget:
        dock = QDockWidget(title, self, objectName=f"{title}Dock")
        dock.setWidget(widget)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        return dock

    def reset_layout(self) -> None:
        for dock in self._docks:
            dock.setFloating(False)
            self.removeDockWidget(dock)
        area = Qt.DockWidgetArea.LeftDockWidgetArea
        self.addDockWidget(area, self.topics_dock)
        self.splitDockWidget(self.topics_dock, self.messages_dock, Qt.Orientation.Horizontal)
        self.splitDockWidget(self.messages_dock, self.clients_dock, Qt.Orientation.Horizontal)
        self.splitDockWidget(self.messages_dock, self.payload_dock, Qt.Orientation.Vertical)
        for dock in self._docks:
            dock.show()
        self.resizeDocks(
            [self.topics_dock, self.messages_dock, self.clients_dock], [260, 700, 340], Qt.Orientation.Horizontal
        )
        self.resizeDocks([self.messages_dock, self.payload_dock], [500, 180], Qt.Orientation.Vertical)

    def _build_menu(self) -> None:
        view = self.menuBar().addMenu("&View")
        for dock in self._docks:
            view.addAction(dock.toggleViewAction())
        view.addAction(self.toolbar.toggleViewAction())
        view.addSeparator()
        reset = QAction("&Reset layout", self)
        reset.triggered.connect(self.reset_layout)
        view.addAction(reset)
        self.fullscreen_action = QAction("&Full screen", self, checkable=True)
        self.fullscreen_action.setShortcut(QKeySequence(Qt.Key.Key_F11))
        self.fullscreen_action.toggled.connect(self._set_fullscreen)
        view.addAction(self.fullscreen_action)

    def _set_fullscreen(self, enabled: bool) -> None:
        if enabled:
            self.showFullScreen()
        else:
            self.showMaximized()

    def _build_toolbar(self) -> QToolBar:
        bar = QToolBar("Broker", self, objectName="BrokerToolbar")
        bar.setMovable(True)
        bar.setFloatable(False)

        bar.addWidget(QLabel(" Interface ", objectName="FieldLabel"))
        self.interface_combo = QComboBox(objectName="InterfaceCombo")
        self.interface_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.interface_combo.setMinimumContentsLength(22)
        self.interface_combo.setToolTip("Network adapter / address the broker listens on")
        bar.addWidget(self.interface_combo)
        self.refresh_button = QToolButton(text="\u27f3", toolTip="Refresh network adapters")
        bar.addWidget(self.refresh_button)

        bar.addWidget(QLabel("  Port ", objectName="FieldLabel"))
        self.port_spin = QSpinBox(objectName="PortSpin")
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(self.config.port)
        bar.addWidget(self.port_spin)

        bar.addWidget(QLabel("  History ", objectName="FieldLabel"))
        self.limit_spin = QSpinBox(objectName="LimitSpin")
        self.limit_spin.setRange(MIN_HISTORY, MAX_HISTORY)
        self.limit_spin.setValue(self.config.max_messages)
        self.limit_spin.setSuffix(" msgs/topic")
        self.limit_spin.setKeyboardTracking(False)
        self.limit_spin.setToolTip("Maximum number of messages retained per topic")
        bar.addWidget(self.limit_spin)

        bar.addWidget(QLabel("  "))
        self.start_button = QPushButton("Start", objectName="StartButton")
        self.start_button.setCursor(Qt.CursorShape.PointingHandCursor)
        bar.addWidget(self.start_button)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(spacer)
        self.status_label = QLabel("Stopped", objectName="StatusPill")
        bar.addWidget(self.status_label)
        return bar

    def _build_topics_panel(self) -> QWidget:
        panel, layout, header = _panel()
        self.export_all_button = QPushButton("Export CSV", toolTip="Export history of all topics")
        self.clear_button = QPushButton("Clear", toolTip="Clear all stored messages")
        header.addWidget(self.export_all_button)
        header.addWidget(self.clear_button)
        header.addStretch()
        self.topic_tree = TopicTree()
        layout.addWidget(self.topic_tree)
        return panel

    def _build_messages_panel(self) -> QWidget:
        panel, layout, header = _panel()
        self.topic_label = _shrinkable(QLabel("Select a topic", objectName="TopicLabel"))
        header.addWidget(self.topic_label, 1)

        self.auto_scroll_check = QCheckBox("Auto-scroll", checked=True)
        header.addWidget(self.auto_scroll_check)
        header.addSpacing(6)

        self.utf8_button = QPushButton("UTF-8", objectName="Segment", checkable=True, checked=True)
        self.hex_button = QPushButton("HEX", objectName="Segment", checkable=True)
        self.format_group = QButtonGroup(self)
        self.format_group.setExclusive(True)
        self.format_group.addButton(self.utf8_button)
        self.format_group.addButton(self.hex_button)
        segment = QHBoxLayout()
        segment.setSpacing(0)
        segment.addWidget(self.utf8_button)
        segment.addWidget(self.hex_button)
        header.addLayout(segment)
        header.addSpacing(6)

        self.export_topic_button = QPushButton("Export topic", toolTip="Export selected topic history")
        header.addWidget(self.export_topic_button)

        self.message_model = MessageTableModel(self)
        self.message_table = QTableView()
        self.message_table.setModel(self.message_model)
        self.message_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.message_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.message_table.setAlternatingRowColors(True)
        self.message_table.setShowGrid(False)
        self.message_table.setWordWrap(False)
        self.message_table.verticalHeader().setVisible(False)
        self.message_table.verticalHeader().setDefaultSectionSize(26)
        h = self.message_table.horizontalHeader()
        for col in range(MessageTableModel.PAYLOAD_COLUMN):
            h.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(MessageTableModel.PAYLOAD_COLUMN, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.message_table)
        return panel

    def _build_payload_panel(self) -> QWidget:
        panel, layout, header = _panel()
        self.payload_info = _shrinkable(QLabel("", objectName="Muted"))
        header.addWidget(self.payload_info, 1)
        self.payload_view = QPlainTextEdit(objectName="PayloadView", readOnly=True)
        self.payload_view.setPlaceholderText("Select a message to see its full payload")
        layout.addWidget(self.payload_view)
        return panel

    def _build_clients_panel(self) -> QWidget:
        panel, layout, header = _panel()
        layout.removeItem(header)
        self.clients_tree = ClientsTree()
        layout.addWidget(self.clients_tree)
        return panel

    def _connect_signals(self) -> None:
        c = self.controller
        c.messageReceived.connect(self._on_message)
        c.clientsChanged.connect(self._on_clients_changed)
        c.runningChanged.connect(self._set_running_ui)
        c.errorOccurred.connect(self._show_error)

        self.start_button.clicked.connect(self._on_start_clicked)
        self.refresh_button.clicked.connect(lambda: self._populate_interfaces(self.selected_host()))
        self.limit_spin.valueChanged.connect(self._on_limit_changed)
        self.topic_tree.topicSelected.connect(self._on_topic_selected)
        self.format_group.buttonToggled.connect(self._on_format_toggled)
        self.message_table.selectionModel().selectionChanged.connect(self._on_message_selection)
        self.export_all_button.clicked.connect(lambda: self._prompt_export(all_topics=True))
        self.export_topic_button.clicked.connect(lambda: self._prompt_export(all_topics=False))
        self.clear_button.clicked.connect(self._on_clear_clicked)

    # Interface selection

    def _populate_interfaces(self, preferred: str | None) -> None:
        self.interface_combo.clear()
        options = self._bind_options()
        for opt in options:
            self.interface_combo.addItem(opt.label, opt.address)
        if preferred and self.interface_combo.findData(preferred) < 0:
            self.interface_combo.addItem(f"{preferred} (unavailable)", preferred)
        index = self.interface_combo.findData(preferred) if preferred else 0
        self.interface_combo.setCurrentIndex(max(index, 0))

    def selected_host(self) -> str:
        return self.interface_combo.currentData() or ""

    def select_host(self, address: str) -> bool:
        index = self.interface_combo.findData(address)
        if index >= 0:
            self.interface_combo.setCurrentIndex(index)
        return index >= 0

    # Broker control

    def _on_start_clicked(self) -> None:
        if self.controller.running:
            self.controller.stop()
            return
        self._clear_error()
        host, port = self.selected_host(), self.port_spin.value()
        if self.controller.start(host, port):
            self._save_config()

    def _set_running_ui(self, running: bool) -> None:
        self.start_button.setText("Stop" if running else "Start")
        self.start_button.setProperty("running", running)
        _repolish(self.start_button)
        for widget in (self.interface_combo, self.refresh_button, self.port_spin):
            widget.setEnabled(not running)
        svc = self.controller.service
        if running:
            self._set_status(f"Running on {svc.host}:{svc.port}", "running")
        elif self.status_label.property("state") != "error":
            self._set_status("Stopped", "stopped")

    def _set_status(self, text: str, state: str) -> None:
        self.status_label.setText(text)
        self.status_label.setProperty("state", state)
        _repolish(self.status_label)

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setToolTip(message)
        self._set_status("Error", "error")

    def _clear_error(self) -> None:
        self.error_label.clear()
        if self.status_label.property("state") == "error":
            self._set_status("Stopped", "stopped")

    def _on_limit_changed(self, value: int) -> None:
        self.controller.set_max_messages(value)
        self._dirty_topics.update(self.controller.store.topics())
        self._save_config()

    def _save_config(self) -> None:
        self.config = AppConfig(
            host=self.selected_host() or self.config.host,
            port=self.port_spin.value(),
            max_messages=self.limit_spin.value(),
        )
        try:
            save_config(self.config, self._config_path)
        except OSError as exc:
            self._show_error(f"Could not save settings: {exc}")

    # Live updates

    def _on_message(self, message: StoredMessage) -> None:
        self._dirty_topics.add(message.topic)

    def _on_clients_changed(self) -> None:
        self._clients_dirty = True

    def _flush(self) -> None:
        if self._dirty_topics:
            dirty, self._dirty_topics = self._dirty_topics, set()
            store = self.controller.store
            for topic in dirty:
                self.topic_tree.update_topic(topic, store.count(topic))
            selected = self.topic_tree.selected_topic()
            if selected in dirty:
                self._reload_messages(selected)
            self._update_stats()
        if self._clients_dirty:
            self._clients_dirty = False
            self.clients_tree.set_clients(self.controller.clients.clients())
            self._update_stats()

    def _update_stats(self) -> None:
        store = self.controller.store
        clients = self.controller.clients.clients()
        online = sum(1 for c in clients if c.connected)
        self.stats_label.setText(
            f"{len(store.topics())} topics  \u00b7  {store.total()} messages stored  \u00b7  {online} clients connected"
        )

    def _on_topic_selected(self, topic: str | None) -> None:
        self.topic_label.setText(topic if topic else "Select a topic")
        self._reload_messages(topic)

    def _reload_messages(self, topic: str | None) -> None:
        selected = self._selected_message()
        messages = self.controller.store.messages(topic) if topic else []
        self.message_model.set_messages(messages)
        if selected is not None and selected in messages:
            self.message_table.selectRow(messages.index(selected))
        elif self.auto_scroll_check.isChecked():
            self.message_table.scrollToBottom()
        if selected is None or selected not in messages:
            self._show_payload(None)

    def _selected_message(self) -> StoredMessage | None:
        rows = self.message_table.selectionModel().selectedRows()
        return self.message_model.message_at(rows[0].row()) if rows else None

    def _on_message_selection(self, _selected: QItemSelection, _deselected: QItemSelection) -> None:
        self._show_payload(self._selected_message())

    def _on_format_toggled(self, _button: QPushButton, checked: bool) -> None:
        if checked:
            self.message_model.set_format(self.payload_format())
            self._show_payload(self._selected_message())

    def payload_format(self) -> PayloadFormat:
        return PayloadFormat.HEX if self.hex_button.isChecked() else PayloadFormat.UTF8

    def _show_payload(self, message: StoredMessage | None) -> None:
        if message is None:
            self.payload_info.setText("")
            self.payload_view.setPlainText("")
            return
        ts = message.timestamp.astimezone().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        parts = [f"{len(message.payload)} bytes", f"QoS {message.qos}"]
        if message.retain:
            parts.append("retained")
        parts += [message.client_id, ts]
        self.payload_info.setText("  \u00b7  ".join(parts))
        self.payload_view.setPlainText(format_payload(message.payload, self.payload_format()))

    # Export / clear

    def _prompt_export(self, all_topics: bool) -> None:
        topic = None if all_topics else self.topic_tree.selected_topic()
        if not all_topics and topic is None:
            self._show_error("Select a topic to export")
            return
        default_name = "mqtt_topics.csv" if topic is None else f"{topic.replace('/', '_') or 'topic'}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", default_name, "CSV files (*.csv)")
        if path:
            self.export_to(Path(path), topic)

    def export_to(self, path: Path, topic: str | None = None) -> int:
        store = self.controller.store
        history = store.snapshot() if topic is None else {topic: store.messages(topic)}
        try:
            rows = export_csv(path, history)
        except OSError as exc:
            self._show_error(f"Export failed: {exc}")
            return 0
        self._clear_error()
        self.statusBar().showMessage(f"Exported {rows} messages to {path}", 5000)
        return rows

    def _on_clear_clicked(self) -> None:
        answer = QMessageBox.question(self, "Clear history", "Delete all stored messages?")
        if answer == QMessageBox.StandardButton.Yes:
            self.clear_history()

    def clear_history(self) -> None:
        self.controller.store.clear()
        self._dirty_topics.clear()
        self.topic_tree.clear_topics()
        self.message_model.set_messages([])
        self._show_payload(None)
        self._update_stats()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._timer.stop()
        self.controller.stop()
        self._save_config()
        super().closeEvent(event)
