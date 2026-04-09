"""CLI script — bulk load WinEst XLSX exports from apex/backend/db/data/winest/.

Usage:
  # Bulk scan directory
  python apex/backend/db/load_remaining_projects.py

  # Single file
  python apex/backend/db/load_remaining_projects.py path/to/file.xlsx "Project Name" \\
      --region michigan --type industrial

Options:
  --region <region>   Project region (default: michigan)
  --type <type>       Project type (default: commercial)
  --sector <sector>   Market sector (default: commercial)
  --method <method>   Delivery method (default: cmar)
  --dq <score>        Data quality score (default: 0.6)
"""

import argparse
import os
import sys

# Add project root to path so apex.backend imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apex.backend.db.database import Base, SessionLocal
from apex.backend.models.decision_models import ComparableProject
from apex.backend.services.decision_project_loader import load_winest_project


_WINEST_DIR = os.path.join(os.path.dirname(__file__), "data", "winest")

_DEFAULT_CONTEXT = {
    "project_type":   "commercial",
    "market_sector":  "commercial",
    "region":         "michigan",
    "delivery_method":"cmar",
    "contract_type":  "self_perform",
    "complexity_level":"medium",
    "data_quality_score": 0.6,
}


def _make_name(filename: str) -> str:
    stem = os.path.splitext(os.path.basename(filename))[0]
    return stem.replace("_", " ").replace("-", " ")


def _dedupe_name(db, name: str) -> str:
    """Append incrementing count to name if it already exists."""
    existing = {r[0] for r in db.query(ComparableProject.name).all()}
    if name not in existing:
        return name
    count = 2
    while f"{name} ({count})" in existing:
        count += 1
    return f"{name} ({count})"


def bulk_load(args):
    """Scan winest directory and load all XLSX files."""
    scan_dir = _WINEST_DIR
    if not os.path.isdir(scan_dir):
        print(f"[load] winest directory not found: {scan_dir}")
        print("  Create it and add XLSX exports, then re-run.")
        return

    files = [
        os.path.join(scan_dir, f)
        for f in sorted(os.listdir(scan_dir))
        if f.lower().endswith(".xlsx")
    ]

    if not files:
        print(f"[load] No XLSX files found in {scan_dir}")
        return

    # Create tables
    from apex.backend.db.database import engine
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    total_projects = 0
    total_obs = 0

    try:
        for file_path in files:
            name_raw = _make_name(file_path)
            name = _dedupe_name(db, name_raw)
            metadata = {**_DEFAULT_CONTEXT, "name": name}

            # Override context from CLI args if provided
            if hasattr(args, "region") and args.region:
                metadata["region"] = args.region
            if hasattr(args, "type") and getattr(args, "type", None):
                metadata["project_type"] = getattr(args, "type")
            if hasattr(args, "sector") and args.sector:
                metadata["market_sector"] = args.sector
            if hasattr(args, "method") and args.method:
                metadata["delivery_method"] = args.method
            if hasattr(args, "dq") and args.dq:
                metadata["data_quality_score"] = float(args.dq)

            try:
                result = load_winest_project(db, file_path, metadata)
                db.commit()
                print(
                    f"  [OK] {result['project_name']}: "
                    f"{result['observations_loaded']} observations"
                )
                total_projects += 1
                total_obs += result["observations_loaded"]
            except FileNotFoundError as e:
                print(f"  [SKIP] {file_path}: {e}")
            except ValueError as e:
                print(f"  [SKIP] {file_path}: {e}")
            except Exception as e:
                db.rollback()
                print(f"  [ERROR] {file_path}: {e}")

    finally:
        db.close()

    print(f"\n[load] Done — {total_projects} projects, {total_obs} observations loaded")


def single_load(args):
    """Load a single XLSX file with explicit metadata."""
    file_path = args.file
    if not os.path.exists(file_path):
        print(f"[ERROR] File not found: {file_path}")
        sys.exit(1)

    name = args.name if args.name else _make_name(file_path)
    metadata = {
        **_DEFAULT_CONTEXT,
        "name": name,
        "region": args.region or "michigan",
        "project_type": getattr(args, "type", "commercial") or "commercial",
        "market_sector": args.sector or "commercial",
        "delivery_method": args.method or "cmar",
        "data_quality_score": float(args.dq) if args.dq else 0.6,
    }

    from apex.backend.db.database import engine
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        result = load_winest_project(db, file_path, metadata)
        db.commit()
        print(f"[OK] {result['project_name']}: {result['observations_loaded']} observations loaded")
    except Exception as e:
        db.rollback()
        print(f"[ERROR] {e}")
        sys.exit(1)
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description="Load WinEst XLSX projects into the APEX decision system"
    )
    parser.add_argument("file", nargs="?", help="Path to single XLSX file (omit for bulk mode)")
    parser.add_argument("name", nargs="?", help="Project name for single file mode")
    parser.add_argument("--region", default=None)
    parser.add_argument("--type", default=None, dest="type")
    parser.add_argument("--sector", default=None)
    parser.add_argument("--method", default=None)
    parser.add_argument("--dq", default=None, help="Data quality score 0-1")

    args = parser.parse_args()

    if args.file:
        single_load(args)
    else:
        bulk_load(args)


if __name__ == "__main__":
    main()
