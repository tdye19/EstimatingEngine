"""
Productivity Brain — Ingestion Script
Parses WinEst Excel exports and loads them into the central SQLite database.

Handles two known WinEst export formats:
  - 26-column "Civil Est Report" (City Gate style)
  - 21-column "Estimate Report" (Leonidas/Spring Arbor style)

Usage:
    python ingest.py <file_or_folder>         # Ingest one file or all .xlsx in a folder
    python ingest.py <folder> --recursive     # Walk subdirectories
    python ingest.py <file> --force           # Re-ingest even if already loaded
"""

import pandas as pd
import sqlite3
import hashlib
import os
import sys
import glob
import argparse
from schema import get_db, init_db, DB_PATH


# ── Column mappings for known WinEst export formats ──

FORMAT_26 = {
    'name': 'CCI Civil Est Report (26-col)',
    'identifier': '_CCI Civil Est Report',
    'cols': {
        'wbs': 1,
        'desc': 3,
        'qty': 4,
        'unit': 5,
        'prod': 6,
        'prod_unit': 7,
        'crew': 8,
        'labor_hrs': 10,
        'labor_up': 11,
        'mat_up': 12,
        'equip_prod': 13,
        'equip_up': 17,
        'subs_up': 18,
        'labor_total': 19,
        'mat_total': 20,
        'equip_total': 21,
        'subs_total': 22,
        'grand_total': 25,
    },
    'project_name_col': 3,
    'totals_row': 4,
    'totals_hrs_col': 10,
    'totals_rate_col': 16,
    'totals_labor_col': 19,
    'totals_mat_col': 20,
    'totals_equip_col': 21,
    'totals_subs_col': 22,
    'totals_grand_col': 25,
}

FORMAT_21 = {
    'name': 'CCI Estimate Report (21-col)',
    'identifier': '_CCI Estimate Report',
    'cols': {
        'wbs': 1,
        'desc': 2,
        'qty': 3,
        'unit': 4,
        'crew': 5,
        'prod': 6,
        'prod_unit': 7,
        'labor_hrs': 8,
        'labor_up': 9,
        'mat_up': 10,
        'equip_prod': 11,
        'equip_up': 12,
        'subs_up': 13,
        'labor_total': 14,
        'mat_total': 15,
        'equip_total': 16,
        'subs_total': 17,
        'grand_total': 20,
    },
    'project_name_col': 3,
    'totals_row': 4,
    'totals_hrs_col': 8,
    'totals_rate_col': None,
    'totals_labor_col': 14,
    'totals_mat_col': 15,
    'totals_equip_col': 16,
    'totals_subs_col': 17,
    'totals_grand_col': 20,
}


def detect_format(df):
    """Detect which WinEst export format this file uses."""
    cell_00 = str(df.iloc[0, 0]) if pd.notna(df.iloc[0, 0]) else ''
    if FORMAT_26['identifier'] in cell_00:
        return FORMAT_26
    elif FORMAT_21['identifier'] in cell_00:
        return FORMAT_21
    # Fallback: check column count
    if df.shape[1] >= 25:
        return FORMAT_26
    elif df.shape[1] >= 20:
        return FORMAT_21
    return None


def file_hash(filepath):
    """Compute MD5 hash of file for change detection."""
    h = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def extract_project_name(filepath, df, fmt):
    """Extract a clean project name from the file path in cell."""
    raw = str(df.iloc[0, fmt['project_name_col']]) if pd.notna(df.iloc[0, fmt['project_name_col']]) else ''
    if raw and '.est' in raw:
        # Extract filename without extension from the path
        name = os.path.splitext(os.path.basename(raw))[0]
        # Clean up common prefixes
        for prefix in ['2024-25 CCI Concrete 10_13_22 w GCs - ', 'CCI Concrete ']:
            if name.startswith(prefix):
                name = name[len(prefix):]
        return name.strip()
    # Fallback to export filename
    return os.path.splitext(os.path.basename(filepath))[0]


def safe_float(val):
    """Safely convert to float, handling NaN and strings."""
    if pd.isna(val):
        return None
    try:
        v = float(str(val).replace(',', ''))
        return v
    except (ValueError, TypeError):
        return None


def safe_str(val):
    """Safely convert to string."""
    if pd.isna(val):
        return None
    s = str(val).strip()
    return s if s and s != 'nan' else None


