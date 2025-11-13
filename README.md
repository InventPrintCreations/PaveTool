# PaveTool

Utilities to ingest call log Excel spreadsheets into integration-friendly payloads.

## Features

- Parse Excel-based call logs with configurable column mappings.
- Normalize timestamps and durations into consistent data structures.
- Produce JSON payloads ready for integration with other systems.
- Command line helper for quick conversions.

## Usage

Install the package and run the CLI:

```bash
pip install .
pavetool-call-log path/to/call_log.xlsx \
  --column timestamp=Timestamp \
  --column caller=Caller \
  --column callee=Callee \
  --column direction=Direction \
  --column duration=Duration \
  --column notes=Notes \
  --column ticket_id=Ticket \
  --json payload.json \
  --indent 2
```

The generated `payload.json` file contains a JSON array of call log entries with normalized
values that you can POST to a remote integration endpoint.
