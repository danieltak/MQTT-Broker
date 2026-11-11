from __future__ import annotations

import socket
from dataclasses import dataclass

import psutil

LOOPBACK = "127.0.0.1"
ALL_INTERFACES = "0.0.0.0"


@dataclass(frozen=True, slots=True)
class BindOption:
    label: str
    address: str


def list_bind_options() -> list[BindOption]:
    """Loopback, all interfaces, then the IPv4 address of every adapter that is up."""
    options = [
        BindOption(f"Loopback ({LOOPBACK})", LOOPBACK),
        BindOption(f"All interfaces ({ALL_INTERFACES})", ALL_INTERFACES),
    ]
    stats = psutil.net_if_stats()
    for name, addresses in sorted(psutil.net_if_addrs().items()):
        stat = stats.get(name)
        if stat is None or not stat.isup:
            continue
        for addr in addresses:
            if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                options.append(BindOption(f"{name} ({addr.address})", addr.address))
    return options


def check_port_available(host: str, port: int) -> None:
    """Raise OSError if host:port cannot be bound exclusively."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        # amqtt binds with SO_REUSEADDR, which on Windows silently shares a busy port
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.bind((host, port))
