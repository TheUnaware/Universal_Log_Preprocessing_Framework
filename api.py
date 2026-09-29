import os
import sys
import json
import tempfile

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from parser import parse_log                      # noqa: E402  (real file)
from normalizer import normalize                   # noqa: E402  (real file)
from main import read_records_from_file             # noqa: E402  (real file)
from field_mapper import (                          # noqa: E402  (real file)
    clean_name, name_score, value_type, compatible, overlap, strong_id,
    should_review_mapping, CACHE,
)

app = FastAPI(title="ULPF Backend — wraps parser.py / normalizer.py / field_mapper.py / main.py")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def serve_dashboard():
    """Serves the frontend dashboard directly when hosted online."""
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
    return FileResponse(html_path)


# ---------------------------------------------------------------------
# In-memory session (single demo session — fine for a hackathon prototype)
# ---------------------------------------------------------------------
class Session:
    def __init__(self):
        self.files = []
        self.normalized = []
        self.field_values = {}
        self.auto_matches = []
        self.pending_matches = []
        self.canonical = {}
        self.lineage = []


SESSION = Session()


def load_cache():
    if os.path.exists(CACHE):
        try:
            with open(CACHE) as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_cache(cache):
    with open(CACHE, "w") as f:
        json.dump(cache, f, indent=2)


class DecisionIn(BaseModel):
    key: str
    accept: bool


# ---------------------------------------------------------------------
# STATUS
# ---------------------------------------------------------------------
@app.get("/api/status")
def status():
    cache = load_cache()
    pending_left = [p for p in SESSION.pending_matches if p["key"] not in cache]
    return {
        "engine": "online",
        "total_files": len(SESSION.files),
        "total_records": len(SESSION.normalized),
        "auto_matched": len(SESSION.auto_matches),
        "pending": len(pending_left),
        "cached_decisions": len(cache),
    }


@app.post("/api/reset")
def reset():
    global SESSION
    SESSION = Session()
    if os.path.exists(CACHE):
        os.remove(CACHE)
    return {"status": "reset"}


