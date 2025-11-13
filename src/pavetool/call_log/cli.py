"""Command line interface for importing call logs."""

from __future__ import annotations

import argparse
from pathlib import Path

from .importer import CallLogImporter
from .integration import IntegrationPayloadBuilder


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("excel", type=Path, help="Path to the Excel call log")
    parser.add_argument(
        "--sheet",
        dest="sheet_name",
        help="Worksheet name. Defaults to the first sheet in the workbook.",
    )
    parser.add_argument(
        "--column",
        dest="columns",
        action="append",
        default=[],
        metavar="FIELD=HEADER",
        help=(
            "Column mapping expressed as FIELD=HEADER. Required fields are "
            "timestamp, caller, callee, direction and duration."
        ),
    )
    parser.add_argument(
        "--extra",
        dest="extra",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Additional constant values to attach to each record.",
    )
    parser.add_argument(
        "--json",
        dest="json_path",
        type=Path,
        help="Optional path to write the resulting JSON payload. Defaults to stdout.",
    )
    parser.add_argument(
        "--indent",
        dest="indent",
        type=int,
        default=None,
        help="Pretty-print JSON output with the provided indentation.",
    )
    return parser


def parse_key_value_pairs(pairs):
    mapping = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"Expected KEY=VALUE but received '{pair}'")
        key, value = pair.split("=", 1)
        mapping[key.strip()] = value.strip()
    return mapping


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    column_mapping = parse_key_value_pairs(args.columns)
    if not column_mapping:
        parser.error("At least one --column mapping must be provided")

    importer = CallLogImporter(column_mapping, sheet_name=args.sheet_name)
    entries = importer.load(args.excel)

    payload_builder = IntegrationPayloadBuilder(extra_fields=parse_key_value_pairs(args.extra))
    json_output = payload_builder.to_json(entries, indent=args.indent)

    if args.json_path:
        args.json_path.write_text(json_output, encoding="utf-8")
    else:
        print(json_output)
    return 0


if __name__ == "__main__":  # pragma: no cover - convenience entry point
    raise SystemExit(main())
