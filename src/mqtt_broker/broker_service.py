from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Protocol

from amqtt.broker import Broker

from .models import StoredMessage
from .network import check_port_available
from .plugin import CapturePlugin
from .store import ClientRegistry, MessageStore

log = logging.getLogger(__name__)


class BrokerListener(Protocol):
    """Callbacks invoked from the broker thread."""

    def on_message(self, message: StoredMessage) -> None: ...
    def on_clients_changed(self) -> None: ...


class BrokerStartError(RuntimeError):
    pass


class BrokerService:
    """Runs an amqtt broker on its own asyncio event loop in a background thread."""

    def __init__(
        self,
        store: MessageStore,
        clients: ClientRegistry,
        listener: BrokerListener | None = None,
    ) -> None:
        self.store = store
        self.clients = clients
        self.listener = listener
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._broker: Broker | None = None
        self.host: str | None = None
        self.port: int | None = None

    @property
    def running(self) -> bool:
        return self._broker is not None

    @staticmethod
    def _broker_config(host: str, port: int) -> dict[str, Any]:
        return {
            "listeners": {"default": {"type": "tcp", "bind": f"{host}:{port}"}},
            "plugins": {
                "amqtt.plugins.authentication.AnonymousAuthPlugin": {"allow_anonymous": True},
                f"{CapturePlugin.__module__}.{CapturePlugin.__name__}": {},
            },
        }

    def start(self, host: str, port: int, timeout: float = 10.0) -> None:
        if self.running:
            raise BrokerStartError("Broker is already running")
        try:
            check_port_available(host, port)
        except OSError as exc:
            raise BrokerStartError(f"Cannot bind {host}:{port} - {exc.strerror or exc}") from exc

        loop = asyncio.new_event_loop()
        thread = threading.Thread(target=self._run_loop, args=(loop,), name="mqtt-broker", daemon=True)
        thread.start()
        future = asyncio.run_coroutine_threadsafe(self._start_broker(host, port), loop)
        try:
            broker = future.result(timeout)
        except Exception as exc:
            future.cancel()
            self._stop_loop(loop, thread, timeout)
            raise BrokerStartError(f"Broker failed to start on {host}:{port} - {exc}") from exc

        self._loop, self._thread, self._broker = loop, thread, broker
        self.host, self.port = host, port
        log.info("Broker listening on %s:%s", host, port)

    def stop(self, timeout: float = 10.0) -> None:
        loop, thread, broker = self._loop, self._thread, self._broker
        if loop is None or thread is None or broker is None:
            return
        try:
            asyncio.run_coroutine_threadsafe(broker.shutdown(), loop).result(timeout)
        except Exception:
            log.exception("Error while shutting down broker")
        finally:
            self._stop_loop(loop, thread, timeout)
            self._loop = self._thread = self._broker = None
            self.host = self.port = None
            self.clients.clear()
            self._notify_clients()
        log.info("Broker stopped")

    @staticmethod
    def _run_loop(loop: asyncio.AbstractEventLoop) -> None:
        asyncio.set_event_loop(loop)
        loop.run_forever()

    @staticmethod
    def _stop_loop(loop: asyncio.AbstractEventLoop, thread: threading.Thread, timeout: float) -> None:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout)
        if not thread.is_alive():
            loop.close()

    async def _start_broker(self, host: str, port: int) -> Broker:
        broker = Broker(self._broker_config(host, port))
        plugin = broker.plugins_manager.get_plugin(CapturePlugin.__name__)
        if not isinstance(plugin, CapturePlugin):
            raise BrokerStartError("Capture plugin failed to load")
        plugin.sink = self
        await broker.start()
        return broker

    def _notify_clients(self) -> None:
        if self.listener:
            self.listener.on_clients_changed()

    # BrokerEventSink, called on the broker thread

    def client_connected(self, client_id: str, address: str) -> None:
        self.clients.connect(client_id, address)
        self._notify_clients()

    def client_disconnected(self, client_id: str, clean_session: bool) -> None:
        self.clients.disconnect(client_id, clear_subscriptions=clean_session)
        self._notify_clients()

    def client_subscribed(self, client_id: str, topic: str, qos: int) -> None:
        self.clients.subscribe(client_id, topic, qos)
        self._notify_clients()

    def client_unsubscribed(self, client_id: str, topic: str) -> None:
        self.clients.unsubscribe(client_id, topic)
        self._notify_clients()

    def message_received(self, message: StoredMessage) -> None:
        self.store.add(message)
        if self.listener:
            self.listener.on_message(message)
