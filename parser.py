"""
parser.py — STEP 1 of the pipeline

Job: take a raw log line/blob + its format type, and turn it into a flat
python dict. No normalization/field-mapping logic here — that's steps 2 & 3.
Types are kept source-native (no coercion) — CSV values stay strings,
JSON/XML keep whatever type they came in as. Coercion decisions belong
in a later step, not parsing.
"""

import json
import re

try:
    import xmltodict
except ImportError:
    xmltodict = None  # xml parsing will raise a clear error if actually used


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def flatten(obj, parent_key="", sep="."):
    """
    Flattens nested dicts/lists into a single-level dict.
    {"user": {"id": 1}} -> {"user.id": 1}
    {"tags": ["a", "b"]} -> {"tags.0": "a", "tags.1": "b"}
    """
    items = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            items.update(flatten(v, new_key, sep))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            new_key = f"{parent_key}{sep}{i}" if parent_key else str(i)
            items.update(flatten(v, new_key, sep))
    else:
        items[parent_key] = obj
    return items


# ---------------------------------------------------------------------------
# Syslog (RFC3164-ish) parser
# ---------------------------------------------------------------------------

SYSLOG_PATTERN = re.compile(
    r"^(?P<timestamp>\w{3}\s+\d{1,2}\s\d{2}:\d{2}:\d{2})\s"
    r"(?P<host>\S+)\s"
    r"(?P<process>\S+?)(\[(?P<pid>\d+)\])?:\s"
    r"(?P<message>.*)$"
)


def parse_syslog_regex(raw_log):
    match = SYSLOG_PATTERN.match(raw_log.strip())
    if not match:
        # fall back so a bad line doesn't crash the whole batch
        return {"raw": raw_log.strip(), "parse_error": "syslog_pattern_mismatch"}
    return {k: v for k, v in match.groupdict().items() if v is not None}


# ---------------------------------------------------------------------------
# CEF (Common Event Format) parser
# CEF:Version|Vendor|Product|Version|SignatureID|Name|Severity|Extension
# ---------------------------------------------------------------------------

def parse_cef(raw_log):
    raw_log = raw_log.strip()
    if not raw_log.startswith("CEF:"):
        return {"raw": raw_log, "parse_error": "not_cef_format"}

    parts = raw_log.split("|")
    if len(parts) < 8:
        return {"raw": raw_log, "parse_error": "cef_field_count_mismatch"}

    result = {
        "cef_version": parts[0].replace("CEF:", ""),
        "vendor": parts[1],
        "product": parts[2],
        "product_version": parts[3],
        "signature_id": parts[4],
        "name": parts[5],
        "severity": parts[6],
    }

    # extension is key=value pairs separated by spaces (values can't contain
    # unescaped spaces in real CEF, good enough for a prototype)
    extension = "|".join(parts[7:])
    for kv in extension.split(" "):
        if "=" in kv:
            k, v = kv.split("=", 1)
            result[k] = v

    return result


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------

def parse_log(raw_log, format_type, headers=None):
    """
    raw_log: the raw log string (a single record — one line, or a full
             json/xml blob depending on format_type)
    format_type: "json" | "csv" | "syslog" | "xml" | "cef"
    headers: required for "csv" — list of column names matching the row order
    """
    format_type = format_type.lower()

    if format_type == "json":
        return flatten(json.loads(raw_log))

    if format_type == "csv":
        if not headers:
            raise ValueError("CSV parsing requires a 'headers' list")
        values = raw_log.strip().split(",")
        return dict(zip(headers, values))

    if format_type == "syslog":
        return parse_syslog_regex(raw_log)

    if format_type == "xml":
        if xmltodict is None:
            raise ImportError("xmltodict is required for XML parsing — pip install xmltodict")
        return flatten(xmltodict.parse(raw_log))

    if format_type == "cef":
        return parse_cef(raw_log)

    raise ValueError(f"Unsupported format_type: {format_type}")
