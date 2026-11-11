from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from pathlib import Path

from .models import PayloadFormat, StoredMessage, format_payload

CSV_COLUMNS = ("topic", "timestamp", "payload_hex", "payload_utf8", "qos", "retain", "client_id")
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _safe_cell(value: str) -> str:
    # Prevent CSV/formula injection when the file is opened in a spreadsheet
    return "'" + value if value.startswith(_FORMULA_PREFIXES) else value


def export_csv(path: Path, history: Mapping[str, Sequence[StoredMessage]]) -> int:
    """Write one row per message, grouped by topic and ordered by time. Returns row count."""
    rows = 0
    with Path(path).open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(CSV_COLUMNS)
        for topic in sorted(history):
            for msg in sorted(history[topic], key=lambda m: m.timestamp):
                writer.writerow((
                    _safe_cell(topic),
                    msg.timestamp.astimezone().isoformat(timespec="milliseconds"),
                    format_payload(msg.payload, PayloadFormat.HEX),
                    _safe_cell(format_payload(msg.payload, PayloadFormat.UTF8)),
                    msg.qos,
                    int(msg.retain),
                    _safe_cell(msg.client_id),
                ))
                rows += 1
    return rows
