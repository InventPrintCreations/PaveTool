"""Helpers to prepare call log data for third-party integrations."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Iterable, List, Mapping

from .importer import CallLogEntry


class IntegrationPayloadBuilder:
    """Generate payloads that are easy to hand over to remote services."""

    def __init__(self, *, extra_fields: Mapping[str, str] | None = None) -> None:
        self._extra_fields = dict(extra_fields or {})

    def to_dicts(self, entries: Iterable[CallLogEntry]) -> List[Mapping[str, object]]:
        payload: List[Mapping[str, object]] = []
        for entry in entries:
            row = asdict(entry)
            row.update(self._extra_fields)
            payload.append(row)
        return payload

    def to_json(self, entries: Iterable[CallLogEntry], *, indent: int | None = None) -> str:
        return json.dumps(self.to_dicts(entries), indent=indent, default=str)

