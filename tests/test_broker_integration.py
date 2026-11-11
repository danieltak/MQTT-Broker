from __future__ import annotations

import socket

import pytest

from mqtt_broker.broker_service import BrokerService, BrokerStartError
from mqtt_broker.store import ClientRegistry, MessageStore

from .conftest import wait_until


class Recorder:
    def __init__(self) -> None:
        self.messages = []
        self.client_events = 0

    def on_message(self, message) -> None:
        self.messages.append(message)

    def on_clients_changed(self) -> None:
        self.client_events += 1


@pytest.fixture
def service(free_port):
    svc = BrokerService(MessageStore(5), ClientRegistry(), Recorder())
    svc.start("127.0.0.1", free_port)
    yield svc
    svc.stop()


def test_publish_is_stored_as_raw_bytes(service, mqtt_client):
    pub = mqtt_client(service.port, "publisher")
    pub.publish("plant/line1/temp", b"\xff\x00abc", qos=1, retain=True).wait_for_publish(5)

    wait_until(lambda: service.store.count("plant/line1/temp") == 1)
    stored = service.store.messages("plant/line1/temp")[0]
    assert stored.payload == b"\xff\x00abc"
    assert isinstance(stored.payload, bytes)
    assert (stored.qos, stored.retain, stored.client_id) == (1, True, "publisher")
    assert service.listener.messages == [stored]


def test_history_limit_applies_to_live_messages(service, mqtt_client):
    pub = mqtt_client(service.port, "publisher")
    for i in range(8):
        pub.publish("t", str(i).encode(), qos=1).wait_for_publish(5)
    wait_until(lambda: len(service.listener.messages) == 8)
    assert [m.payload for m in service.store.messages("t")] == [b"3", b"4", b"5", b"6", b"7"]


def test_subscriptions_are_tracked(service, mqtt_client):
    sub = mqtt_client(service.port, "device-1")
    sub.subscribe([("plant/#", 1), ("alarms", 0)])
    wait_until(lambda: service.clients.clients()[0].subscriptions == {"plant/#": 1, "alarms": 0})
    info = service.clients.clients()[0]
    assert info.connected and info.address.startswith("127.0.0.1:")

    sub.unsubscribe("alarms")
    wait_until(lambda: service.clients.clients()[0].subscriptions == {"plant/#": 1})

    sub.disconnect()
    wait_until(lambda: not service.clients.clients()[0].connected)


def test_port_in_use_raises(free_port):
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", free_port))
        busy.listen()
        svc = BrokerService(MessageStore(), ClientRegistry())
        with pytest.raises(BrokerStartError, match=str(free_port)):
            svc.start("127.0.0.1", free_port)
        assert not svc.running


def test_restart_on_same_port(free_port, mqtt_client):
    svc = BrokerService(MessageStore(), ClientRegistry())
    svc.start("127.0.0.1", free_port)
    svc.stop()
    assert not svc.running
    svc.start("127.0.0.1", free_port)
    try:
        mqtt_client(free_port, "again").publish("x", b"1", qos=1).wait_for_publish(5)
        wait_until(lambda: svc.store.count("x") == 1)
    finally:
        svc.stop()
