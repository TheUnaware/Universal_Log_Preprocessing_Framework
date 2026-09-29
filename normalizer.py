"""
normalizer.py — STEP 2 of the pipeline

Job: take the raw flat dict produced by parser.py and wrap it into a single,
consistent JSON "envelope" shape — regardless of which format it came from.

This is intentionally dumb: it does NOT rename fields or guess field
meaning. It just standardizes the outer structure so field_mapper.py (step 3)
has one consistent shape to work with instead of 5 different ones.
"""

from datetime import datetime, timezone


def normalize(parsed_fields, source_type, format_type):
    """
    parsed_fields: the flat dict returned by parser.parse_log()
    source_type: logical origin of this log, e.g. "db", "network", "auth"
                 (this is what field_mapper.py will use to know which
                 records come from which system)
    format_type: "json" | "csv" | "syslog" | "xml" | "cef"
                 (kept for traceability/debugging, not used for logic)

    Returns a single normalized record:
    {
        "source_type": "db",
        "format": "json",
        "ingested_at": "2026-08-31T12:00:00+00:00",
        "fields": { ...untouched, source-native key/values... }
    }
    """
    if not isinstance(parsed_fields, dict):
        raise TypeError("parsed_fields must be a dict (output of parser.parse_log)")

    return {
        "source_type": source_type,
        "format": format_type,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "fields": parsed_fields,
    }


def normalize_batch(records):
    """
    records: list of tuples -> (parsed_fields, source_type, format_type)
    Convenience wrapper for normalizing many records at once.
    """
    return [normalize(pf, st, ft) for pf, st, ft in records]
