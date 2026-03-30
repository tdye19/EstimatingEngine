# Productivity Brain
### Central database for historical concrete estimating production rates

Built for CCI / Christman self-perform concrete estimating. Parses WinEst Excel exports, stores every line item with productivity rates in a local SQLite database, and lets you query averaged rates, compare new estimates, and track historical trends.

---

## Quick Start

```bash
# 1. Install dependencies (one time)
pip install pandas openpyxl

# 2. Initialize the database
cd scripts
python schema.py

# 3. Ingest your first estimates
python ingest.py "C:\path\to\your\exports\Highland.xlsx"
python ingest.py "C:\path\to\your\exports\Flint.xlsx"
# Or ingest a whole folder:
python ingest.py "C:\path\to\exports_folder"

# 4. Check what's loaded
python ingest.py --stats

# 5. Query rates
python query.py --all                              # All averaged rates
python query.py --activity "Wall Formwork"         # Search by activity
python query.py --crew "Formwork"                  # Filter by crew
python query.py --wbs "Heater"                     # Filter by WBS area
python query.py --detail "Wall Formwork"           # Per-project breakdown
python query.py --export rates.xlsx                # Export to Excel

# 6. Compare a new estimate against the database
python query.py --compare "C:\path\to\new_estimate.xlsx"

# 7. Batch scan your estimate archive
python batch_scan.py "Q:\Estimate Files\2025 Estimate Files\001 CCI"
python batch_scan.py "Q:\Estimate Files" --dry-run    # Preview first
```

---

## Folder Structure

```
productivity_brain/
├── data/
│   └── productivity.db          ← SQLite database (auto-created)
├── exports/                     ← Drop WinEst .xlsx exports here
├── scripts/
│   ├── schema.py                ← Database schema & initialization
│   ├── ingest.py                ← Parse WinEst exports → SQLite
│   ├── query.py                 ← Query rates, compare estimates
│   └── batch_scan.py            ← Scan folders for WinEst exports
└── README.md
```

---

## Supported WinEst Export Formats

The system auto-detects two known WinEst export formats:

| Format | Columns | Identifier | Example |
|--------|---------|------------|---------|
| CCI Civil Est Report | 26 | `_CCI Civil Est Report` | City Gate estimates |
| CCI Estimate Report | 21 | `_CCI Estimate Report` | Leonidas, Spring Arbor |

**To export from WinEst:** File → Print/Export → Excel. The system reads whatever column layout WinEst produces.

---

## How It Works

### Ingestion
- Reads the Excel file and auto-detects the column format
- Extracts the project name from the embedded .est file path
- Loads project-level totals (hours, labor $, material $, etc.)
- Parses every line item row with productivity rates
- Computes an MD5 hash to detect changed files (skip unchanged on re-run)

### Averaging
- Groups all line items by activity description
- Computes avg, min, max across all projects for each activity
- Tracks how many distinct projects contribute to each average
- Available as a SQL view (`v_activity_averages`) or via the query script

### Comparison
- Takes a new estimate Excel file
- Looks up each activity's historical average in the database
- Flags items as OK (<5% delta), REVIEW (5-20%), or UPDATE (>20%)
- Shows exactly which rates to change in WinEst

---

## Database Schema

### `projects`
One row per ingested estimate file.

| Column | Type | Description |
|--------|------|-------------|
| project_name | TEXT | Cleaned name from .est path |
| file_path | TEXT | Full path to source .xlsx (unique) |
| file_hash | TEXT | MD5 for change detection |
| total_labor_hrs | REAL | Project total labor hours |
| grand_total | REAL | Project grand total $ |
| ... | | Other totals and metadata |

### `line_items`
Every activity row from every estimate.

| Column | Type | Description |
|--------|------|-------------|
| project_id | INTEGER | FK to projects table |
| wbs_area | TEXT | WBS grouping (e.g., "M & R Building Foundation") |
| description | TEXT | Activity name (e.g., "Wall Formwork") |
| prod_rate | REAL | Productivity rate (unit/hour) |
| prod_unit | TEXT | Rate unit (e.g., "sqft/hour") |
| crew_mix | TEXT | Crew designation (e.g., "Formwork Crew") |
| labor_unit_price | REAL | Labor $/unit |
| mat_unit_price | REAL | Material $/unit |
| is_summary_row | INTEGER | 1 = rollup row, 0 = detail |
| ... | | Quantities, totals, etc. |

### Views
- `v_activity_averages` — Pre-computed averages grouped by activity
- `v_rates_by_project` — Flat view for side-by-side project comparison

---

## Workflow for Bidding

1. **Seed the database** — Ingest all historical estimates you can get
2. **Before bidding** — Export your current WinEst estimate to .xlsx
3. **Run comparison** — `python query.py --compare your_estimate.xlsx`
4. **Review flags** — Focus on UPDATE items (>20% off historical)
5. **Update in WinEst** — Adjust productivity rates using the historical averages
6. **After award** — As field data comes in, compare actual vs. estimated

---

## Future: APEX Integration Points

This database is designed to plug directly into APEX:

- **Agent 1 (Data Harvester)** — Replaces batch_scan.py with continuous monitoring
- **Agent 2 (Rate Analyst)** — Queries the database for context-weighted averages
- **Agent 3 (Spec Reader)** — Adds project context (specs, drawings) to the projects table
- **Agent 4 (Comparator)** — Automates the compare workflow with natural language
- **Streamlit Dashboard** — Visualizes trends, distributions, and outliers

The SQLite database can be upgraded to PostgreSQL when you're ready to go multi-user or add the Streamlit layer.
