from __future__ import annotations

import ipaddress
import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from .store import MAX_HISTORY, MIN_HISTORY

log = logging.getLogger(__name__)


@dataclass(slots=True)
class AppConfig:
    host: str = "127.0.0.1"
    port: int = 1883
    max_messages: int = 1000

    def validate(self) -> None:
        ipaddress.IPv4Address(self.host)
        if not 1 <= self.port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if not MIN_HISTORY <= self.max_messages <= MAX_HISTORY:
            raise ValueError(f"max_messages must be between {MIN_HISTORY} and {MAX_HISTORY}")


def default_config_path() -> Path:
    base = os.environ.get("APPDATA") or Path.home() / ".config"
    return Path(base) / "mqtt_broker" / "config.json"


def load_config(path: Path | None = None) -> AppConfig:
    path = path or default_config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        defaults = AppConfig()
        config = AppConfig(
            host=str(data.get("host", defaults.host)),
            port=int(data.get("port", defaults.port)),
            max_messages=int(data.get("max_messages", defaults.max_messages)),
        )
        config.validate()
        return config
    except FileNotFoundError:
        return AppConfig()
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        log.warning("Ignoring invalid config %s: %s", path, exc)
        return AppConfig()


def save_config(config: AppConfig, path: Path | None = None) -> None:
    path = path or default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
