import csv
import json
import socket
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from mqtt_broker import network
from mqtt_broker.config import AppConfig, load_config, save_config
from mqtt_broker.exporter import CSV_COLUMNS, export_csv
from mqtt_broker.models import StoredMessage

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def read_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.reader(fh))


def test_export_csv_rows_sorted_by_topic_then_time(tmp_path):
    later = StoredMessage(T0 + timedelta(seconds=1), "b", b"2", 1, True, "c2")
    earlier = StoredMessage(T0, "b", b"\xff\n1", 0, False, "c1")
    other = StoredMessage(T0, "a", b"x", 0, False, "c1")
    path = tmp_path / "out.csv"

    assert export_csv(path, {"b": [later, earlier], "a": [other]}) == 3

    rows = read_rows(path)
    assert tuple(rows[0]) == CSV_COLUMNS
    assert [r[0] for r in rows[1:]] == ["a", "b", "b"]
    assert rows[2][2] == "FF 0A 31"
    assert rows[2][3] == "\ufffd\n1"
    assert rows[3][4:] == ["1", "1", "c2"]
    assert datetime.fromisoformat(rows[2][1]) == T0


def test_export_csv_neutralises_formulas(tmp_path):
    m = StoredMessage(T0, "=cmd", b"=HYPERLINK(1)", 0, False, "+evil")
    path = tmp_path / "out.csv"
    export_csv(path, {m.topic: [m]})
    row = read_rows(path)[1]
    assert row[0] == "'=cmd"
    assert row[3] == "'=HYPERLINK(1)"
    assert row[6] == "'+evil"


def test_config_round_trip_and_invalid_fallback(tmp_path):
    path = tmp_path / "cfg" / "config.json"
    assert load_config(path) == AppConfig()
    save_config(AppConfig("192.168.1.5", 1884, 50), path)
    assert load_config(path) == AppConfig("192.168.1.5", 1884, 50)

    path.write_text(json.dumps({"host": "not-an-ip", "port": 1}), encoding="utf-8")
    assert load_config(path) == AppConfig()
    path.write_text("{broken", encoding="utf-8")
    assert load_config(path) == AppConfig()


def test_bind_options_include_up_ipv4_adapters_only(monkeypatch):
    addr = lambda fam, ip: SimpleNamespace(family=fam, address=ip)  # noqa: E731
    monkeypatch.setattr(network.psutil, "net_if_addrs", lambda: {
        "Ethernet": [addr(socket.AF_INET, "10.0.0.5"), addr(socket.AF_INET6, "fe80::1")],
        "Wi-Fi": [addr(socket.AF_INET, "192.168.1.9")],
        "Loopback Pseudo-Interface 1": [addr(socket.AF_INET, "127.0.0.1")],
    })
    monkeypatch.setattr(network.psutil, "net_if_stats", lambda: {
        "Ethernet": SimpleNamespace(isup=True),
        "Wi-Fi": SimpleNamespace(isup=False),
        "Loopback Pseudo-Interface 1": SimpleNamespace(isup=True),
    })
    addresses = [o.address for o in network.list_bind_options()]
    assert addresses == ["127.0.0.1", "0.0.0.0", "10.0.0.5"]


def test_check_port_available_detects_busy_port():
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        with pytest.raises(OSError):
            network.check_port_available("127.0.0.1", busy.getsockname()[1])
