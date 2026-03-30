# Productivity Brain
## Historical Concrete Estimating Production Rates

Central database for CCI/Christman self-perform concrete estimating.
Parses WinEst Excel exports, stores every line item with productivity
rates in a local SQLite database, and provides query/compare tools.

### Status
- 24 projects ingested
- 4,513 line items
- 62 unique activities
- WinEst 26-col and 21-col format auto-detection

### Quick Start
```bash
pip install pandas openpyxl
cd scripts
python schema.py          # Initialize database
python ingest.py <file>   # Ingest WinEst export
python query.py --all     # View all rates
python query.py --compare <file>  # Compare estimate
```

### Structure
```
productivity_brain/
├── data/              ← SQLite database (gitignored)
├── exports/           ← WinEst .xlsx exports
├── scripts/
│   ├── schema.py      ← Database schema
│   ├── ingest.py      ← WinEst parser → SQLite
│   ├── query.py       ← Query rates, compare estimates
│   └── batch_scan.py  ← Folder scanner for WinEst exports
└── README.md
```
