"""Minimal XLSX reader used by the importer.

The implementation intentionally only covers the subset of the XLSX format
required for the importer tests: plain text, numbers, booleans and shared
strings. This avoids the need for heavy third-party dependencies such as
``openpyxl`` while keeping the importer fully functional for structured call
logs exported from Excel.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, List, Optional
from xml.etree import ElementTree as ET


NAMESPACES = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


@dataclass
class WorksheetRef:
    sheet_id: str
    name: str
    rel_id: str


def iter_rows(path: Path | str, *, sheet_name: str | None = None) -> Iterator[List[object | None]]:
    """Yield rows from an XLSX worksheet."""

    with zipfile.ZipFile(Path(path)) as archive:
        shared_strings = _load_shared_strings(archive)
        sheets = _load_sheets(archive)

        target_sheet = _resolve_sheet(sheets, sheet_name)
        sheet_path = target_sheet.rel_id
        rels = _load_relationships(archive, "xl/_rels/workbook.xml.rels")
        sheet_target = rels.get(sheet_path)
        if sheet_target is None:
            raise KeyError(f"Sheet data for relationship '{sheet_path}' not found")

        yield from _load_sheet_rows(archive, f"xl/{sheet_target}", shared_strings)


def _load_shared_strings(archive: zipfile.ZipFile) -> List[str]:
    try:
        with archive.open("xl/sharedStrings.xml") as shared:
            tree = ET.parse(shared)
    except KeyError:
        return []

    strings = []
    for si in tree.findall("main:si", NAMESPACES):
        text = "".join(node.text or "" for node in si.findall("main:t", NAMESPACES))
        strings.append(text)
    return strings


def _load_sheets(archive: zipfile.ZipFile) -> List[WorksheetRef]:
    with archive.open("xl/workbook.xml") as workbook:
        tree = ET.parse(workbook)

    sheets = []
    for element in tree.findall("main:sheets/main:sheet", NAMESPACES):
        sheets.append(
            WorksheetRef(
                sheet_id=element.get("sheetId"),
                name=element.get("name"),
                rel_id=element.get(f"{{{NAMESPACES['rel']}}}id"),
            )
        )
    return sheets


def _resolve_sheet(sheets: Iterable[WorksheetRef], sheet_name: str | None) -> WorksheetRef:
    sheets = list(sheets)
    if not sheets:
        raise ValueError("Workbook does not contain any sheets")

    if sheet_name is None:
        return sheets[0]

    for sheet in sheets:
        if sheet.name == sheet_name:
            return sheet
    raise KeyError(f"Worksheet '{sheet_name}' not found. Available: {[s.name for s in sheets]}")


def _load_relationships(archive: zipfile.ZipFile, path: str) -> dict[str, str]:
    try:
        with archive.open(path) as rels_file:
            tree = ET.parse(rels_file)
    except KeyError:
        return {}

    relationships = {}
    for rel in tree.iter():
        if rel.tag.endswith("Relationship"):
            relationships[rel.get("Id")] = rel.get("Target")
    return relationships


def _col_to_index(col: str) -> int:
    result = 0
    for char in col:
        if not char.isalpha():
            break
        result = result * 26 + (ord(char.upper()) - 64)
    return result - 1


def _load_sheet_rows(
    archive: zipfile.ZipFile, path: str, shared_strings: List[str]
) -> Iterator[List[object | None]]:
    with archive.open(path) as sheet_file:
        tree = ET.parse(sheet_file)

    sheet_data = tree.find("main:sheetData", NAMESPACES)
    if sheet_data is None:
        return iter([])

    for row in sheet_data.findall("main:row", NAMESPACES):
        cells: List[object | None] = []
        last_index = -1
        for cell in row.findall("main:c", NAMESPACES):
            ref = cell.get("r") or ""
            col_ref = "".join(ch for ch in ref if ch.isalpha())
            index = _col_to_index(col_ref)
            while last_index + 1 < index:
                cells.append(None)
                last_index += 1

            value = _extract_cell_value(cell, shared_strings)
            cells.append(value)
            last_index = index

        yield cells


def _extract_cell_value(cell, shared_strings: List[str]) -> object | None:
    value_node = cell.find("main:v", NAMESPACES)
    cell_type = cell.get("t")

    if value_node is None:
        if cell_type == "inlineStr":
            text = cell.find("main:is/main:t", NAMESPACES)
            return text.text if text is not None else ""
        return None

    raw_value = value_node.text
    if raw_value is None:
        return None

    if cell_type == "s":
        return shared_strings[int(raw_value)]
    if cell_type == "b":
        return raw_value == "1"
    if cell_type in {"str", "inlineStr"}:
        return raw_value

    try:
        number = float(raw_value)
    except ValueError:
        return raw_value

    if number.is_integer():
        return int(number)
    return number

