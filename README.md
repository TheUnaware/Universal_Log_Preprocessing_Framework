# Universal Log Preprocessing Framework (ULPF)

[![Live Demo](https://img.shields.io/badge/Live_Demo-Render-46E3B7?style=for-the-badge&logo=render&logoColor=white)](https://ulpf-dashboard-y9pe.onrender.com)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org)

> 🚀 **Live Web Prototype:** [https://ulpf-dashboard-y9pe.onrender.com](https://ulpf-dashboard-y9pe.onrender.com)

An intelligent, multi-format log ingestion, normalization, and field-mapping engine with both an **interactive web dashboard** and an **automated CLI pipeline**.

ULPF unifies heterogeneous log formats (**JSON, CSV, Syslog, CEF, XML**) from different vendors and environments into a single, canonical schema using value-type compatibility, string distance algorithms, and data overlap clustering.

---

## Architecture Overview

```
Raw Logs (JSON, CSV, Syslog, CEF, XML)
                 │
                 ▼
       ┌───────────────────┐
       │     STAGE 1       │  parser.py
       │ Flatten & Parse   │  Extracts raw fields into a flat dictionary
       └─────────┬─────────┘
                 │
                 ▼
       ┌───────────────────┐
       │     STAGE 2       │  normalizer.py
       │ Normalize Envelope│  Wraps fields in standard JSON metadata envelope
       └─────────┬─────────┘
                 │
                 ▼
       ┌───────────────────┐
       │     STAGE 3       │  field_mapper.py
       │ Field Equivalence │  Name similarity + Type compatibility + Value overlap
       └─────────┬─────────┘
                 │
      ┌──────────┴──────────┐
      ▼                     ▼
┌──────────────┐     ┌──────────────┐
│  CLI Engine  │     │ Web Engine   │  (api.py + index.html)
│  (main.py)   │     │ (Dashboard)  │  Interactive review & visualization
└──────────────┘     └──────────────┘
```

### The 3 Core Stages

1. **Parser (`parser.py`)**: Converts format-specific syntax (RFC syslog, CEF pipe-delimited, CSV rows, or nested JSON) into flat Python dictionaries.
2. **Normalizer (`normalizer.py`)**: Standardizes each log into a unified envelope containing metadata: `source_type`, `format`, `ingested_at`, and raw `fields`.
3. **Field Mapper (`field_mapper.py`)**: Analyzes cross-vendor schemas using:
   - **Name Similarity**: Sequence matching across field identifiers (e.g., `user_id` vs `customer_id`).
   - **Type Compatibility**: Ensures data types align before comparing values.
   - **Value Overlap**: Measures exact and structured identifier overlap (e.g., UUIDs, `USR-xxxx`, `DRV-xxxx`).
   - **Union-Find Clustering**: Groups equivalent fields into canonical clusters and standardizes all records.

---

## Quickstart

### 1. Prerequisites & Installation

- Python 3.9+ installed
- Clone or open the project folder in your terminal:

```bash
pip install -r requirements.txt
```

*(Installs `fastapi`, `uvicorn[standard]`, `python-multipart`, and `xmltodict`)*

---

### Option A: Using the Interactive Web Dashboard

> 🌐 **Try it online instantly:** Visit **[https://ulpf-dashboard-y9pe.onrender.com](https://ulpf-dashboard-y9pe.onrender.com)** (no installation required).

To run it locally on your machine:

#### Step 1: Start the Backend API

```bash
uvicorn api:app --reload --port 8000
```

You should see:
```text
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

#### Step 2: Open the Dashboard

Open `index.html` in your web browser:
- Double-click `index.html` in your file explorer, OR
- Right-click `index.html` in VS Code and select **"Open with Live Server"**, OR
- Open your browser and navigate to `file:///path/to/ULPF%20Dashboard/index.html`

The status badge in the top-left will turn green: **`PYTHON ENGINE API CONNECTED`**.

#### Step 3: Walkthrough with Sample Logs

Pre-built sample logs are provided in the `sample_logs/` directory:

1. **Upload Logs**: Drag & drop files from `sample_logs/` (or click **+ Browse Log Files**):
   - `rides_vendorA.json` (JSON ride data)
   - `rides_vendorB.csv` (CSV ride data with alternative headers)
   - `firewall_sec.cef` (CEF security logs)
   - `auth_syslog.log` (Syslog authentication events)
2. **Run Pipeline**: Click **Generate Mappings &rarr;** (or **Run Pipeline** in the top bar).
3. **Review Mappings**: Navigate to **Suggested Mappings**:
   - **Auto-Mapped**: High-confidence pairs (e.g., `ride_id` &harr; `trip_ref`, `user_id` &harr; `customer_id`) are clustered automatically.
   - **Pending Review**: Ambiguous pairs are presented with match score, sample values, and shared evidence for you to **Accept** or **Skip**.
4. **Generate Unified Dataset**: Click **Generate Unified Dataset &rarr;** to merge records under canonical field names.
5. **Inspect & Export**:
   - **Unified Records**: Search and filter transformed records across all feeds. Click **Export JSON** to download `merged_output.json`.
   - **Lineage Report**: View Union-Find cluster trees and transformation audit trails. Click **Download Report** to export `lineage_report.csv`.

---

### Option B: Using the Command Line (CLI)

The CLI (`main.py`) runs the entire pipeline headless without a browser.

#### Basic CLI Command

```bash
python main.py \
  -i sample_logs/rides_vendorA.json:json:db \
  -i sample_logs/rides_vendorB.csv:csv:db \
  -i sample_logs/auth_syslog.log:syslog:auth \
  -o merged_output.json
```

Each `-i` / `--input` flag takes `<file_path>:<format_type>:<source_type>`.

Supported formats: `json`, `csv`, `syslog`, `cef`, `xml`.

#### Interactive vs Automated (CI/CD) Mode

- **Default (Interactive)**: Prompts you in the terminal (`[y/n]`) whenever an ambiguous field mapping is encountered.
- **Automated (`--auto-confirm`)**: Automatically confirms plausible suggestions without prompting—ideal for automated pipelines and CI/CD:

```bash
python main.py \
  -i sample_logs/rides_vendorA.json:json:db \
  -i sample_logs/rides_vendorB.csv:csv:db \
  --auto-confirm \
  -o merged_output.json
```

---

## Sample Data Reference

The repository includes four test log files in `sample_logs/`:

| File | Format | Source | Key Fields Included |
|---|---|---|---|
| `rides_vendorA.json` | `json` | `db` | `ride_id`, `user_id`, `driver_id`, `status`, `amount`, `payment_mode`, `rating` |
| `rides_vendorB.csv` | `csv` | `db` | `trip_ref`, `customer_id`, `cab_driver`, `trip_status`, `fare`, `pay_method`, `customer_rating` |
| `firewall_sec.cef` | `cef` | `security` | `src`, `dst`, `spt`, `dpt`, `user_id`, `act`, `severity`, `timestamp` |
| `auth_syslog.log` | `syslog` | `auth` | `user_id`, `action`, `status`, `ip_address`, `session_id`, `timestamp` |

### Expected Schema Unification

When combining Vendor A and Vendor B:
- `ride_id` + `trip_ref` &rarr; **`ride_id`** (shared structured IDs: `RD-1001`, `RD-1003`)
- `user_id` + `customer_id` &rarr; **`user_id`** (shared user IDs: `USR-4421`, `USR-5530`)
- `amount` + `fare` &rarr; **`amount`** (numeric fare values)
- `status` + `trip_status` &rarr; **`status`** (statuses like `completed`, `cancelled`)
- `payment_mode` + `pay_method` &rarr; **`payment_mode`** (values like `UPI`, `card`, `cash`)

---

## Cache & Decision Memory

All manual user decisions (accepted or skipped mappings) are saved to:

```text
confirmed_mappings.json
```

- **Shared Memory**: Both the Web Dashboard (`/api/decide`) and the CLI (`field_mapper.py`) read and write to this exact same file. Decisions made in the dashboard are remembered when running the CLI later.
- **Resetting State**:
  - **In Web Dashboard**: Click the **Reset Demo** button in the top bar.
  - **In Terminal**: Delete the file:
    ```bash
    # Windows PowerShell
    Remove-Item "confirmed_mappings.json" -ErrorAction SilentlyContinue
    
    # Linux / macOS
    rm -f confirmed_mappings.json
    ```

---

## REST API Reference

The FastAPI server (`api.py`) exposes the following endpoints:

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/status` | Current engine status, record counts, and cached decision count |
| `POST` | `/api/upload` | Multipart file upload (invokes `parser.py` and `normalizer.py`) |
| `GET` | `/api/files` | Lists currently uploaded files and record totals |
| `POST` | `/api/analyze` | Evaluates field pairs and returns auto-matched and pending review pairs |
| `POST` | `/api/decide` | Saves a user decision (`{ "key": "fieldA\|fieldB", "accept": true }`) |
| `GET` | `/api/records` | Returns all records mapped to current canonical schemas |
| `POST` | `/api/merge` | Writes the final unified records to `merged_output.json` |
| `GET` | `/api/lineage` | Returns cluster groups, confidence scores, and transformation history |
| `POST` | `/api/reset` | Clears in-memory session and deletes `confirmed_mappings.json` |

---

## Running Tests

Unit tests verify value compatibility, mapping review thresholds, and session isolation:

```bash
# Run all tests
python -m unittest discover -s . -p "test_*.py"

# Or run specific test suites
python -m unittest test_field_mapper_compatibility.py
python -m unittest test_upload_session.py
```

---

## Repository Structure

```text
ULPF Dashboard/
├── api.py                           # FastAPI REST backend wrapping core pipeline
├── field_mapper.py                  # Step 3: Similarity scoring, overlap & clustering
├── index.html                       # Frontend SPA dashboard (Upload, Mappings, Records, Lineage)
├── main.py                          # CLI entry point (parse -> normalize -> map)
├── normalizer.py                    # Step 2: Standard envelope normalization
├── parser.py                        # Step 1: Multi-format log parsing (JSON, CSV, Syslog, CEF, XML)
├── requirements.txt                 # Python package dependencies
├── confirmed_mappings.json          # Cached human mapping decisions (auto-created)
├── merged_output.json               # Final canonical output (generated on merge/export)
├── sample_logs/                     # Ready-to-use sample vendor log streams
│   ├── rides_vendorA.json
│   ├── rides_vendorB.csv
│   ├── firewall_sec.cef
│   └── auth_syslog.log
├── test_field_mapper_compatibility.py # Unit tests for field mapping logic
└── test_upload_session.py             # Unit tests for upload session handling
```
