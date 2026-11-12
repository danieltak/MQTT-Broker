from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class PayloadFormat(StrEnum):
    UTF8 = "utf8"
    HEX = "hex"


@dataclass(frozen=True, slots=True)
class StoredMessage:
    timestamp: datetime
    topic: str
    payload: bytes
    qos: int
    retain: bool
    client_id: str


@dataclass(slots=True)
class ClientInfo:
    client_id: str
    address: str
    connected: bool
    connected_at: datetime
    subscriptions: dict[str, int] = field(default_factory=dict)


def format_payload(payload: bytes, fmt: PayloadFormat) -> str:
    if fmt is PayloadFormat.HEX:
        return payload.hex(" ").upper()
    return payload.decode("utf-8", errors="replace")


def topic_matches(pattern: str, topic: str) -> bool:
    """MQTT wildcard match if the pattern contains '+' or '#', otherwise case-insensitive substring."""
    if not pattern:
        return True
    if "+" not in pattern and "#" not in pattern:
        return pattern.lower() in topic.lower()
    pattern_levels = pattern.split("/")
    topic_levels = topic.split("/")
    for index, level in enumerate(pattern_levels):
        if level == "#":
            return True
        if index >= len(topic_levels) or level not in ("+", topic_levels[index]):
            return False
    return len(pattern_levels) == len(topic_levels)