def ingest_file(filepath, db_path=None, force=False):
    """Parse a single WinEst Excel export and load it into the database."""
    filepath = os.path.abspath(filepath)
    conn = get_db(db_path)
    c = conn.cursor()

    # Check if already ingested
    fhash = file_hash(filepath)
    existing = c.execute("SELECT id, file_hash FROM projects WHERE file_path = ?", (filepath,)).fetchone()

    if existing and not force:
        if existing['file_hash'] == fhash:
            print(f"  SKIP (unchanged): {os.path.basename(filepath)}")
            conn.close()
            return False
        else:
            # File changed — delete old data and re-ingest
            print(f"  UPDATE (file changed): {os.path.basename(filepath)}")
            c.execute("DELETE FROM line_items WHERE project_id = ?", (existing['id'],))
            c.execute("DELETE FROM projects WHERE id = ?", (existing['id'],))
            conn.commit()
    elif existing and force:
        c.execute("DELETE FROM line_items WHERE project_id = ?", (existing['id'],))
        c.execute("DELETE FROM projects WHERE id = ?", (existing['id'],))
        conn.commit()

    # Read the file
    try:
        df = pd.read_excel(filepath, header=None)
    except Exception as e:
        print(f"  ERROR reading {filepath}: {e}")
        conn.close()
        return False

    # Detect format
    fmt = detect_format(df)
    if fmt is None:
        print(f"  ERROR: Unknown format for {os.path.basename(filepath)}")
        conn.close()
        return False

    cols = fmt['cols']
    project_name = extract_project_name(filepath, df, fmt)

    # Extract project totals from the totals row
    tr = fmt['totals_row']
    total_hrs = safe_float(df.iloc[tr, fmt['totals_hrs_col']]) if fmt['totals_hrs_col'] is not None else None
    avg_rate = safe_float(df.iloc[tr, fmt['totals_rate_col']]) if fmt.get('totals_rate_col') else None
    total_labor = safe_float(df.iloc[tr, fmt['totals_labor_col']]) if fmt['totals_labor_col'] is not None else None
    total_mat = safe_float(df.iloc[tr, fmt['totals_mat_col']]) if fmt['totals_mat_col'] is not None else None
    total_equip = safe_float(df.iloc[tr, fmt['totals_equip_col']]) if fmt['totals_equip_col'] is not None else None
    total_subs = safe_float(df.iloc[tr, fmt['totals_subs_col']]) if fmt['totals_subs_col'] is not None else None
    total_grand = safe_float(df.iloc[tr, fmt['totals_grand_col']]) if fmt['totals_grand_col'] is not None else None

    # Extract export date from row 0
    export_date = safe_str(df.iloc[0, 5]) if df.shape[1] > 5 else None

    # Insert project
    c.execute("""
        INSERT INTO projects (project_name, file_path, file_hash, export_date,
            total_labor_hrs, total_labor_dollars, total_mat_dollars,
            total_equip_dollars, total_subs_dollars, grand_total, avg_labor_rate)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (project_name, filepath, fhash, export_date,
          total_hrs, total_labor, total_mat, total_equip, total_subs, total_grand, avg_rate))

    project_id = c.lastrowid

    # Parse line items
    items_loaded = 0
    for idx in range(4, len(df)):
        row = df.iloc[idx]

        desc = safe_str(row[cols['desc']])
        if desc is None:
            continue

        prod = safe_float(row[cols['prod']])
        prod_unit = safe_str(row[cols['prod_unit']])
        qty = safe_float(row[cols['qty']])
        unit = safe_str(row[cols['unit']])
        crew = safe_str(row[cols['crew']])
        wbs = safe_str(row[cols['wbs']])
        labor_hrs = safe_float(row[cols['labor_hrs']])
        labor_up = safe_float(row[cols['labor_up']])
        mat_up = safe_float(row[cols['mat_up']])
        equip_prod = safe_float(row[cols.get('equip_prod')]) if cols.get('equip_prod') is not None else None
        equip_up = safe_float(row[cols.get('equip_up')]) if cols.get('equip_up') is not None else None
        subs_up = safe_float(row[cols.get('subs_up')]) if cols.get('subs_up') is not None else None
        labor_total = safe_float(row[cols['labor_total']]) if cols.get('labor_total') is not None else None
        mat_total = safe_float(row[cols['mat_total']]) if cols.get('mat_total') is not None else None
        equip_total = safe_float(row[cols.get('equip_total')]) if cols.get('equip_total') is not None else None
        subs_total = safe_float(row[cols.get('subs_total')]) if cols.get('subs_total') is not None else None
        grand_total_li = safe_float(row[cols['grand_total']]) if cols.get('grand_total') is not None else None

        # Determine if this is a summary/rollup row (has prod but no prod_unit with unit type)
        is_summary = 1 if (prod is not None and (prod_unit is None or prod_unit == '')) else 0

        c.execute("""
            INSERT INTO line_items (
                project_id, row_index, wbs_area, description, quantity, unit,
                crew_mix, prod_rate, prod_unit, labor_hours, labor_unit_price,
                mat_unit_price, equip_prod, equip_unit_price, subs_unit_price,
                labor_total, mat_total, equip_total, subs_total, grand_total,
                is_summary_row
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (project_id, idx, wbs, desc, qty, unit, crew, prod, prod_unit,
              labor_hrs, labor_up, mat_up, equip_prod, equip_up, subs_up,
              labor_total, mat_total, equip_total, subs_total, grand_total_li,
              is_summary))

        items_loaded += 1

    conn.commit()
    conn.close()
    print(f"  LOADED: {project_name} — {items_loaded} line items ({fmt['name']})")
    return True


def ingest_folder(folder_path, db_path=None, recursive=False, force=False):
    """Ingest all .xlsx files in a folder."""
    folder_path = os.path.abspath(folder_path)

    if recursive:
        pattern = os.path.join(folder_path, '**', '*.xlsx')
        files = glob.glob(pattern, recursive=True)
    else:
        pattern = os.path.join(folder_path, '*.xlsx')
        files = glob.glob(pattern)

    # Filter out temp files
    files = [f for f in files if not os.path.basename(f).startswith('~')]

    if not files:
        print(f"No .xlsx files found in {folder_path}")
        return

    print(f"\nFound {len(files)} Excel files to process")
    print("=" * 60)

    loaded = 0
    skipped = 0
    errors = 0

    for f in sorted(files):
        try:
            result = ingest_file(f, db_path=db_path, force=force)
            if result:
                loaded += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"  ERROR: {os.path.basename(f)} — {e}")
            errors += 1

    print("=" * 60)
    print(f"Done: {loaded} loaded, {skipped} skipped, {errors} errors")


