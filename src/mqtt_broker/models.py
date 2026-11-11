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
