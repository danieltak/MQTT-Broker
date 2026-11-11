from __future__ import annotations

import threading
from collections import deque
from dataclasses import replace
from datetime import datetime, timezone

from .models import ClientInfo, StoredMessage

MIN_HISTORY = 1
MAX_HISTORY = 1_000_000


class MessageStore:
    """Thread-safe per-topic message history with a bounded size."""

    def __init__(self, max_messages: int = 1000) -> None:
        self._lock = threading.Lock()
        self._max = self._validate(max_messages)
        self._topics: dict[str, deque[StoredMessage]] = {}

    @staticmethod
    def _validate(value: int) -> int:
        if not MIN_HISTORY <= value <= MAX_HISTORY:
            raise ValueError(f"max_messages must be between {MIN_HISTORY} and {MAX_HISTORY}")
        return value

    @property
    def max_messages(self) -> int:
        return self._max

    def set_max_messages(self, value: int) -> None:
        value = self._validate(value)
        with self._lock:
            if value == self._max:
                return
            self._max = value
            # deque(iterable, maxlen) keeps the newest items when trimming
            self._topics = {t: deque(q, maxlen=value) for t, q in self._topics.items()}

    def add(self, message: StoredMessage) -> None:
        with self._lock:
            queue = self._topics.get(message.topic)
            if queue is None:
                queue = self._topics[message.topic] = deque(maxlen=self._max)
            queue.append(message)

    def topics(self) -> list[str]:
        with self._lock:
            return sorted(self._topics)

    def messages(self, topic: str) -> list[StoredMessage]:
        with self._lock:
            return list(self._topics.get(topic, ()))

    def count(self, topic: str) -> int:
        with self._lock:
            return len(self._topics.get(topic, ()))

    def total(self) -> int:
        with self._lock:
            return sum(len(q) for q in self._topics.values())

    def snapshot(self) -> dict[str, list[StoredMessage]]:
        with self._lock:
            return {t: list(q) for t, q in sorted(self._topics.items())}

    def clear(self) -> None:
        with self._lock:
            self._topics.clear()


class ClientRegistry:
    """Thread-safe view of connected clients and their subscriptions."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._clients: dict[str, ClientInfo] = {}

    def connect(self, client_id: str, address: str) -> None:
        with self._lock:
            existing = self._clients.get(client_id)
            subscriptions = existing.subscriptions if existing else {}
            self._clients[client_id] = ClientInfo(
                client_id=client_id,
                address=address,
                connected=True,
                connected_at=datetime.now(timezone.utc),
                subscriptions=subscriptions,
            )

    def disconnect(self, client_id: str, clear_subscriptions: bool) -> None:
        with self._lock:
            info = self._clients.get(client_id)
            if info is None:
                return
            info.connected = False
            if clear_subscriptions:
                info.subscriptions.clear()

    def subscribe(self, client_id: str, topic: str, qos: int) -> None:
        with self._lock:
            info = self._clients.get(client_id)
            if info is not None:
                info.subscriptions[topic] = qos

    def unsubscribe(self, client_id: str, topic: str) -> None:
        with self._lock:
            info = self._clients.get(client_id)
            if info is not None:
                info.subscriptions.pop(topic, None)

    def clients(self) -> list[ClientInfo]:
        with self._lock:
            return [
                replace(c, subscriptions=dict(c.subscriptions))
                for _, c in sorted(self._clients.items())
            ]

    def clear(self) -> None:
        with self._lock:
            self._clients.clear()
