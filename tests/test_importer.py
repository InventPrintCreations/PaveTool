import datetime as dt
from pathlib import Path
import zipfile
from xml.etree import ElementTree as ET

from pavetool.call_log.importer import CallLogImporter


def excel_serial(dt_value: dt.datetime) -> float:
    base = dt.datetime(1899, 12, 30)
    delta = dt_value - base
    return delta.days + delta.seconds / 86400 + delta.microseconds / 86400_000000


def build_workbook(tmp_path: Path) -> Path:
    headers = [
        "Timestamp",
        "Caller",
        "Callee",
        "Direction",
        "Duration",
        "Notes",
        "Ticket",
    ]
    rows = [
        [dt.datetime(2023, 10, 1, 13, 30), "Alice", "Bob", "outbound", "00:05:30", "", "123"],
        [dt.datetime(2023, 10, 1, 14, 0), "Charlie", "Support", "inbound", 0.020833333333333332, "follow up", "456"],
    ]

    shared_strings = []
    string_ids = {}

    def add_string(value: str) -> int:
        if value not in string_ids:
            string_ids[value] = len(shared_strings)
            shared_strings.append(value)
        return string_ids[value]

    sheet_rows = []
    for row_index, row in enumerate([headers, *rows], start=1):
        cell_elements = []
        for column_index, value in enumerate(row):
            cell_ref = f"{chr(65 + column_index)}{row_index}"
            cell = ET.Element("c", r=cell_ref)
            if isinstance(value, dt.datetime):
                v = ET.SubElement(cell, "v")
                v.text = str(excel_serial(value))
            elif isinstance(value, (int, float)):
                v = ET.SubElement(cell, "v")
                v.text = str(value)
            else:
                idx = add_string(str(value))
                cell.set("t", "s")
                v = ET.SubElement(cell, "v")
                v.text = str(idx)
            cell_elements.append(cell)
        row_el = ET.Element("row", r=str(row_index))
        row_el.extend(cell_elements)
        sheet_rows.append(row_el)

    sheet_data = ET.Element("sheetData")
    for row_el in sheet_rows:
        sheet_data.append(row_el)

    worksheet = ET.Element("worksheet", xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main")
    worksheet.append(sheet_data)
    worksheet_xml = ET.tostring(worksheet, encoding="utf-8", xml_declaration=True)

    sst = ET.Element("sst", xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main", count=str(len(shared_strings)))
    for value in shared_strings:
        si = ET.SubElement(sst, "si")
        t = ET.SubElement(si, "t")
        t.text = value
    shared_xml = ET.tostring(sst, encoding="utf-8", xml_declaration=True)

    workbook = ET.Element(
        "workbook",
        xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        attrib={"xmlns:r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"},
    )
    sheets = ET.SubElement(workbook, "sheets")
    ET.SubElement(sheets, "sheet", name="Calls", sheetId="1", attrib={"{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id": "rId1"})
    workbook_xml = ET.tostring(workbook, encoding="utf-8", xml_declaration=True)

    rels = ET.Element("Relationships", xmlns="http://schemas.openxmlformats.org/package/2006/relationships")
    ET.SubElement(rels, "Relationship", Id="rId1", Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet", Target="worksheets/sheet1.xml")
    ET.SubElement(rels, "Relationship", Id="rId2", Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings", Target="sharedStrings.xml")
    rels_xml = ET.tostring(rels, encoding="utf-8", xml_declaration=True)

    pkg_rels = ET.Element("Relationships", xmlns="http://schemas.openxmlformats.org/package/2006/relationships")
    ET.SubElement(pkg_rels, "Relationship", Id="rId1", Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument", Target="xl/workbook.xml")
    pkg_rels_xml = ET.tostring(pkg_rels, encoding="utf-8", xml_declaration=True)

    content_types = ET.Element("Types", xmlns="http://schemas.openxmlformats.org/package/2006/content-types")
    ET.SubElement(content_types, "Default", Extension="rels", ContentType="application/vnd.openxmlformats-package.relationships+xml")
    ET.SubElement(content_types, "Default", Extension="xml", ContentType="application/xml")
    ET.SubElement(content_types, "Override", PartName="/xl/workbook.xml", ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml")
    ET.SubElement(content_types, "Override", PartName="/xl/worksheets/sheet1.xml", ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml")
    ET.SubElement(content_types, "Override", PartName="/xl/sharedStrings.xml", ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml")
    content_types_xml = ET.tostring(content_types, encoding="utf-8", xml_declaration=True)

    file_path = tmp_path / "call_log.xlsx"
    with zipfile.ZipFile(file_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", pkg_rels_xml)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", rels_xml)
        zf.writestr("xl/sharedStrings.xml", shared_xml)
        zf.writestr("xl/worksheets/sheet1.xml", worksheet_xml)
    return file_path


def test_importer_parses_rows(tmp_path: Path):
    workbook_path = build_workbook(tmp_path)

    importer = CallLogImporter(
        {
            "timestamp": "Timestamp",
            "caller": "Caller",
            "callee": "Callee",
            "direction": "Direction",
            "duration": "Duration",
            "notes": "Notes",
            "ticket_id": "Ticket",
        },
        sheet_name="Calls",
    )

    entries = list(importer.load(workbook_path))
    assert len(entries) == 2
    first, second = entries

    assert first.caller == "Alice"
    assert first.duration_seconds == 330
    assert first.metadata["ticket_id"] == "123"

    assert second.duration_seconds == 1800
    assert second.metadata["ticket_id"] == "456"
    assert second.notes == "follow up"

