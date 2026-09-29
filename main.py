"""
main.py — pipeline entry point

Wires together all 3 stages:
    parser.py       raw log text      -> flat dict
    normalizer.py   flat dict         -> normalized envelope
    field_mapper.py normalized batch  -> canonical field names

and adds the piece that was missing: actually reading log files off disk
and turning them into records the pipeline can chew on.

--------------------------------------------------------------------------
USAGE

    python main.py -i FILE:FORMAT:SOURCE [-i FILE:FORMAT:SOURCE ...] [-o out.json]

Each -i / --input is:  <file_path>:<format_type>:<source_type>
    file_path     path to a log file on disk
    format_type   json | csv | syslog | xml | cef
    source_type   your label for where this file came from, e.g. db, network, auth

Example:
    python main.py \
        -i logs/db.jsonl:json:db \
        -i logs/net.csv:csv:network \
        -i logs/auth.log:syslog:auth \
        -o merged_output.json

--------------------------------------------------------------------------
FILE LAYOUT ASSUMPTIONS (how one file becomes many records)

    json / syslog / cef -> one record per non-empty line (JSON-Lines style)
    csv                 -> first line is the header row, one record per
                            line after that
    xml                 -> the whole file is treated as a single record
                            (XML doesn't split cleanly by line)

If a file doesn't match its declared format, that one file's non-parsing
lines are skipped with a warning printed to stderr rather than crashing
the whole run — same "don't let one bad record kill the batch" spirit as
parser.py's syslog fallback.
--------------------------------------------------------------------------
"""

import argparse
import json
import sys
from pathlib import Path

from parser import parse_log
from normalizer import normalize
from field_mapper import map_fields


# ---------------------------------------------------------------------------
# File reading — turns a file on disk into a list of raw record strings
# ---------------------------------------------------------------------------

def read_records_from_file(file_path, format_type):
    """
    Reads a single log file and splits it into raw record strings, ready
    to be handed one-by-one to parser.parse_log().

    Returns (raw_records, headers):
        raw_records  list[str]
        headers      list[str] | None   (only populated for csv)
    """
    format_type = format_type.lower()
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {file_path}")

    text = path.read_text(encoding="utf-8")

    if format_type == "xml":
        # XML doesn't split by line reliably -> treat whole file as 1 record
        stripped = text.strip()
        return ([stripped] if stripped else []), None

    if format_type == "csv":
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if not lines:
            return [], None
        headers = [h.strip() for h in lines[0].split(",")]
        return lines[1:], headers

    # json (JSON-Lines), syslog, cef -> one record per non-empty line
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return lines, None


# ---------------------------------------------------------------------------
# Stage 1 + 2 combined: file -> parsed -> normalized records
# ---------------------------------------------------------------------------

def build_normalized_records(input_specs):
    """
    input_specs: list of (file_path, format_type, source_type)
    Runs every record in every file through parse_log() then normalize().
    Bad individual records are skipped with a stderr warning; bad files
    (missing, wrong format entirely) still raise.
    """
    normalized_records = []

    for file_path, format_type, source_type in input_specs:
        raw_records, headers = read_records_from_file(file_path, format_type)

        parsed_count = 0
        for i, raw_log in enumerate(raw_records, start=1):
            try:
                parsed = parse_log(raw_log, format_type, headers=headers)
            except Exception as e:
                print(f"[warn] {file_path}:{i} failed to parse as {format_type}: {e}",
                      file=sys.stderr)
                continue

            normalized_records.append(
                normalize(parsed, source_type=source_type, format_type=format_type)
            )
            parsed_count += 1

        print(f"[info] {file_path}: parsed {parsed_count}/{len(raw_records)} record(s) "
              f"as {format_type} (source={source_type})", file=sys.stderr)

    return normalized_records


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------

def parse_input_spec(spec):
    """
    Parses  <file_path>:<format_type>:<source_type>  from the CLI.
    Splits from the right since Windows-style paths (C:\\logs\\db.log)
    contain colons of their own.
    """
    parts = spec.rsplit(":", 2)
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(
            f"--input must look like  <file_path>:<format_type>:<source_type>  (got: {spec!r})"
        )
    file_path, format_type, source_type = parts
    return file_path, format_type, source_type


def make_auto_confirm_callback():
    """
    Non-interactive stand-in for field_mapper.default_ask_org(), for CI
    runs or any time you don't want the pipeline blocking on stdin.
    Every doubtful match is auto-accepted and logged to stderr instead.
    """
    def callback(field_a, field_b, score, context):
        print(f"[auto-confirm] accepting '{field_a}' <-> '{field_b}' "
              f"({context}, confidence={score:.2f})", file=sys.stderr)
        return True
    return callback


def main():
    cli = argparse.ArgumentParser(
        description="Universal log preprocessing pipeline: parse -> normalize -> field-map."
    )
    cli.add_argument(
        "--input", "-i", action="append", required=True, type=parse_input_spec,
        metavar="FILE:FORMAT:SOURCE",
        help="Input file spec (repeatable), e.g. logs/db.jsonl:json:db",
    )
    cli.add_argument(
        "--output", "-o", default=None,
        help="Write result JSON to this path. If omitted, prints to stdout.",
    )
    cli.add_argument(
        "--auto-confirm", action="store_true",
        help="Skip interactive field-mapping prompts and auto-accept doubtful matches "
             "(use for CI / non-interactive runs).",
    )
    args = cli.parse_args()

    normalized_records = build_normalized_records(args.input)

    if not normalized_records:
        print("[warn] no records were successfully parsed from any input file — "
              "output will be empty.", file=sys.stderr)

    ask_org_callback = make_auto_confirm_callback() if args.auto_confirm else None
    if ask_org_callback:
        mapped_records, mapping_report = map_fields(normalized_records, ask_org_callback=ask_org_callback)
    else:
        mapped_records, mapping_report = map_fields(normalized_records)

    output = {
        "record_count": len(mapped_records),
        "field_mapping_report": mapping_report,
        "records": mapped_records,
    }
    output_json = json.dumps(output, indent=2, default=str)

    if args.output:
        Path(args.output).write_text(output_json, encoding="utf-8")
        print(f"[info] wrote {len(mapped_records)} record(s) -> {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
