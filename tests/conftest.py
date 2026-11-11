from __future__ import annotations

import os
import socket
import time
from collections.abc import Callable, Iterator

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import paho.mqtt.client as mqtt  # noqa: E402


def wait_until(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition not met within timeout")


@pytest.fixture
def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


MqttFactory = Callable[..., mqtt.Client]


@pytest.fixture
def mqtt_client() -> Iterator[MqttFactory]:
    created: list[mqtt.Client] = []

    def make(port: int, client_id: str, clean_session: bool = True) -> mqtt.Client:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id, clean_session=clean_session)
        client.connect("127.0.0.1", port)
        client.loop_start()
        created.append(client)
        deadline = time.monotonic() + 5
        while not client.is_connected():
            if time.monotonic() > deadline:
                raise AssertionError(f"{client_id} failed to connect")
            time.sleep(0.02)
        return client

    yield make
    for client in created:
        client.disconnect()
        client.loop_stop()
