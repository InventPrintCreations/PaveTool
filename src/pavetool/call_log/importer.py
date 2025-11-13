"""Excel-based call log importer."""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Iterator, Mapping, Optional

from . import xlsx


@dataclass(frozen=True)
class CallLogEntry:
    """Structured representation of a single call log entry."""

    timestamp: _dt.datetime
    caller: str
    callee: str
    direction: str
    duration_seconds: int
    notes: str = ""
    metadata: Dict[str, str] = field(default_factory=dict)

    @property
    def duration(self) -> _dt.timedelta:
        """Return the call duration as a :class:`datetime.timedelta`."""

        return _dt.timedelta(seconds=self.duration_seconds)


class CallLogImporter:
    """Import call log information from an Excel spreadsheet.

    Parameters
    ----------
    column_mapping:
        Mapping between the canonical field names used by
        :class:`CallLogEntry` and the column headers present in the Excel
        sheet. Required keys are ``timestamp``, ``caller``, ``callee``,
        ``direction`` and ``duration``. Optional keys include ``notes`` and
        any additional metadata fields, which will be stored on the ``metadata``
        dictionary of each entry.
    sheet_name:
        Name of the worksheet to consume. When omitted the first sheet is
        used.
    timezone:
        Optional timezone info applied to naïve datetimes loaded from the
        spreadsheet.
    """

    REQUIRED_KEYS = {"timestamp", "caller", "callee", "direction", "duration"}

    def __init__(
        self,
        column_mapping: Mapping[str, str],
        *,
        sheet_name: Optional[str] = None,
        timezone: Optional[_dt.tzinfo] = None,
    ) -> None:
        missing = self.REQUIRED_KEYS - set(column_mapping)
        if missing:
            raise ValueError(
                "Missing column mappings for required fields: " + ", ".join(sorted(missing))
            )

        self._column_mapping = dict(column_mapping)
        self._sheet_name = sheet_name
        self._timezone = timezone

    # ------------------------------------------------------------------
    def load(self, path: Path | str) -> Iterable[CallLogEntry]:
        """Load entries from *path*.

        Parameters
        ----------
        path:
            File system path to the Excel workbook.
        """

        rows = xlsx.iter_rows(path, sheet_name=self._sheet_name)
        return tuple(self._consume_rows(rows))

    # ------------------------------------------------------------------
    def _consume_rows(self, rows: Iterator[Iterable[object | None]]) -> Iterator[CallLogEntry]:
        header_row = None
        for row in rows:
            if header_row is None:
                header_row = self._build_header_index(row)
                continue

            if self._is_empty_row(row):
                continue

            yield self._row_to_entry(row, header_row)

    # ------------------------------------------------------------------
    def _build_header_index(self, headers: Iterable[object | None]) -> Dict[str, int]:
        header_map: Dict[str, int] = {}
        for idx, header in enumerate(headers):
            if header is None:
                continue
            header_map[str(header).strip().lower()] = idx
        return header_map

    # ------------------------------------------------------------------
    def _is_empty_row(self, row: Iterable[object | None]) -> bool:
        return all(cell is None or (isinstance(cell, str) and not cell.strip()) for cell in row)

    # ------------------------------------------------------------------
    def _row_to_entry(self, row, header_index: Mapping[str, int]) -> CallLogEntry:
        lookup = self._column_mapping

        def get_value(field: str, default: Optional[object] = None):
            column = lookup.get(field)
            if column is None:
                return default
            position = header_index.get(column.lower())
            if position is None:
                raise KeyError(f"Column '{column}' for field '{field}' not found in sheet")
            try:
                return row[position]
            except IndexError:
                return default

        timestamp = self._parse_timestamp(get_value("timestamp"))
        caller = self._ensure_text(get_value("caller"))
        callee = self._ensure_text(get_value("callee"))
        direction = self._ensure_text(get_value("direction"))
        duration_seconds = self._parse_duration(get_value("duration"))
        notes = self._ensure_text(get_value("notes", ""))

        metadata: Dict[str, str] = {}
        for field in lookup:
            if field in self.REQUIRED_KEYS or field == "notes":
                continue
            metadata[field] = self._ensure_text(get_value(field, ""))

        return CallLogEntry(
            timestamp=timestamp,
            caller=caller,
            callee=callee,
            direction=direction,
            duration_seconds=duration_seconds,
            notes=notes,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    def _parse_timestamp(self, value) -> _dt.datetime:
        if isinstance(value, _dt.datetime):
            ts = value
        elif isinstance(value, _dt.date):
            ts = _dt.datetime.combine(value, _dt.time())
        elif isinstance(value, (float, int)):
            ts = _dt.datetime(1899, 12, 30) + _dt.timedelta(days=float(value))
        elif isinstance(value, str):
            ts = self._parse_timestamp_from_string(value)
        else:
            raise TypeError(f"Unsupported timestamp value: {value!r}")

        if ts.tzinfo is None and self._timezone is not None:
            ts = ts.replace(tzinfo=self._timezone)
        return ts

    # ------------------------------------------------------------------
    def _parse_timestamp_from_string(self, value: str) -> _dt.datetime:
        value = value.strip()
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%m/%d/%Y %H:%M:%S",
            "%m/%d/%Y %H:%M",
            "%m/%d/%y %H:%M",
            "%Y-%m-%d",
            "%m/%d/%Y",
        ):
            try:
                return _dt.datetime.strptime(value, fmt)
            except ValueError:
                continue
        raise ValueError(f"Could not parse timestamp: {value!r}")

    # ------------------------------------------------------------------
    def _parse_duration(self, value) -> int:
        if isinstance(value, _dt.timedelta):
            return int(value.total_seconds())
        if isinstance(value, (int, float)):
            if value > 0 and value < 1:
                return int(round(value * 24 * 3600))
            return int(value)
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return 0
            for separator in ("h", "m", "s"):
                if separator in value.lower():
                    return self._parse_human_duration(value)
            if ":" in value:
                return self._parse_clock_duration(value)
            return int(float(value))
        raise TypeError(f"Unsupported duration value: {value!r}")

    # ------------------------------------------------------------------
    def _parse_human_duration(self, value: str) -> int:
        total_seconds = 0
        number = ""
        for ch in value:
            if ch.isdigit() or ch == ".":
                number += ch
            else:
                unit = ch.lower()
                if not number:
                    continue
                amount = float(number)
                number = ""
                if unit == "h":
                    total_seconds += int(amount * 3600)
                elif unit == "m":
                    total_seconds += int(amount * 60)
                elif unit == "s":
                    total_seconds += int(amount)
        if number:
            total_seconds += int(float(number))
        return total_seconds

    # ------------------------------------------------------------------
    def _parse_clock_duration(self, value: str) -> int:
        parts = value.split(":")
        if len(parts) == 2:
            hours = 0
            minutes, seconds = parts
        elif len(parts) == 3:
            hours, minutes, seconds = parts
        else:
            raise ValueError(f"Unrecognized clock duration: {value!r}")

        hours = int(float(hours)) if isinstance(hours, str) and hours else 0
        minutes = int(float(minutes)) if minutes else 0
        seconds = int(float(seconds)) if seconds else 0
        return hours * 3600 + minutes * 60 + seconds

    # ------------------------------------------------------------------
    def _ensure_text(self, value) -> str:
        if value is None:
            return ""
        return str(value).strip()

