from __future__ import annotations

import csv
import json
import socket

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget

from mqtt_broker.gui.main_window import MainWindow
from mqtt_broker.gui.message_model import MessageTableModel
from mqtt_broker.network import BindOption

OPTIONS = [BindOption("Loopback (127.0.0.1)", "127.0.0.1"), BindOption("All (0.0.0.0)", "0.0.0.0")]


@pytest.fixture
def window(qtbot, tmp_path, free_port):
    win = MainWindow(config_path=tmp_path / "config.json", bind_options=lambda: OPTIONS)
    qtbot.addWidget(win)
    win.port_spin.setValue(free_port)
    yield win
    win.controller.stop()


@pytest.fixture
def running(window, qtbot):
    assert window.select_host("127.0.0.1")
    qtbot.mouseClick(window.start_button, Qt.MouseButton.LeftButton)
    assert window.controller.running
    return window


def payload_cell(win: MainWindow, row: int) -> str:
    model = win.message_model
    return model.data(model.index(row, MessageTableModel.PAYLOAD_COLUMN))


def test_start_and_stop_from_gui(running, qtbot, tmp_path):
    win = running
    port = win.port_spin.value()
    assert win.start_button.text() == "Stop"
    assert f"127.0.0.1:{port}" in win.status_label.text()
    assert not win.port_spin.isEnabled() and not win.interface_combo.isEnabled()
    saved = json.loads((tmp_path / "config.json").read_text())
    assert saved["host"] == "127.0.0.1" and saved["port"] == port

    qtbot.mouseClick(win.start_button, Qt.MouseButton.LeftButton)
    assert not win.controller.running
    assert win.start_button.text() == "Start"
    assert win.port_spin.isEnabled()


def test_published_topic_appears_and_payload_toggles_hex(running, qtbot, mqtt_client):
    win = running
    pub = mqtt_client(win.port_spin.value(), "sensor-1")
    pub.publish("plant/line1/temp", b"\xffA\x00", qos=1).wait_for_publish(5)
    pub.publish("plant/line1/temp", "21.5 °C".encode(), qos=0).wait_for_publish(5)

    qtbot.waitUntil(lambda: win.topic_tree.topics() == ["plant/line1/temp"], timeout=5000)
    qtbot.waitUntil(lambda: win.topic_tree.topic_item("plant/line1/temp").text(1) == "2", timeout=5000)
    win.topic_tree.select_topic("plant/line1/temp")
    assert win.message_model.rowCount() == 2
    assert payload_cell(win, 0) == "\ufffdA\x00"
    assert payload_cell(win, 1) == "21.5 °C"

    qtbot.mouseClick(win.hex_button, Qt.MouseButton.LeftButton)
    assert payload_cell(win, 0) == "FF 41 00"
    assert payload_cell(win, 1) == "21.5 °C".encode().hex(" ").upper()

    win.message_table.selectRow(0)
    assert win.payload_view.toPlainText() == "FF 41 00"
    qtbot.mouseClick(win.utf8_button, Qt.MouseButton.LeftButton)
    assert win.payload_view.toPlainText() == "\ufffdA\x00"
    assert "sensor-1" in win.payload_info.text()


def test_new_messages_refresh_selected_topic(running, qtbot, mqtt_client):
    win = running
    pub = mqtt_client(win.port_spin.value(), "pub")
    pub.publish("a/b", b"1", qos=1).wait_for_publish(5)
    qtbot.waitUntil(lambda: win.topic_tree.topic_item("a/b") is not None, timeout=5000)
    win.topic_tree.select_topic("a/b")
    pub.publish("a/b", b"2", qos=1).wait_for_publish(5)
    qtbot.waitUntil(lambda: win.message_model.rowCount() == 2, timeout=5000)


def test_subscribed_devices_listed(running, qtbot, mqtt_client):
    win = running
    dev = mqtt_client(win.port_spin.value(), "device-42")
    dev.subscribe([("plant/#", 1), ("alarms", 0)])
    qtbot.waitUntil(lambda: win.clients_tree.subscriptions("device-42") == ["alarms", "plant/#"], timeout=5000)
    assert "1 clients connected" in win.stats_label.text()

    dev.disconnect()
    qtbot.waitUntil(lambda: "0 clients connected" in win.stats_label.text(), timeout=5000)
    assert win.clients_tree.topLevelItem(0).text(2) == "Disconnected"


