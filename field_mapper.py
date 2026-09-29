import json
import os
import re
from difflib import SequenceMatcher

CACHE = os.path.join(os.path.dirname(__file__), "confirmed_mappings.json")


def clean_name(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def name_score(a, b):
    return SequenceMatcher(None, clean_name(a), clean_name(b)).ratio()


def value_type(v):
    if v is None:
        return "empty"
    if isinstance(v, bool):
        return "boolean"
    text = str(v).strip()
    if text == "":
        return "empty"
    try:
        float(text)
        return "number"
    except (TypeError, ValueError):
        return "string"


def compatible(a, b):
    a = [x for x in a if x is not None and str(x).strip() != ""]
    b = [x for x in b if x is not None and str(x).strip() != ""]

    if not a or not b:
        return True

    a_types = {value_type(x) for x in a}
    b_types = {value_type(x) for x in b}

    if a_types == b_types:
        return True

    # Numeric-like strings and actual numbers represent the same logical value
    # family for matching purposes, even when the source files serialize them
    # differently (e.g. "123" vs 123).
    if a_types <= {"number", "string"} and b_types <= {"number", "string"}:
        return True

    return False


def overlap(a, b):
    a = {str(x).strip().lower() for x in a}
    b = {str(x).strip().lower() for x in b}
    common = a & b
    ratio = len(common) / min(len(a), len(b)) if common else 0
    return common, ratio


def should_review_mapping(score, common, ratio):
    return bool(
        (score >= 0.55 and common)
        or (len(common) >= 2 and ratio >= 0.50)
        or score >= 0.65
    )


def strong_id(value):
    return bool(
        re.match(
            r"^[A-Z]{2,}[-_][A-Z0-9]*\d{3,}$",
            str(value).strip().upper()
        )
    )


def ask(a, b, score, common, va, vb):

    print("\n" + "=" * 55)
    print("FIELD MAPPING REVIEW")
    print("=" * 55)

    print(f"Field A : {a}")
    print(f"Value A : {va[0]}")
    print(f"Type A  : {value_type(va[0])}")

    print()

    print(f"Field B : {b}")
    print(f"Value B : {vb[0]}")
    print(f"Type B  : {value_type(vb[0])}")

    print(f"\nName similarity : {score:.2f}")
    print(f"Common values   : {list(common)[:5]}")

    return input("\nAre these the same field? (y/n): ").strip().lower() == "y"


def map_fields(normalized_records, ask_org_callback=None):

    if os.path.exists(CACHE):
        try:
            with open(CACHE, "r") as f:
                cache = json.load(f)
        except:
            cache = {}
    else:
        cache = {}

    values = {}

    for record in normalized_records:
        for field, value in record["fields"].items():
            values.setdefault(field, []).append(value)

    fields = sorted(values)
    matches = []

    for i in range(len(fields)):
        for j in range(i + 1, len(fields)):

            a, b = fields[i], fields[j]
            va, vb = values[a], values[b]

            if not compatible(va, vb):
                continue

            score = name_score(a, b)
            common, ratio = overlap(va, vb)
            key = f"{a}|{b}"

            if key in cache:
                if cache[key]:
                    matches.append((a, b))
                continue

            # Strong name + value match
            if score >= 0.85 and ratio >= 0.50:
                matches.append((a, b))
                continue

            # Strong identifier match
            strong = {
                v for v in common
                if strong_id(v)
            }

            if strong and ratio >= 0.75:
                matches.append((a, b))
                continue

            # Ask only when there is actual evidence
            should_ask = should_review_mapping(score, common, ratio)

            if should_ask:

                if ask_org_callback:
                    answer = ask_org_callback(
                        a, b, score, va, vb
                    )
                else:
                    answer = ask(
                        a, b, score, common, va, vb
                    )

                cache[key] = answer

                if answer:
                    matches.append((a, b))

    with open(CACHE, "w") as f:
        json.dump(cache, f, indent=2)

    # Union-Find
    parent = {f: f for f in fields}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for a, b in matches:
        union(a, b)

    groups = {}

    for field in fields:
        groups.setdefault(find(field), []).append(field)

    preferred = {
        "user_id",
        "ride_id",
        "amount",
        "src",
        "dst",
        "timestamp",
        "status"
    }

    canonical = {}

    for members in groups.values():

        name = next(
            (x for x in members if x.lower() in preferred),
            min(members, key=len)
        )

        for field in members:
            canonical[field] = name

    mapped_records = []

    for record in normalized_records:

        new_fields = {}

        for field, value in record["fields"].items():
            new_fields[canonical.get(field, field)] = value

        mapped_records.append({
            **record,
            "fields": new_fields
        })

    report = {
        field: canonical[field]
        for field in fields
        if field != canonical[field]
    }

    return mapped_records, report