# ---------------------------------------------------------------------
# UPLOAD — calls main.read_records_from_file + parser.parse_log + normalizer.normalize
# ---------------------------------------------------------------------
@app.post("/api/upload")
async def upload(
    file: UploadFile = File(...),
    format_type: str = Form(...),
    source_type: str = Form(...),
):
    format_type = format_type.lower()
    content = await file.read()

    suffix = "_" + file.filename.replace("/", "_")
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        raw_records, headers = read_records_from_file(tmp_path, format_type)
    except Exception as e:
        os.remove(tmp_path)
        raise HTTPException(400, f"Failed to read file as {format_type}: {e}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    parsed_count, errors = 0, 0
    for raw in raw_records:
        try:
            parsed = parse_log(raw, format_type, headers=headers)
        except Exception:
            errors += 1
            continue
        record = normalize(parsed, source_type=source_type, format_type=format_type)
        SESSION.normalized.append(record)
        parsed_count += 1

    file_entry = {
        "name": file.filename,
        "format": format_type,
        "source": source_type,
        "records": parsed_count,
        "errors": errors,
        "size": len(content),
        "status": "PARSED" if parsed_count else "ERROR",
    }
    SESSION.files.append(file_entry)

    return {
        "file": file_entry,
        "total_records": len(SESSION.normalized),
        "total_files": len(SESSION.files),
    }


@app.get("/api/files")
def get_files():
    return {"files": SESSION.files, "total_records": len(SESSION.normalized)}


# ---------------------------------------------------------------------
# ANALYZE — mirrors field_mapper.map_fields()'s tiering logic, but calls
# the real comparison primitives from field_mapper.py directly, and splits
# the interactive part into a non-blocking HTTP round trip.
# ---------------------------------------------------------------------
@app.post("/api/analyze")
def analyze():
    if not SESSION.normalized:
        raise HTTPException(400, "No records uploaded yet")

    values = {}
    for record in SESSION.normalized:
        for field, value in record["fields"].items():
            if value in (None, ""):
                continue
            values.setdefault(field, []).append(value)
    SESSION.field_values = values

    cache = load_cache()
    fields = sorted(values)
    auto, pending = [], []

    for i in range(len(fields)):
        for j in range(i + 1, len(fields)):
            a, b = fields[i], fields[j]
            va, vb = values[a], values[b]

            if not compatible(va, vb):          # <- real field_mapper.compatible()
                continue

            score = name_score(a, b)             # <- real field_mapper.name_score()
            common, ratio = overlap(va, vb)       # <- real field_mapper.overlap()
            key = f"{a}|{b}"

            if key in cache:
                if cache[key]:
                    auto.append({
                        "a": a, "b": b, "key": key, "confidence": 1.0,
                        "reason": "Previously confirmed (cached from confirmed_mappings.json)",
                        "sampleA": va[0], "sampleB": vb[0], "common": list(common)[:5],
                        "cached": True,
                    })
                continue

            if score >= 0.85 and ratio >= 0.50:
                auto.append({
                    "a": a, "b": b, "key": key, "confidence": round(score, 2),
                    "reason": "Strong field-name similarity + value overlap",
                    "sampleA": va[0], "sampleB": vb[0], "common": list(common)[:5],
                })
                continue

            strong = {v for v in common if strong_id(v)}  # <- real field_mapper.strong_id()
            if strong and ratio >= 0.75:
                auto.append({
                    "a": a, "b": b, "key": key, "confidence": round(ratio, 2),
                    "reason": "Shared structured identifier pattern",
                    "sampleA": va[0], "sampleB": vb[0], "common": list(common)[:5],
                })
                continue

            if should_review_mapping(score, common, ratio):
                pending.append({
                    "a": a, "b": b, "key": key,
                    "score": round(score, 2), "ratio": round(ratio, 2),
                    "sampleA": va[0], "sampleB": vb[0], "common": list(common)[:5],
                })

    # Cache is only read in analyze(), never modified. Cache is only saved on user decision in decide().

    SESSION.auto_matches = auto
    SESSION.pending_matches = pending
    _recompute_canonical()

    return {"auto_matched": auto, "needs_confirmation": pending}


# ---------------------------------------------------------------------
# DECIDE — one-time confirmation, written to the real cache file
# ---------------------------------------------------------------------
@app.post("/api/decide")
def decide(d: DecisionIn):
    cache = load_cache()
    cache[d.key] = d.accept
    save_cache(cache)
    _recompute_canonical()

    pending_left = [p for p in SESSION.pending_matches if p["key"] not in load_cache()]
    return {"status": "ok", "remaining_pending": len(pending_left)}


def _recompute_canonical():
    """Union-Find clustering + canonical naming — same approach map_fields() uses."""
    fields = list(SESSION.field_values.keys())
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

    cache = load_cache()
    for m in SESSION.auto_matches:
        if m["a"] in parent and m["b"] in parent:
            union(m["a"], m["b"])
    for key, accepted in cache.items():
        if accepted and "|" in key:
            a, b = key.split("|", 1)
            if a in parent and b in parent:
                union(a, b)

    groups = {}
    for f in fields:
        groups.setdefault(find(f), []).append(f)

    preferred = {"user_id", "ride_id", "amount", "src", "dst",
                 "source_ip", "destination_ip", "timestamp", "status"}
    canonical = {}
    for members in groups.values():
        name = next((x for x in members if x.lower() in preferred), min(members, key=len))
        for f in members:
            canonical[f] = name
    SESSION.canonical = canonical

    lineage = []
    for f in fields:
        if canonical[f] == f:
            continue
        auto_hit = next((m for m in SESSION.auto_matches if f in (m["a"], m["b"])), None)
        manual_hit = f"{f}|{canonical[f]}" in cache or f"{canonical[f]}|{f}" in cache
        if auto_hit:
            conf, typ = auto_hit["confidence"], ("CACHED" if auto_hit.get("cached") else "AUTO")
        elif manual_hit:
            conf, typ = 0.80, "MANUAL"
        else:
            conf, typ = 0.75, "AUTO"
        lineage.append({"original": f, "canonical": canonical[f], "confidence": conf, "type": typ})
    SESSION.lineage = lineage


# ---------------------------------------------------------------------
# OUTPUT — mirrors main.py's final output shape
# ---------------------------------------------------------------------
@app.get("/api/records")
def get_records():
    records = []
    for record in SESSION.normalized:
        new_fields = {SESSION.canonical.get(f, f): v for f, v in record["fields"].items()}
        records.append({**record, "fields": new_fields})
    return {"record_count": len(records), "records": records}


@app.post("/api/merge")
def merge_records():
    if not SESSION.normalized:
        raise HTTPException(400, "No records uploaded yet")

    records = []
    for record in SESSION.normalized:
        mapped_fields = {SESSION.canonical.get(f, f): v for f, v in record["fields"].items()}
        records.append({**record, "fields": mapped_fields})

    report = {}
    for key, canonical in SESSION.canonical.items():
        if key != canonical:
            report[key] = canonical

    payload = {
        "record_count": len(records),
        "field_mapping_report": report,
        "records": records,
    }

    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "merged_output.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    SESSION.merged_output = payload
    return {
        "status": "ok",
        "output_path": output_path,
        "record_count": len(records),
        "field_mapping_report": report,
    }


@app.get("/api/lineage")
def get_lineage():
    avg = (sum(l["confidence"] for l in SESSION.lineage) / len(SESSION.lineage)) if SESSION.lineage else 0
    return {"lineage": SESSION.lineage, "avg_confidence": round(avg, 3)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
