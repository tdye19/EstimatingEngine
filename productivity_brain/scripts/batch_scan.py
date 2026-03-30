"""
Productivity Brain — Batch Scanner
Scans estimate folder trees for WinEst export files.

On your work machine, point this at Q:\\Estimate Files\\ and it will:
1. Walk all subdirectories
2. Find .xlsx files that look like WinEst exports
3. Ingest them all into the database
4. Skip files already loaded (unless --force)

Usage:
    python batch_scan.py "Q:\\Estimate Files\\2025 Estimate Files\\001 CCI"
    python batch_scan.py "Q:\\Estimate Files" --recursive
    python batch_scan.py "Q:\\Estimate Files" --dry-run     # Preview only
"""

import os
import sys
import glob
import argparse
import pandas as pd
from ingest import ingest_file, detect_format, show_stats
from schema import init_db


def is_winest_export(filepath):
    """Quick check if a file looks like a WinEst Excel export."""
    try:
        # Read just the first row to check
        df = pd.read_excel(filepath, header=None, nrows=1)
        cell = str(df.iloc[0, 0]) if pd.notna(df.iloc[0, 0]) else ''
        return '_CCI' in cell or 'Est Report' in cell
    except Exception:
        return False


def scan_folder(folder_path, recursive=True, dry_run=False, force=False, db_path=None):
    """Scan a folder tree for WinEst exports and optionally ingest them."""
    folder_path = os.path.abspath(folder_path)

    if not os.path.isdir(folder_path):
        print(f"ERROR: Not a directory: {folder_path}")
        return

    # Find all .xlsx files
    if recursive:
        pattern = os.path.join(folder_path, '**', '*.xlsx')
        all_files = glob.glob(pattern, recursive=True)
    else:
        pattern = os.path.join(folder_path, '*.xlsx')
        all_files = glob.glob(pattern)

    # Filter out temp files and non-WinEst files
    all_files = [f for f in all_files if not os.path.basename(f).startswith('~')]

    print(f"\nScanning: {folder_path}")
    print(f"Found {len(all_files)} .xlsx files total")
    print("=" * 70)

    winest_files = []
    for f in sorted(all_files):
        if is_winest_export(f):
            rel_path = os.path.relpath(f, folder_path)
            size_kb = os.path.getsize(f) / 1024
            print(f"  ✓ WinEst export: {rel_path} ({size_kb:.0f} KB)")
            winest_files.append(f)
        else:
            rel_path = os.path.relpath(f, folder_path)
            print(f"  ✗ Not WinEst:    {rel_path}")

    print(f"\n{len(winest_files)} WinEst exports found out of {len(all_files)} total files")

    if dry_run:
        print("\n[DRY RUN — no files were ingested]")
        return

    if winest_files:
        print(f"\nIngesting {len(winest_files)} files...")
        print("─" * 70)
        loaded = 0
        for f in winest_files:
            try:
                if ingest_file(f, db_path=db_path, force=force):
                    loaded += 1
            except Exception as e:
                print(f"  ERROR: {os.path.basename(f)} — {e}")
        print(f"\n{loaded} files successfully ingested")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Scan for WinEst exports')
    parser.add_argument('folder', help='Root folder to scan')
    parser.add_argument('--recursive', '-r', action='store_true', default=True, help='Walk subdirs (default)')
    parser.add_argument('--no-recursive', action='store_true', help='Only scan top-level folder')
    parser.add_argument('--dry-run', '-n', action='store_true', help='Preview only, don\'t ingest')
    parser.add_argument('--force', '-f', action='store_true', help='Re-ingest all files')
    parser.add_argument('--db', default=None, help='Custom database path')

    args = parser.parse_args()

    init_db(args.db)

    recursive = not args.no_recursive
    scan_folder(args.folder, recursive=recursive, dry_run=args.dry_run,
                force=args.force, db_path=args.db)

    if not args.dry_run:
        show_stats(args.db)