def test_history_limit_from_gui(running, qtbot, mqtt_client):
    win = running
    win.limit_spin.setValue(3)
    pub = mqtt_client(win.port_spin.value(), "pub")
    for i in range(6):
        pub.publish("limited", str(i).encode(), qos=1).wait_for_publish(5)
    qtbot.waitUntil(lambda: win.controller.store.count("limited") == 3, timeout=5000)
    qtbot.waitUntil(lambda: win.topic_tree.topic_item("limited") is not None, timeout=5000)
    win.topic_tree.select_topic("limited")
    qtbot.waitUntil(lambda: win.message_model.rowCount() == 3, timeout=5000)
    assert [payload_cell(win, r) for r in range(3)] == ["3", "4", "5"]
    assert win.topic_tree.topic_item("limited").text(1) == "3"


def test_export_csv_from_gui(running, qtbot, mqtt_client, tmp_path):
    win = running
    pub = mqtt_client(win.port_spin.value(), "pub")
    pub.publish("x/1", b"\x01\x02", qos=1).wait_for_publish(5)
    pub.publish("x/2", b"hello", qos=1).wait_for_publish(5)
    qtbot.waitUntil(lambda: win.controller.store.total() == 2, timeout=5000)

    all_path, one_path = tmp_path / "all.csv", tmp_path / "one.csv"
    assert win.export_to(all_path) == 2
    assert win.export_to(one_path, "x/2") == 1

    with all_path.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert [(r["topic"], r["payload_hex"], r["client_id"]) for r in rows] == [
        ("x/1", "01 02", "pub"),
        ("x/2", "68 65 6C 6C 6F", "pub"),
    ]
    assert all(r["timestamp"] for r in rows)


def test_topic_filter(running, qtbot, mqtt_client):
    win = running
    pub = mqtt_client(win.port_spin.value(), "pub")
    for topic in ("plant/line1/temperature", "plant/line2/status", "alarms/line1/overtemp"):
        pub.publish(topic, b"1", qos=1).wait_for_publish(5)
    qtbot.waitUntil(lambda: len(win.topic_tree.topics()) == 3, timeout=5000)

    qtbot.keyClicks(win.topic_filter, "TEMP")
    assert win.topic_tree.visible_topics() == ["alarms/line1/overtemp", "plant/line1/temperature"]

    win.topic_filter.setText("plant/+/status")
    assert win.topic_tree.visible_topics() == ["plant/line2/status"]
    assert win.topic_tree.topic_item("plant/line1/temperature").isHidden()

    pub.publish("plant/line3/status", b"1", qos=1).wait_for_publish(5)
    pub.publish("other/topic", b"1", qos=1).wait_for_publish(5)
    qtbot.waitUntil(lambda: len(win.topic_tree.topics()) == 5, timeout=5000)
    assert win.topic_tree.visible_topics() == ["plant/line2/status", "plant/line3/status"]

    win.topic_filter.clear()
    assert len(win.topic_tree.visible_topics()) == 5


def test_clear_history(running, qtbot, mqtt_client):
    win = running
    mqtt_client(win.port_spin.value(), "pub").publish("gone", b"1", qos=1).wait_for_publish(5)
    qtbot.waitUntil(lambda: win.topic_tree.topics() == ["gone"], timeout=5000)
    win.clear_history()
    assert win.topic_tree.topics() == []
    assert win.controller.store.total() == 0


def test_port_conflict_shows_error(window, qtbot):
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", window.port_spin.value()))
        busy.listen()
        qtbot.mouseClick(window.start_button, Qt.MouseButton.LeftButton)
    assert not window.controller.running
    assert window.status_label.text() == "Error"
    assert str(window.port_spin.value()) in window.error_label.text()
    assert window.start_button.text() == "Start"


def test_long_texts_do_not_force_window_wider(window, qtbot):
    window.show()
    baseline = window.minimumSizeHint().width()
    long_text = "x" * 400
    window.topic_label.setText(long_text)
    window.payload_info.setText(long_text)
    window._show_error(long_text)
    window.stats_label.setText(long_text)
    assert window.minimumSizeHint().width() == baseline
    assert baseline <= 1024


def test_panels_are_movable_floatable_docks(window, qtbot):
    window.show()
    for dock in (window.topics_dock, window.messages_dock, window.payload_dock, window.clients_dock):
        features = dock.features()
        assert features & QDockWidget.DockWidgetFeature.DockWidgetMovable
        assert features & QDockWidget.DockWidgetFeature.DockWidgetFloatable

    window.clients_dock.setFloating(True)
    window.payload_dock.close()
    assert window.payload_dock.isHidden()
    window.reset_layout()
    assert not window.clients_dock.isFloating()
    assert window.payload_dock.isVisible()
    assert window.dockWidgetArea(window.clients_dock) == window.dockWidgetArea(window.topics_dock)


def test_fullscreen_toggle(window, qtbot):
    window.show()
    window.fullscreen_action.setChecked(True)
    qtbot.waitUntil(window.isFullScreen, timeout=2000)
    window.fullscreen_action.setChecked(False)
    qtbot.waitUntil(lambda: not window.isFullScreen(), timeout=2000)
