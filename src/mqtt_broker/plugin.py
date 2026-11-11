from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from amqtt.broker import BrokerContext
from amqtt.plugins.base import BasePlugin
from amqtt.session import ApplicationMessage, Session

from .models import StoredMessage


class BrokerEventSink(Protocol):
    def client_connected(self, client_id: str, address: str) -> None: ...
    def client_disconnected(self, client_id: str, clean_session: bool) -> None: ...
    def client_subscribed(self, client_id: str, topic: str, qos: int) -> None: ...
    def client_unsubscribed(self, client_id: str, topic: str) -> None: ...
    def message_received(self, message: StoredMessage) -> None: ...


class CapturePlugin(BasePlugin[BrokerContext]):
    """amqtt plugin forwarding broker events to a sink attached after the broker is created."""

    def __init__(self, context: BrokerContext) -> None:
        super().__init__(context)
        self.sink: BrokerEventSink | None = None

    async def on_broker_client_connected(self, *, client_id: str, client_session: Session, **_: Any) -> None:
        if self.sink:
            address = f"{client_session.remote_address}:{client_session.remote_port}"
            self.sink.client_connected(client_id, address)

    async def on_broker_client_disconnected(self, *, client_id: str, client_session: Session, **_: Any) -> None:
        if self.sink:
            self.sink.client_disconnected(client_id, bool(client_session.clean_session))

    async def on_broker_client_subscribed(self, *, client_id: str, topic: str, qos: int, **_: Any) -> None:
        if self.sink:
            self.sink.client_subscribed(client_id, topic, qos)

    async def on_broker_client_unsubscribed(self, *, client_id: str, topic: str, **_: Any) -> None:
        if self.sink:
            self.sink.client_unsubscribed(client_id, topic)

    # Broadcast (not "received") fires only for validated, permitted publishes
    async def on_broker_message_broadcast(self, *, client_id: str, message: ApplicationMessage, **_: Any) -> None:
        if self.sink:
            self.sink.message_received(StoredMessage(
                timestamp=datetime.now(timezone.utc),
                topic=message.topic,
                payload=bytes(message.data or b""),
                qos=message.qos or 0,
                retain=bool(message.retain),
                client_id=client_id,
            ))
