from datetime import datetime, timedelta, timezone

import pytest

from mqtt_broker.models import PayloadFormat, StoredMessage, format_payload
from mqtt_broker.store import ClientRegistry, MessageStore

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def msg(topic: str, payload: bytes, n: int = 0) -> StoredMessage:
    return StoredMessage(T0 + timedelta(seconds=n), topic, payload, 0, False, "c1")


def test_store_keeps_newest_up_to_limit():
    store = MessageStore(max_messages=3)
    for i in range(5):
        store.add(msg("a", bytes([i]), i))
    assert [m.payload for m in store.messages("a")] == [b"\x02", b"\x03", b"\x04"]


def test_shrinking_limit_trims_oldest_and_growing_keeps_all():
    store = MessageStore(max_messages=10)
    for i in range(6):
        store.add(msg("a", bytes([i]), i))
    store.set_max_messages(2)
    assert [m.payload for m in store.messages("a")] == [b"\x04", b"\x05"]
    store.set_max_messages(5)
    store.add(msg("a", b"\x06", 6))
    assert store.count("a") == 3


@pytest.mark.parametrize("value", [0, -1, 1_000_001])
def test_store_rejects_invalid_limit(value):
    with pytest.raises(ValueError):
        MessageStore(value)


def test_store_topics_snapshot_and_clear():
    store = MessageStore()
    store.add(msg("b", b"1"))
    store.add(msg("a", b"2"))
    assert store.topics() == ["a", "b"]
    assert store.total() == 2
    assert list(store.snapshot()) == ["a", "b"]
    store.clear()
    assert store.topics() == []


def test_payload_is_stored_as_bytes_and_formatted():
    raw = b"\xffA\x00"
    assert format_payload(raw, PayloadFormat.HEX) == "FF 41 00"
    assert format_payload(raw, PayloadFormat.UTF8) == "\ufffdA\x00"
    assert format_payload("héllo".encode(), PayloadFormat.UTF8) == "héllo"


def test_client_registry_lifecycle():
    reg = ClientRegistry()
    reg.connect("dev1", "1.2.3.4:5")
    reg.subscribe("dev1", "a/#", 1)
    reg.subscribe("ghost", "x", 0)
    assert reg.clients()[0].subscriptions == {"a/#": 1}
    assert [c.client_id for c in reg.clients()] == ["dev1"]

    reg.disconnect("dev1", clear_subscriptions=False)
    info = reg.clients()[0]
    assert not info.connected and info.subscriptions == {"a/#": 1}

    reg.connect("dev1", "1.2.3.4:6")
    assert reg.clients()[0].subscriptions == {"a/#": 1}
    reg.unsubscribe("dev1", "a/#")
    reg.disconnect("dev1", clear_subscriptions=True)
    assert reg.clients()[0].subscriptions == {}


def test_client_registry_returns_copies():
    reg = ClientRegistry()
    reg.connect("dev1", "x")
    reg.clients()[0].subscriptions["hack"] = 0
    assert reg.clients()[0].subscriptions == {}