def show_stats(db_path=None):
    """Print database statistics."""
    conn = get_db(db_path)
    c = conn.cursor()

    projects = c.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    items = c.execute("SELECT COUNT(*) FROM line_items").fetchone()[0]
    activities = c.execute("SELECT COUNT(*) FROM line_items WHERE prod_rate IS NOT NULL AND is_summary_row = 0").fetchone()[0]
    unique_activities = c.execute("""
        SELECT COUNT(DISTINCT description) FROM line_items
        WHERE prod_rate IS NOT NULL AND prod_unit IS NOT NULL AND is_summary_row = 0
    """).fetchone()[0]

    print(f"\n{'='*50}")
    print(f"  PRODUCTIVITY BRAIN — Database Stats")
    print(f"{'='*50}")
    print(f"  Projects loaded:        {projects}")
    print(f"  Total line items:       {items}")
    print(f"  Activity rows w/ rates: {activities}")
    print(f"  Unique activities:      {unique_activities}")

    if projects > 0:
        print(f"\n  Projects:")
        for row in c.execute("SELECT project_name, total_labor_hrs, grand_total FROM projects ORDER BY project_name"):
            hrs = f"{row[1]:,.0f}" if row[1] else "—"
            gt = f"${row[2]:,.0f}" if row[2] else "—"
            print(f"    • {row[0]:40s}  Hrs: {hrs:>8s}  Total: {gt:>10s}")

    print(f"{'='*50}\n")
    conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Ingest WinEst Excel exports into Productivity Brain')
    parser.add_argument('path', nargs='?', help='File or folder to ingest')
    parser.add_argument('--recursive', '-r', action='store_true', help='Walk subdirectories')
    parser.add_argument('--force', '-f', action='store_true', help='Re-ingest even if unchanged')
    parser.add_argument('--stats', '-s', action='store_true', help='Show database statistics')
    parser.add_argument('--db', default=None, help='Custom database path')

    args = parser.parse_args()

    # Initialize DB
    init_db(args.db)

    if args.stats:
        show_stats(args.db)
    elif args.path:
        if os.path.isfile(args.path):
            ingest_file(args.path, db_path=args.db, force=args.force)
        elif os.path.isdir(args.path):
            ingest_folder(args.path, db_path=args.db, recursive=args.recursive, force=args.force)
        else:
            print(f"Path not found: {args.path}")
        show_stats(args.db)
    else:
        parser.print_help()
